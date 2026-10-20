"""因子计算上下文：把行情面板与财务面板组合成统一取值入口。"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..data.financials import FinancialPanel
from ..data.prices import PricePanel
from . import indicators as ind


@dataclass
class FactorContext:
    price: PricePanel
    financial: FinancialPanel
    market_close: pd.Series
    _cache: dict[str, pd.DataFrame] = field(default_factory=dict, repr=False)

    @property
    def dates(self) -> pd.DatetimeIndex:
        return self.price.dates

    @property
    def codes(self) -> list[str]:
        return self.price.codes

    def px(self, name: str) -> pd.DataFrame:
        return self.price[name].reindex(columns=self.codes)

    @property
    def open(self) -> pd.DataFrame:
        return self.px("open")

    @property
    def high(self) -> pd.DataFrame:
        return self.px("high")

    @property
    def low(self) -> pd.DataFrame:
        return self.px("low")

    @property
    def close(self) -> pd.DataFrame:
        return self.px("close")

    @property
    def close_raw(self) -> pd.DataFrame:
        return self.price.close_raw.reindex(columns=self.codes)

    @property
    def volume(self) -> pd.DataFrame:
        return self.px("volume")

    @property
    def amount(self) -> pd.DataFrame:
        return self.px("amount")

    @property
    def turnover(self) -> pd.DataFrame:
        return self.px("turnover")

    @property
    def float_shares(self) -> pd.DataFrame:
        return self.px("float_shares").ffill()

    @property
    def returns(self) -> pd.DataFrame:
        if "returns" not in self._cache:
            self._cache["returns"] = ind.returns(self.close)
        return self._cache["returns"]

    @property
    def market_returns(self) -> pd.Series:
        series = self.market_close.reindex(self.dates).ffill()
        return series.pct_change()

    @property
    def market_returns_panel(self) -> pd.DataFrame:
        """市场收益按股票列广播，便于逐列回归。"""
        if "market_panel" not in self._cache:
            series = self.market_returns.fillna(0.0)
            self._cache["market_panel"] = pd.DataFrame(
                np.repeat(series.to_numpy()[:, None], len(self.codes), axis=1),
                index=self.dates,
                columns=self.codes,
            )
        return self._cache["market_panel"]

    def ttm(self, field: str, lag_q: int = 0) -> pd.DataFrame:
        return self.financial.ttm(field, lag_q)

    def point(self, field: str, lag_q: int = 0) -> pd.DataFrame:
        return self.financial.point(field, lag_q)

    def avg4(self, field: str, lag_q: int = 0) -> pd.DataFrame:
        return self.financial.avg4(field, lag_q)

    def avg4_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        """对派生存量指标求四季均值。

        日频面板本身是按公告日阶梯更新的，这里按季末采样后再滚动四季平均，
        属于工程近似，因子说明中已标注。
        """
        quarterly = frame.resample("QE").last()
        averaged = quarterly.rolling(4, min_periods=2).mean()
        return averaged.reindex(self.dates, method="ffill")

    @property
    def shares(self) -> pd.DataFrame:
        return self.financial.shares.reindex(columns=self.codes)

    @property
    def market_cap(self) -> pd.DataFrame:
        if "market_cap" not in self._cache:
            self._cache["market_cap"] = self.close * self.shares
        return self._cache["market_cap"]

    @property
    def total_assets(self) -> pd.DataFrame:
        return self.point("total_assets")

    def growth(self, field: str) -> pd.DataFrame:
        """TTM 同比增速：(今年TTM / 去年TTM) - 1。"""
        current = self.ttm(field)
        previous = self.ttm(field, lag_q=4)
        return ind.safe_div(current, previous) - 1
