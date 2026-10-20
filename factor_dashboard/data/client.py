"""AKShare 数据接口封装：重试、字段规范化、交易所前缀处理。"""

from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

PRICE_COLUMNS = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pct_chg",
    "涨跌额": "change",
    "换手率": "turnover",
}

STATEMENT_NAMES = ("资产负债表", "利润表", "现金流量表")


def exchange_prefix(code: str) -> str:
    """把 6 位代码转成新浪接口需要的带交易所前缀代码。"""
    if code.startswith(("6", "9")):
        return f"sh{code}"
    if code.startswith(("0", "2", "3")):
        return f"sz{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    raise ValueError(f"无法判断交易所：{code}")


@dataclass
class AkshareClient:
    """只负责取数与字段规范化，不做任何因子计算。"""

    retries: int = 3
    retry_wait: float = 1.5
    timeout: float = 30.0

    def __post_init__(self) -> None:
        # AKShare 内部多数请求未显式设置 timeout，这里用全局 socket 超时兜底，
        # 避免网络异常时进程无限挂起。
        socket.setdefaulttimeout(self.timeout)

    def _call(self, func, **kwargs) -> pd.DataFrame:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                frame = func(**kwargs)
                if frame is None or len(frame) == 0:
                    raise ValueError("接口返回空数据")
                return frame
            except Exception as exc:  # AKShare 内部异常类型不稳定，统一重试
                last_error = exc
                logger.warning("%s 第 %d 次失败：%s", func.__name__, attempt, exc)
                if attempt < self.retries:
                    time.sleep(self.retry_wait * attempt)
        raise RuntimeError(f"{func.__name__} 取数失败：{last_error}") from last_error

    def index_constituents(self, index_code: str) -> pd.DataFrame:
        frame = self._call(ak.index_stock_cons_csindex, symbol=index_code)
        result = pd.DataFrame(
            {
                "code": frame["成分券代码"].astype(str).str.zfill(6),
                "name": frame["成分券名称"].astype(str),
                "exchange": frame["交易所"].astype(str),
            }
        )
        return result.drop_duplicates(subset="code").reset_index(drop=True)

    def daily_bars(self, code: str, start_date: str, end_date: str, adjust: str) -> pd.DataFrame:
        """优先使用新浪日线（含流通股本），失败时回退东方财富。"""
        if not end_date:
            end_date = pd.Timestamp.today().strftime("%Y-%m-%d")
        if not start_date:
            start_date = "1990-01-01"
        try:
            frame = self._call(
                ak.stock_zh_a_daily,
                symbol=exchange_prefix(code),
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            )
            frame = frame.rename(
                columns={"date": "date", "outstanding_share": "float_shares"}
            )
            frame["date"] = pd.to_datetime(frame["date"])
            # 新浪换手率为小数（0.004=0.4%），统一换算成百分数
            frame["turnover"] = pd.to_numeric(frame["turnover"], errors="coerce") * 100
        except Exception as exc:
            logger.warning("%s 新浪日线失败，回退东方财富：%s", code, exc)
            frame = self._call(
                ak.stock_zh_a_hist,
                symbol=code,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust=adjust,
            )
            frame = frame.rename(columns=PRICE_COLUMNS)
            frame["date"] = pd.to_datetime(frame["date"])
            if "float_shares" not in frame.columns:
                frame["float_shares"] = pd.NA

        for column in ("open", "high", "low", "close", "volume", "amount"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if "float_shares" in frame.columns:
            frame["float_shares"] = pd.to_numeric(frame["float_shares"], errors="coerce")
        else:
            frame["float_shares"] = pd.NA
        frame["pct_chg"] = frame["close"].pct_change() * 100
        frame["amplitude"] = (frame["high"] - frame["low"]) / frame["close"].shift(1) * 100

        keep = [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "turnover",
            "pct_chg",
            "amplitude",
            "float_shares",
        ]
        return frame[keep].sort_values("date").reset_index(drop=True)

    def statements(self, code: str) -> dict[str, pd.DataFrame]:
        prefixed = exchange_prefix(code)
        return {
            name: self._call(ak.stock_financial_report_sina, stock=prefixed, symbol=name)
            for name in STATEMENT_NAMES
        }

    def index_bars(self, index_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        prefix = "sh" if index_code.startswith(("0", "9")) else "sz"
        frame = self._call(ak.stock_zh_index_daily, symbol=f"{prefix}{index_code}")
        frame = frame.rename(columns={"date": "date"})
        frame["date"] = pd.to_datetime(frame["date"])
        frame = frame.sort_values("date").reset_index(drop=True)
        if start_date:
            frame = frame[frame["date"] >= pd.Timestamp(start_date)]
        if end_date:
            frame = frame[frame["date"] <= pd.Timestamp(end_date)]
        if frame.empty:
            raise ValueError(f"指数 {index_code} 在指定区间无数据")
        return frame
