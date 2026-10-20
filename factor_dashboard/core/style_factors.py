"""风格/复合类因子：需要横截面标准化、回归取残差的 Barra 型构造。"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from . import indicators as ind
from .context import FactorContext
from .price_factors import PRICE_FACTORS

STYLE_FACTORS: dict[str, Callable[[FactorContext], pd.DataFrame]] = {}


def factor(name: str):
    def decorator(func: Callable[[FactorContext], pd.DataFrame]):
        STYLE_FACTORS[name] = func
        return func

    return decorator


def _size_factor(ctx: FactorContext) -> pd.DataFrame:
    return np.log(ctx.market_cap.where(ctx.market_cap > 0))


@factor("market_size")
def market_size(ctx: FactorContext) -> pd.DataFrame:
    return _size_factor(ctx)


@factor("non_linear_size")
def non_linear_size(ctx: FactorContext) -> pd.DataFrame:
    """标准化市值的三次方，对标准化市值回归取残差，缩尾后再标准化。"""
    z = ind.cs_zscore(_size_factor(ctx))
    cube = z**3
    residual = ind.cs_residual(cube, z)
    return ind.cs_zscore(ind.cs_winsorize(residual, 3.0))


@factor("cube_of_size")
def cube_of_size(ctx: FactorContext) -> pd.DataFrame:
    return non_linear_size(ctx)


@factor("midcap")
def midcap(ctx: FactorContext) -> pd.DataFrame:
    return non_linear_size(ctx)


@factor("liquidity")
def liquidity(ctx: FactorContext) -> pd.DataFrame:
    monthly = ctx.turnover.rolling(21, min_periods=21).sum()
    quarterly = ctx.turnover.rolling(63, min_periods=63).sum() / 3
    annual = ctx.turnover.rolling(252, min_periods=252).sum() / 12
    raw = 0.35 * monthly + 0.35 * quarterly + 0.3 * annual
    return ind.cs_residual(raw, _size_factor(ctx))


@factor("liquidty")
def liquidty(ctx: FactorContext) -> pd.DataFrame:
    monthly = ctx.turnover.rolling(21, min_periods=21).sum()
    quarterly = ctx.turnover.rolling(63, min_periods=63).sum() / 3
    annual = ctx.turnover.rolling(252, min_periods=252).sum() / 12
    traded_value = np.log(
        ind.safe_div(ctx.amount.rolling(252, min_periods=252).sum(), ctx.market_cap)
    )
    return 0.25 * monthly + 0.25 * quarterly + 0.25 * annual + 0.25 * traded_value


@factor("residual_volatility")
def residual_volatility(ctx: FactorContext) -> pd.DataFrame:
    dastd = PRICE_FACTORS["daily_standard_deviation"](ctx)
    cmra = PRICE_FACTORS["cumulative_range"](ctx)
    hsigma = PRICE_FACTORS["historical_sigma"](ctx)
    raw = 0.74 * dastd + 0.16 * cmra + 0.10 * hsigma
    beta = PRICE_FACTORS["beta"](ctx)
    return ind.cs_residual(raw, beta, _size_factor(ctx))


@factor("resvol")
def resvol(ctx: FactorContext) -> pd.DataFrame:
    dastd = PRICE_FACTORS["daily_standard_deviation"](ctx)
    cmra = PRICE_FACTORS["cumulative_range"](ctx)
    hsigma = PRICE_FACTORS["historical_sigma"](ctx)
    return 0.50 * dastd + 0.42 * hsigma + 0.08 * cmra
