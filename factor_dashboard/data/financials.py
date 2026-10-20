"""三大报表的规范化、季度化、TTM 与按公告日对齐。"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .client import AkshareClient

logger = logging.getLogger(__name__)

BALANCE_MAP = {
    "货币资金": "cash",
    "交易性金融资产": "financial_assets_trading",
    "应收票据": "notes_receivable",
    "应收账款": "accounts_receivable",
    "预付款项": "prepayments",
    "其他应收款": "other_receivables",
    "存货": "inventory",
    "流动资产合计": "current_assets",
    "固定资产净额": "fixed_assets",
    "在建工程": "construction_in_progress",
    "工程物资": "construction_materials",
    "无形资产": "intangible_assets",
    "开发支出": "development_expense",
    "商誉": "goodwill",
    "长期股权投资": "long_term_equity_investment",
    "可供出售金融资产": "available_for_sale",
    "非流动资产合计": "non_current_assets",
    "资产总计": "total_assets",
    "短期借款": "short_term_borrowings",
    "应付票据": "notes_payable",
    "应付账款": "accounts_payable",
    "预收款项": "advance_receipts",
    "合同负债": "contract_liabilities",
    "应付职工薪酬": "payroll_payable",
    "应交税费": "tax_payable",
    "应付利息": "interest_payable",
    "其他应付款": "other_payables",
    "一年内的递延收益": "deferred_income_current",
    "其他流动负债": "other_current_liabilities",
    "流动负债合计": "current_liabilities",
    "长期借款": "long_term_borrowings",
    "应付债券": "bonds_payable",
    "长期递延收益": "deferred_income_noncurrent",
    "非流动负债合计": "non_current_liabilities",
    "负债合计": "total_liabilities",
    "实收资本(或股本)": "share_capital",
    "资本公积": "capital_reserve",
    "盈余公积": "surplus_reserve",
    "未分配利润": "retained_profit",
    "归属于母公司股东权益合计": "equity_parent",
    "少数股东权益": "minority_equity",
    "所有者权益(或股东权益)合计": "total_equity",
}

INCOME_MAP = {
    "营业总收入": "total_revenue",
    "营业收入": "revenue",
    "营业总成本": "total_cost",
    "营业成本": "cost",
    "营业税金及附加": "tax_surcharge",
    "销售费用": "selling_expense",
    "管理费用": "admin_expense",
    "研发费用": "rd_expense",
    "财务费用": "financial_expense",
    "利息费用": "interest_expense",
    "投资收益": "investment_income",
    "对联营企业和合营企业的投资收益": "associates_income",
    "公允价值变动收益": "fair_value_change",
    "资产减值损失": "asset_impairment",
    "信用减值损失": "credit_impairment",
    "营业利润": "operating_profit",
    "营业外收入": "non_operating_income",
    "营业外支出": "non_operating_expense",
    "利润总额": "total_profit",
    "所得税费用": "income_tax",
    "净利润": "net_profit",
    "归属于母公司所有者的净利润": "net_profit_parent",
    "基本每股收益": "eps",
}

CASHFLOW_MAP = {
    "销售商品、提供劳务收到的现金": "cash_from_sales",
    "经营活动产生的现金流量净额": "cfo",
    "投资活动产生的现金流量净额": "cfi",
    "筹资活动产生的现金流量净额": "cff",
    "购建固定资产、无形资产和其他长期资产所支付的现金": "capex",
    "分配股利、利润或偿付利息所支付的现金": "dividend_interest_paid",
    "吸收投资收到的现金": "equity_raised",
    "取得借款收到的现金": "borrowings_received",
    "发行债券收到的现金": "bonds_issued",
    "现金及现金等价物净增加额": "net_cash_increase",
    "期末现金及现金等价物余额": "cash_end",
}

FLOW_FIELDS = set(INCOME_MAP.values()) | set(CASHFLOW_MAP.values())
STOCK_FIELDS = set(BALANCE_MAP.values())

# 报表缺失时的保守披露延迟（自然日）
FALLBACK_PUBLICATION_LAG_DAYS = 75


def _normalise_statement(frame: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    working = frame.copy()
    working["报告日"] = pd.to_datetime(working["报告日"].astype(str), format="%Y%m%d", errors="coerce")
    working = working.dropna(subset=["报告日"]).set_index("报告日").sort_index()
    available = {src: dst for src, dst in mapping.items() if src in working.columns}
    result = working[list(available)].rename(columns=available).apply(pd.to_numeric, errors="coerce")
    if "公告日期" in working.columns:
        announce = pd.to_datetime(working["公告日期"], errors="coerce")
        result["announce_date"] = announce
    else:
        result["announce_date"] = pd.NaT
    return result


def _dedupe_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if not frame.columns.duplicated().any():
        return frame
    return frame.loc[:, ~frame.columns.duplicated()]


@dataclass
class FinancialQuarterly:
    """单只股票的季度财务宽表（流量为单季，存量为期末值）。"""

    frame: pd.DataFrame
    announce: pd.Series

    @property
    def fields(self) -> list[str]:
        return [c for c in self.frame.columns if c not in {"announce_date"}]

    def _field(self, field: str) -> pd.Series:
        if field not in self.frame.columns:
            return pd.Series(index=self.frame.index, dtype=float)
        return self.frame[field].astype(float)

    def single_quarter(self, field: str) -> pd.Series:
        return cumulative_to_single_quarter(self._field(field))

    def ttm(self, field: str) -> pd.Series:
        return self.single_quarter(field).rolling(4, min_periods=4).sum()

    def point(self, field: str) -> pd.Series:
        return self._field(field)

    def avg4(self, field: str) -> pd.Series:
        return self._field(field).rolling(4, min_periods=2).mean()

    def shares(self) -> pd.Series:
        """用 归母净利润 / 基本每股收益 反推总股本（近似）。"""
        net = self.single_quarter_cumulative("net_profit_parent")
        eps = self.single_quarter_cumulative("eps")
        if net.empty or eps.empty:
            return pd.Series(index=self.frame.index, dtype=float)
        shares = net / eps.replace(0, np.nan)
        return shares.where(shares > 1e6)

    def single_quarter_cumulative(self, field: str) -> pd.Series:
        return self._field(field)


def cumulative_to_single_quarter(cumulative: pd.Series) -> pd.Series:
    """把年内累计值转为单季值；相邻报告期跨年或缺季度时退化为原值。"""
    if cumulative.empty:
        return cumulative
    index = cumulative.index
    years = index.year
    quarters = index.quarter
    prev_value = cumulative.shift(1)
    same_year = pd.Series(years, index=index).eq(pd.Series(years, index=index).shift(1))
    consecutive = pd.Series(quarters, index=index).sub(
        pd.Series(quarters, index=index).shift(1)
    ).eq(1)
    single = cumulative - prev_value
    result = single.where(same_year & consecutive, cumulative)
    return result


class FinancialRepository:
    def __init__(
        self,
        client: AkshareClient,
        cache_dir: Path,
        max_workers: int,
        max_age_days: int = 7,
    ) -> None:
        self.client = client
        self.cache_dir = cache_dir / "financials"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers
        self.max_age_days = max_age_days

    def _cache_path(self, code: str) -> Path:
        return self.cache_dir / f"{code}.parquet"

    def _cache_is_fresh(self, path: Path) -> bool:
        if not path.exists() or self.max_age_days <= 0:
            return False
        age_days = (time.time() - path.stat().st_mtime) / 86400
        return age_days <= self.max_age_days

    def load_one(self, code: str) -> FinancialQuarterly:
        path = self._cache_path(code)
        if self._cache_is_fresh(path):
            cached = pd.read_parquet(path)
            if not cached.empty:
                cached.index = pd.to_datetime(cached.index)
                announce = cached.pop("announce_date")
                return FinancialQuarterly(frame=cached, announce=announce)

        raw = self.client.statements(code)
        balance = _normalise_statement(raw["资产负债表"], BALANCE_MAP)
        income = _normalise_statement(raw["利润表"], INCOME_MAP)
        cashflow = _normalise_statement(raw["现金流量表"], CASHFLOW_MAP)

        announce = pd.concat(
            [
                balance.pop("announce_date"),
                income.pop("announce_date"),
                cashflow.pop("announce_date"),
            ],
            axis=1,
        ).max(axis=1)

        merged = pd.concat([balance, income, cashflow], axis=1)
        merged = _dedupe_columns(merged)
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        announce = announce.reindex(merged.index)
        fallback = pd.Series(
            merged.index + pd.Timedelta(days=FALLBACK_PUBLICATION_LAG_DAYS), index=merged.index
        )
        announce = announce.fillna(fallback)

        stored = merged.copy()
        stored["announce_date"] = announce
        stored.to_parquet(path)
        return FinancialQuarterly(frame=merged, announce=announce)

    def load(self, codes: list[str]) -> dict[str, FinancialQuarterly]:
        result: dict[str, FinancialQuarterly] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self.load_one, code): code for code in codes}
            for future in as_completed(futures):
                code = futures[future]
                try:
                    result[code] = future.result()
                except Exception as exc:
                    logger.error("财报获取失败 %s：%s", code, exc)
        missing = sorted(set(codes) - set(result))
        if missing:
            logger.warning("以下股票财报缺失：%s", missing)
        return result


class FinancialPanel:
    """按公告日对齐到交易日的财务面板，带计算缓存。"""

    def __init__(self, quarters: dict[str, FinancialQuarterly], dates: pd.DatetimeIndex) -> None:
        self.quarters = quarters
        self.codes = list(quarters)
        self.dates = dates
        self._cache: dict[tuple[str, str, int], pd.DataFrame] = {}

    def _lagged(self, series: pd.Series, lag_q: int) -> pd.Series:
        return series.shift(lag_q) if lag_q else series

    def _align(self, getter, field: str, lag_q: int) -> pd.DataFrame:
        key = (getter, field, lag_q)
        if key in self._cache:
            return self._cache[key]
        columns: list[pd.Series] = []
        for code in self.codes:
            item = self.quarters[code]
            try:
                if getter == "shares":
                    series = item.shares()
                elif field not in item.frame.columns:
                    continue
                elif getter == "point":
                    series = item.point(field)
                elif getter == "avg4":
                    series = item.avg4(field)
                elif getter == "ttm":
                    series = item.ttm(field)
                else:  # pragma: no cover - 防御性分支
                    raise ValueError(f"未知取值方式：{getter}")
            except Exception as exc:
                logger.debug("字段 %s 在 %s 上不可用：%s", field, code, exc)
                continue
            series = self._lagged(series, lag_q)
            series = series.dropna()
            if series.empty:
                continue
            availability = item.announce.reindex(series.index)
            availability = availability.fillna(
                series.index.to_series() + pd.Timedelta(days=FALLBACK_PUBLICATION_LAG_DAYS)
            )
            series.index = pd.DatetimeIndex(availability.values)
            series = series[~series.index.duplicated(keep="last")].sort_index()
            aligned = series.reindex(self.dates, method="ffill")
            aligned.name = code
            columns.append(aligned)
        panel = pd.concat(columns, axis=1) if columns else pd.DataFrame(index=self.dates)
        self._cache[key] = panel
        return panel

    def ttm(self, field: str, lag_q: int = 0) -> pd.DataFrame:
        return self._align("ttm", field, lag_q)

    def point(self, field: str, lag_q: int = 0) -> pd.DataFrame:
        return self._align("point", field, lag_q)

    def avg4(self, field: str, lag_q: int = 0) -> pd.DataFrame:
        return self._align("avg4", field, lag_q)

    @property
    def shares(self) -> pd.DataFrame:
        return self._align("shares", "shares", 0)

    def annual(self, field: str) -> pd.DataFrame:
        """年报口径的年度序列，索引为财年。"""
        columns = {}
        for code in self.codes:
            item = self.quarters[code]
            if field not in item.frame.columns:
                continue
            frame = item.frame[item.frame.index.month == 12]
            columns[code] = frame[field].astype(float)
        if not columns:
            return pd.DataFrame()
        return pd.DataFrame(columns).sort_index()

    def annual_frame(self, field: str) -> pd.DataFrame:
        """年报值（12 月报告期），索引为报告期日期。"""
        columns = {}
        for code in self.codes:
            item = self.quarters[code]
            if field not in item.frame.columns:
                continue
            frame = item.frame[item.frame.index.month == 12]
            columns[code] = frame[field].astype(float)
        if not columns:
            return pd.DataFrame(index=pd.DatetimeIndex([]))
        return pd.DataFrame(columns).sort_index()

    def align_annual(self, frame: pd.DataFrame) -> pd.DataFrame:
        """把年度指标按对应年报的公告日对齐到交易日。"""
        columns: list[pd.Series] = []
        for code in frame.columns:
            item = self.quarters[code]
            series = frame[code].dropna()
            if series.empty:
                continue
            availability = item.announce.reindex(series.index).fillna(
                series.index.to_series() + pd.Timedelta(days=FALLBACK_PUBLICATION_LAG_DAYS)
            )
            series.index = pd.DatetimeIndex(availability.values)
            series = series[~series.index.duplicated(keep="last")].sort_index()
            aligned = series.reindex(self.dates, method="ffill")
            aligned.name = code
            columns.append(aligned)
        if not columns:
            return pd.DataFrame(index=self.dates)
        return pd.concat(columns, axis=1).reindex(columns=list(frame.columns))
