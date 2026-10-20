"""量价与技术类因子实现。

每个函数接收 FactorContext，返回「日期 × 股票」的因子值 DataFrame。
公式来源：聚宽因子库 algorithmIntro 文本，注释中标出与原文口径的差异。
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from . import indicators as ind
from .context import FactorContext

PRICE_FACTORS: dict[str, Callable[[FactorContext], pd.DataFrame]] = {}


def factor(name: str):
    def decorator(func: Callable[[FactorContext], pd.DataFrame]):
        PRICE_FACTORS[name] = func
        return func

    return decorator


def _rolling_last_rank(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    """当前值在过去 window 个值中由大到小的位置（1 为最大）。"""
    values = frame.to_numpy(dtype=float)
    length, width = values.shape
    result = np.full((length, width), np.nan)
    if length < window:
        return pd.DataFrame(result, index=frame.index, columns=frame.columns)
    windows = np.lib.stride_tricks.sliding_window_view(values, window, axis=0)
    last = windows[:, :, -1:]
    result[window - 1 :, :] = (windows > last).sum(axis=-1) + 1
    return pd.DataFrame(result, index=frame.index, columns=frame.columns)


def _aroon(frame: pd.DataFrame, window: int, mode: str) -> pd.DataFrame:
    values = frame.to_numpy(dtype=float)
    length, width = values.shape
    result = np.full((length, width), np.nan)
    if length < window:
        return pd.DataFrame(result, index=frame.index, columns=frame.columns)
    windows = np.lib.stride_tricks.sliding_window_view(values, window, axis=0)
    if mode == "max":
        position = np.nanargmax(np.where(np.isfinite(windows), windows, -np.inf), axis=-1)
    else:
        position = np.nanargmin(np.where(np.isfinite(windows), windows, np.inf), axis=-1)
    days_since = window - 1 - position
    result[window - 1 :, :] = (window - days_since) / window * 100
    return pd.DataFrame(result, index=frame.index, columns=frame.columns)


# ---------------------------------------------------------------- 量能 / 换手


@factor("PSY")
def psy(ctx: FactorContext) -> pd.DataFrame:
    """心理线：12 日内上涨天数占比。

    原文写「连续上涨的天数」，业界 PSY 为窗口内上涨天数，此处按后者实现。
    """
    return (ctx.returns > 0).rolling(12, min_periods=12).sum() / 12 * 100


@factor("VROC6")
def vroc6(ctx: FactorContext) -> pd.DataFrame:
    return (ctx.volume / ctx.volume.shift(6) - 1) * 100


@factor("VROC12")
def vroc12(ctx: FactorContext) -> pd.DataFrame:
    return (ctx.volume / ctx.volume.shift(12) - 1) * 100


@factor("TVMA6")
def tvma6(ctx: FactorContext) -> pd.DataFrame:
    return ctx.amount.rolling(6, min_periods=6).mean()


@factor("TVMA20")
def tvma20(ctx: FactorContext) -> pd.DataFrame:
    return ctx.amount.rolling(20, min_periods=20).mean()


@factor("VEMA5")
def vema5(ctx: FactorContext) -> pd.DataFrame:
    """原文公式为空，按成交量的 5 日指数移动平均实现。"""
    return ind.ema(ctx.volume, 5)


@factor("VEMA10")
def vema10(ctx: FactorContext) -> pd.DataFrame:
    return ind.ema(ctx.volume, 10)


@factor("VEMA12")
def vema12(ctx: FactorContext) -> pd.DataFrame:
    return ind.ema(ctx.volume, 12)


@factor("VEMA26")
def vema26(ctx: FactorContext) -> pd.DataFrame:
    return ind.ema(ctx.volume, 26)


@factor("VOL5")
def vol5(ctx: FactorContext) -> pd.DataFrame:
    return ctx.turnover.rolling(5, min_periods=5).mean()


@factor("VOL10")
def vol10(ctx: FactorContext) -> pd.DataFrame:
    return ctx.turnover.rolling(10, min_periods=10).mean()


@factor("VOL20")
def vol20(ctx: FactorContext) -> pd.DataFrame:
    return ctx.turnover.rolling(20, min_periods=20).mean()


@factor("VOL60")
def vol60(ctx: FactorContext) -> pd.DataFrame:
    return ctx.turnover.rolling(60, min_periods=60).mean()


@factor("VOL120")
def vol120(ctx: FactorContext) -> pd.DataFrame:
    return ctx.turnover.rolling(120, min_periods=120).mean()


@factor("VOL240")
def vol240(ctx: FactorContext) -> pd.DataFrame:
    return ctx.turnover.rolling(240, min_periods=240).mean()


@factor("DAVOL5")
def davol5(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(
        ctx.turnover.rolling(5, min_periods=5).mean(),
        ctx.turnover.rolling(120, min_periods=120).mean(),
    )


@factor("DAVOL10")
def davol10(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(
        ctx.turnover.rolling(10, min_periods=10).mean(),
        ctx.turnover.rolling(120, min_periods=120).mean(),
    )


@factor("DAVOL20")
def davol20(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(
        ctx.turnover.rolling(20, min_periods=20).mean(),
        ctx.turnover.rolling(120, min_periods=120).mean(),
    )


@factor("VSTD10")
def vstd10(ctx: FactorContext) -> pd.DataFrame:
    """原文「去标准差」为笔误，按成交量 10 日标准差实现。"""
    return ind.rolling_std(ctx.volume, 10)


@factor("VSTD20")
def vstd20(ctx: FactorContext) -> pd.DataFrame:
    return ind.rolling_std(ctx.volume, 20)


@factor("TVSTD6")
def tvstd6(ctx: FactorContext) -> pd.DataFrame:
    return ind.rolling_std(ctx.amount, 6)


@factor("TVSTD20")
def tvstd20(ctx: FactorContext) -> pd.DataFrame:
    return ind.rolling_std(ctx.amount, 20)


@factor("VR")
def vr(ctx: FactorContext) -> pd.DataFrame:
    window = 26
    change = ctx.close.diff()
    up = ctx.volume.where(change > 0, 0.0).rolling(window, min_periods=window).sum()
    down = ctx.volume.where(change < 0, 0.0).rolling(window, min_periods=window).sum()
    flat = ctx.volume.where(change == 0, 0.0).rolling(window, min_periods=window).sum()
    return ind.safe_div(up + 0.5 * flat, down + 0.5 * flat) * 100


@factor("BR")
def br(ctx: FactorContext) -> pd.DataFrame:
    window = 26
    prev_close = ctx.close.shift(1)
    up = (ctx.high - prev_close).clip(lower=0).rolling(window, min_periods=window).sum()
    down = (prev_close - ctx.low).clip(lower=0).rolling(window, min_periods=window).sum()
    return ind.safe_div(up, down) * 100


@factor("AR")
def ar(ctx: FactorContext) -> pd.DataFrame:
    window = 26
    up = (ctx.high - ctx.open).clip(lower=0).rolling(window, min_periods=window).sum()
    down = (ctx.open - ctx.low).clip(lower=0).rolling(window, min_periods=window).sum()
    return ind.safe_div(up, down) * 100


@factor("ARBR")
def arbr(ctx: FactorContext) -> pd.DataFrame:
    return PRICE_FACTORS["AR"](ctx) - PRICE_FACTORS["BR"](ctx)


@factor("WVAD")
def wvad(ctx: FactorContext) -> pd.DataFrame:
    spread = ind.safe_div(ctx.close - ctx.open, ctx.high - ctx.low)
    daily = spread * ctx.volume
    return daily.rolling(6, min_periods=6).sum()


@factor("MAWVAD")
def mawvad(ctx: FactorContext) -> pd.DataFrame:
    return PRICE_FACTORS["WVAD"](ctx).rolling(6, min_periods=6).mean()


@factor("VDIFF")
def vdiff(ctx: FactorContext) -> pd.DataFrame:
    return ind.ema(ctx.volume, 12) - ind.ema(ctx.volume, 26)


@factor("VDEA")
def vdea(ctx: FactorContext) -> pd.DataFrame:
    return ind.ema(PRICE_FACTORS["VDIFF"](ctx), 9)


@factor("VMACD")
def vmacd(ctx: FactorContext) -> pd.DataFrame:
    return PRICE_FACTORS["VDIFF"](ctx) - PRICE_FACTORS["VDEA"](ctx)


@factor("VOSC")
def vosc(ctx: FactorContext) -> pd.DataFrame:
    fast = ind.ema(ctx.volume, 12)
    slow = ind.ema(ctx.volume, 26)
    return ind.safe_div(fast - slow, fast) * 100


@factor("turnover_volatility")
def turnover_volatility(ctx: FactorContext) -> pd.DataFrame:
    return ind.rolling_std(ctx.turnover, 20)


@factor("share_turnover_monthly")
def share_turnover_monthly(ctx: FactorContext) -> pd.DataFrame:
    return np.log(ctx.turnover.rolling(21, min_periods=21).sum().replace(0, np.nan))


@factor("average_share_turnover_quarterly")
def average_share_turnover_quarterly(ctx: FactorContext) -> pd.DataFrame:
    return np.log(ctx.turnover.rolling(63, min_periods=63).sum().replace(0, np.nan) / 3)


@factor("average_share_turnover_annual")
def average_share_turnover_annual(ctx: FactorContext) -> pd.DataFrame:
    return np.log(ctx.turnover.rolling(252, min_periods=252).sum().replace(0, np.nan) / 12)


# ---------------------------------------------------------------- 波动 / 分布


@factor("Variance20")
def variance20(ctx: FactorContext) -> pd.DataFrame:
    return ctx.returns.rolling(20, min_periods=20).var(ddof=0)


@factor("Variance60")
def variance60(ctx: FactorContext) -> pd.DataFrame:
    return ctx.returns.rolling(60, min_periods=60).var(ddof=0)


@factor("Variance120")
def variance120(ctx: FactorContext) -> pd.DataFrame:
    return ctx.returns.rolling(120, min_periods=120).var(ddof=0)


@factor("Skewness20")
def skewness20(ctx: FactorContext) -> pd.DataFrame:
    return ctx.returns.rolling(20, min_periods=20).skew()


@factor("Skewness60")
def skewness60(ctx: FactorContext) -> pd.DataFrame:
    return ctx.returns.rolling(60, min_periods=60).skew()


@factor("Skewness120")
def skewness120(ctx: FactorContext) -> pd.DataFrame:
    return ctx.returns.rolling(120, min_periods=120).skew()


@factor("Kurtosis20")
def kurtosis20(ctx: FactorContext) -> pd.DataFrame:
    """pandas 的 kurt 为超额峰度，与聚宽口径一致。"""
    return ctx.returns.rolling(20, min_periods=20).kurt()


@factor("Kurtosis60")
def kurtosis60(ctx: FactorContext) -> pd.DataFrame:
    return ctx.returns.rolling(60, min_periods=60).kurt()


@factor("Kurtosis120")
def kurtosis120(ctx: FactorContext) -> pd.DataFrame:
    return ctx.returns.rolling(120, min_periods=120).kurt()


@factor("sharpe_ratio_20")
def sharpe_ratio_20(ctx: FactorContext) -> pd.DataFrame:
    return _sharpe(ctx, 20)


@factor("sharpe_ratio_60")
def sharpe_ratio_60(ctx: FactorContext) -> pd.DataFrame:
    return _sharpe(ctx, 60)


@factor("sharpe_ratio_120")
def sharpe_ratio_120(ctx: FactorContext) -> pd.DataFrame:
    return _sharpe(ctx, 120)


def _sharpe(ctx: FactorContext, window: int) -> pd.DataFrame:
    """(年化收益 - 无风险利率) / 年化波动率，无风险利率取 4%。"""
    mean = ctx.returns.rolling(window, min_periods=window).mean() * 252
    sigma = ctx.returns.rolling(window, min_periods=window).std(ddof=0) * np.sqrt(252)
    return ind.safe_div(mean - 0.04, sigma)


@factor("daily_standard_deviation")
def daily_standard_deviation(ctx: FactorContext) -> pd.DataFrame:
    return ind.weighted_std(ctx.returns, 252, 42)


@factor("cumulative_range")
def cumulative_range(ctx: FactorContext) -> pd.DataFrame:
    """12 个月内的累计对数收益路径极差：ln(1+Zmax) − ln(1+Zmin)。"""
    monthly = ctx.close.resample("ME").last()
    monthly_returns = monthly.pct_change()
    log_growth = np.log1p(monthly_returns)
    values = log_growth.to_numpy(dtype=float)
    result = np.full_like(values, np.nan)
    window = 12
    if values.shape[0] >= window:
        windows = np.lib.stride_tricks.sliding_window_view(values, window, axis=0)
        cumulative = np.nancumsum(windows, axis=-1)
        paths = np.where(np.isfinite(windows), cumulative, np.nan)
        z_max = np.nanmax(paths, axis=-1)
        z_min = np.nanmin(paths, axis=-1)
        block = np.log1p(z_max) - np.log1p(z_min)
        block = np.where(np.isfinite(windows).sum(axis=-1) == window, block, np.nan)
        result[window - 1 :, :] = block
    series = pd.DataFrame(result, index=monthly.index, columns=monthly.columns)
    return series.reindex(ctx.dates, method="ffill")


@factor("ATR6")
def atr6(ctx: FactorContext) -> pd.DataFrame:
    return ind.true_range(ctx.high, ctx.low, ctx.close).rolling(6, min_periods=6).mean()


@factor("ATR14")
def atr14(ctx: FactorContext) -> pd.DataFrame:
    return ind.true_range(ctx.high, ctx.low, ctx.close).rolling(14, min_periods=14).mean()


# ---------------------------------------------------------------- 动量 / 反转


@factor("momentum")
def momentum(ctx: FactorContext) -> pd.DataFrame:
    """相对强弱：滞后 21 日、504 日窗口、半衰期 126 天的加权对数收益。"""
    log_returns = np.log1p(ctx.returns)
    return ind.weighted_mean(log_returns.shift(21), 504, 126)


@factor("relative_strength")
def relative_strength(ctx: FactorContext) -> pd.DataFrame:
    return PRICE_FACTORS["momentum"](ctx)


@factor("Price1M")
def price1m(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.close, ctx.close.rolling(21, min_periods=21).mean()) - 1


@factor("Price3M")
def price3m(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.close, ctx.close.rolling(61, min_periods=61).mean()) - 1


@factor("Price1Y")
def price1y(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.close, ctx.close.rolling(250, min_periods=250).mean()) - 1


@factor("Rank1M")
def rank1m(ctx: FactorContext) -> pd.DataFrame:
    """1 - 20 日收益的横截面排名百分位。"""
    return 1 - ctx.close.pct_change(20).rank(axis=1, pct=True)


@factor("fifty_two_week_close_rank")
def fifty_two_week_close_rank(ctx: FactorContext) -> pd.DataFrame:
    return _rolling_last_rank(ctx.close, 250) / 250


# ---------------------------------------------------------------- 均线 / 通道


@factor("MAC5")
def mac5(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ind.sma(ctx.close, 5), ctx.close)


@factor("MAC10")
def mac10(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ind.sma(ctx.close, 10), ctx.close)


@factor("MAC20")
def mac20(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ind.sma(ctx.close, 20), ctx.close)


@factor("MAC60")
def mac60(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ind.sma(ctx.close, 60), ctx.close)


@factor("MAC120")
def mac120(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ind.sma(ctx.close, 120), ctx.close)


@factor("EMA5")
def ema5(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ind.ema(ctx.close, 5), ctx.close)


@factor("EMAC10")
def emac10(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ind.ema(ctx.close, 10), ctx.close)


@factor("EMAC12")
def emac12(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ind.ema(ctx.close, 12), ctx.close)


@factor("EMAC20")
def emac20(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ind.ema(ctx.close, 20), ctx.close)


@factor("EMAC26")
def emac26(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ind.ema(ctx.close, 26), ctx.close)


@factor("EMAC120")
def emac120(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ind.ema(ctx.close, 120), ctx.close)


@factor("BBIC")
def bbic(ctx: FactorContext) -> pd.DataFrame:
    bbi = (
        ind.sma(ctx.close, 3)
        + ind.sma(ctx.close, 6)
        + ind.sma(ctx.close, 12)
        + ind.sma(ctx.close, 24)
    ) / 4
    return ind.safe_div(bbi, ctx.close)


@factor("MACDC")
def macdc(ctx: FactorContext) -> pd.DataFrame:
    """MACD 柱（2×(DIF−DEA)）除以收盘价。"""
    dif = ind.ema(ctx.close, 12) - ind.ema(ctx.close, 26)
    dea = ind.ema(dif, 9)
    return ind.safe_div(2 * (dif - dea), ctx.close)


@factor("boll_up")
def boll_up(ctx: FactorContext) -> pd.DataFrame:
    middle = ind.sma(ctx.close, 20)
    band = 2 * ind.rolling_std(ctx.close, 20)
    return ind.safe_div(middle + band, ctx.close)


@factor("boll_down")
def boll_down(ctx: FactorContext) -> pd.DataFrame:
    middle = ind.sma(ctx.close, 20)
    band = 2 * ind.rolling_std(ctx.close, 20)
    return ind.safe_div(middle - band, ctx.close)


# ---------------------------------------------------------------- 摆动指标


@factor("BIAS5")
def bias5(ctx: FactorContext) -> pd.DataFrame:
    return _bias(ctx, 5)


@factor("BIAS10")
def bias10(ctx: FactorContext) -> pd.DataFrame:
    return _bias(ctx, 10)


@factor("BIAS20")
def bias20(ctx: FactorContext) -> pd.DataFrame:
    return _bias(ctx, 20)


@factor("BIAS60")
def bias60(ctx: FactorContext) -> pd.DataFrame:
    return _bias(ctx, 60)


def _bias(ctx: FactorContext, window: int) -> pd.DataFrame:
    mean = ind.sma(ctx.close, window)
    return ind.safe_div(ctx.close - mean, mean) * 100


@factor("ROC6")
def roc6(ctx: FactorContext) -> pd.DataFrame:
    return _roc(ctx, 6)


@factor("ROC12")
def roc12(ctx: FactorContext) -> pd.DataFrame:
    return _roc(ctx, 12)


@factor("ROC20")
def roc20(ctx: FactorContext) -> pd.DataFrame:
    return _roc(ctx, 20)


@factor("ROC60")
def roc60(ctx: FactorContext) -> pd.DataFrame:
    """原文写成「20天前收盘价 / 60天前收盘价」，按标准 ROC(60) 实现。"""
    return _roc(ctx, 60)


@factor("ROC120")
def roc120(ctx: FactorContext) -> pd.DataFrame:
    return _roc(ctx, 120)


def _roc(ctx: FactorContext, window: int) -> pd.DataFrame:
    past = ctx.close.shift(window)
    return ind.safe_div(ctx.close - past, past) * 100


@factor("CCI10")
def cci10(ctx: FactorContext) -> pd.DataFrame:
    return _cci(ctx, 10)


@factor("CCI15")
def cci15(ctx: FactorContext) -> pd.DataFrame:
    return _cci(ctx, 15)


@factor("CCI20")
def cci20(ctx: FactorContext) -> pd.DataFrame:
    return _cci(ctx, 20)


@factor("CCI88")
def cci88(ctx: FactorContext) -> pd.DataFrame:
    return _cci(ctx, 88)


def _cci(ctx: FactorContext, window: int) -> pd.DataFrame:
    typical = (ctx.high + ctx.low + ctx.close) / 3
    mean = typical.rolling(window, min_periods=window).mean()
    deviation = ind.avedev(typical, window)
    return ind.safe_div(typical - mean, 0.015 * deviation)


@factor("PLRC6")
def plrc6(ctx: FactorContext) -> pd.DataFrame:
    return ind.rolling_regression_beta(ctx.close, 6)


@factor("PLRC12")
def plrc12(ctx: FactorContext) -> pd.DataFrame:
    return ind.rolling_regression_beta(ctx.close, 12)


@factor("PLRC24")
def plrc24(ctx: FactorContext) -> pd.DataFrame:
    return ind.rolling_regression_beta(ctx.close, 24)


@factor("TRIX5")
def trix5(ctx: FactorContext) -> pd.DataFrame:
    """原文为 EMA5→EMA10→EMA5 的三重平滑，按原文顺序实现。"""
    first = ind.ema(ctx.close, 5)
    second = ind.ema(first, 10)
    third = ind.ema(second, 5)
    return ind.safe_div(third - third.shift(1), third.shift(1)) * 100


@factor("TRIX10")
def trix10(ctx: FactorContext) -> pd.DataFrame:
    first = ind.ema(ctx.close, 10)
    second = ind.ema(first, 10)
    third = ind.ema(second, 10)
    return ind.safe_div(third - third.shift(1), third.shift(1)) * 100


@factor("MASS")
def mass(ctx: FactorContext) -> pd.DataFrame:
    """梅斯线：EMA9(H-L)/EMA9(EMA9(H-L)) 的 25 日累加，再取 6 日均值。"""
    amplitude = ctx.high - ctx.low
    first = ind.ema(amplitude, 9)
    second = ind.ema(first, 9)
    ratio = ind.safe_div(first, second)
    mass_line = ratio.rolling(25, min_periods=25).sum()
    return mass_line.rolling(6, min_periods=6).mean()


@factor("MFI14")
def mfi14(ctx: FactorContext) -> pd.DataFrame:
    typical = (ctx.high + ctx.low + ctx.close) / 3
    flow = typical * ctx.volume
    change = typical.diff()
    positive = flow.where(change > 0, 0.0).rolling(14, min_periods=14).sum()
    negative = flow.where(change < 0, 0.0).rolling(14, min_periods=14).sum()
    ratio = ind.safe_div(positive, negative)
    return 100 - 100 / (1 + ratio)


@factor("CR20")
def cr20(ctx: FactorContext) -> pd.DataFrame:
    middle = (ctx.high.shift(1) + ctx.low.shift(1)) / 2
    up = (ctx.high - middle).clip(lower=0).rolling(20, min_periods=20).sum()
    down = (middle - ctx.low).clip(lower=0).rolling(20, min_periods=20).sum()
    return ind.safe_div(up, down) * 100


# ---------------------------------------------------------------- 价量 / 力道


@factor("single_day_VPT")
def single_day_vpt(ctx: FactorContext) -> pd.DataFrame:
    return ctx.returns * ctx.volume


@factor("single_day_VPT_6")
def single_day_vpt_6(ctx: FactorContext) -> pd.DataFrame:
    return PRICE_FACTORS["single_day_VPT"](ctx).rolling(6, min_periods=6).mean()


@factor("single_day_VPT_12")
def single_day_vpt_12(ctx: FactorContext) -> pd.DataFrame:
    return PRICE_FACTORS["single_day_VPT"](ctx).rolling(12, min_periods=12).mean()


@factor("Volume1M")
def volume1m(ctx: FactorContext) -> pd.DataFrame:
    ratio = ind.safe_div(ctx.volume, ctx.volume.rolling(20, min_periods=20).mean())
    return ratio * ctx.returns.rolling(20, min_periods=20).mean()


@factor("money_flow_20")
def money_flow_20(ctx: FactorContext) -> pd.DataFrame:
    typical = (ctx.high + ctx.low + ctx.close) / 3
    return (typical * ctx.volume).rolling(20, min_periods=20).sum()


@factor("bull_power")
def bull_power(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.high - ind.ema(ctx.close, 13), ctx.close)


@factor("bear_power")
def bear_power(ctx: FactorContext) -> pd.DataFrame:
    return ind.safe_div(ctx.low - ind.ema(ctx.close, 13), ctx.close)


@factor("arron_up_25")
def arron_up_25(ctx: FactorContext) -> pd.DataFrame:
    return _aroon(ctx.high, 25, "max")


@factor("arron_down_25")
def arron_down_25(ctx: FactorContext) -> pd.DataFrame:
    return _aroon(ctx.low, 25, "min")


# ---------------------------------------------------------------- 价格 / 规模


@factor("price_no_fq")
def price_no_fq(ctx: FactorContext) -> pd.DataFrame:
    return ctx.close_raw


@factor("market_cap")
def market_cap(ctx: FactorContext) -> pd.DataFrame:
    return ctx.market_cap


@factor("natural_log_of_market_cap")
def natural_log_of_market_cap(ctx: FactorContext) -> pd.DataFrame:
    return np.log(ctx.market_cap.where(ctx.market_cap > 0))


@factor("circulating_market_cap")
def circulating_market_cap(ctx: FactorContext) -> pd.DataFrame:
    return ctx.close * ctx.float_shares


# ---------------------------------------------------------------- 风险因子


@factor("beta")
def beta(ctx: FactorContext) -> pd.DataFrame:
    # 停牌日收益缺失按 0 处理，保证回归窗口不中断
    return ind.rolling_weighted_moments(
        ctx.returns.fillna(0.0), ctx.market_returns_panel, 252, 63
    )["beta"]


@factor("raw_beta")
def raw_beta(ctx: FactorContext) -> pd.DataFrame:
    return PRICE_FACTORS["beta"](ctx)


@factor("market_beta")
def market_beta(ctx: FactorContext) -> pd.DataFrame:
    return PRICE_FACTORS["beta"](ctx)


@factor("historical_sigma")
def historical_sigma(ctx: FactorContext) -> pd.DataFrame:
    return ind.rolling_weighted_moments(
        ctx.returns.fillna(0.0), ctx.market_returns_panel, 252, 63
    )["resid_std"]
