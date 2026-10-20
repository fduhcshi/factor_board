"""技术指标与横截面运算的纯函数集合。

所有函数输入输出均为「日期 × 股票」的 DataFrame（或同形状 ndarray），
不读取配置、不发起网络请求。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def safe_div(numerator: pd.DataFrame, denominator: pd.DataFrame) -> pd.DataFrame:
    """分母为 0 或缺失时返回 NaN，避免 inf 污染因子。"""
    result = numerator / denominator.replace(0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


def sma(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=window).mean()


def ema(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.ewm(span=window, adjust=False, min_periods=window).mean()


def rolling_std(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    return frame.rolling(window, min_periods=window).std(ddof=0)


def returns(close: pd.DataFrame) -> pd.DataFrame:
    return close.pct_change()


def true_range(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    prev_close = close.shift(1)
    stacked = np.maximum.reduce(
        [
            (high - low).to_numpy(dtype=float),
            (high - prev_close).abs().to_numpy(dtype=float),
            (low - prev_close).abs().to_numpy(dtype=float),
        ]
    )
    return pd.DataFrame(stacked, index=close.index, columns=close.columns)


def avedev(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    """平均绝对偏差：窗口内各值与窗口均值的绝对离差均值。"""
    mean = frame.rolling(window, min_periods=window).mean()
    deviation = (frame - mean).abs()
    return deviation.rolling(window, min_periods=window).mean()


def rolling_weighted_moments(
    y: pd.DataFrame, x: pd.DataFrame, window: int, halflife: float
) -> dict[str, pd.DataFrame]:
    """滚动指数加权一元回归，返回 beta / alpha / 残差标准差。

    权重按半衰期衰减：w(age) = 0.5 ** (age / halflife)，最新一期 age=0。
    """
    y_values = y.to_numpy(dtype=float)
    x_values = x.to_numpy(dtype=float)
    length, width = y_values.shape
    if length < window:
        empty = pd.DataFrame(np.nan, index=y.index, columns=y.columns)
        return {"beta": empty.copy(), "alpha": empty.copy(), "resid_std": empty.copy()}

    weights = 0.5 ** (np.arange(window - 1, -1, -1) / halflife)
    weights = weights / weights.sum()

    y_win = np.lib.stride_tricks.sliding_window_view(y_values, window, axis=0)
    x_win = np.lib.stride_tricks.sliding_window_view(x_values, window, axis=0)
    y_mean = (y_win * weights).sum(axis=-1)
    x_mean = (x_win * weights).sum(axis=-1)
    cov = ((x_win - x_mean[..., None]) * (y_win - y_mean[..., None]) * weights).sum(axis=-1)
    var = ((x_win - x_mean[..., None]) ** 2 * weights).sum(axis=-1)
    beta = np.divide(cov, var, out=np.full_like(cov, np.nan), where=var > 0)
    alpha = y_mean - beta * x_mean
    residual = y_win - alpha[..., None] - beta[..., None] * x_win
    resid_std = np.sqrt((residual**2 * weights).sum(axis=-1))

    def pad(values: np.ndarray) -> pd.DataFrame:
        full = np.full((length, width), np.nan)
        full[window - 1 :, :] = values
        return pd.DataFrame(full, index=y.index, columns=y.columns)

    return {"beta": pad(beta), "alpha": pad(alpha), "resid_std": pad(resid_std)}


def exponential_weights(window: int, halflife: float) -> np.ndarray:
    weights = 0.5 ** (np.arange(window - 1, -1, -1) / halflife)
    return weights / weights.sum()


def weighted_std(frame: pd.DataFrame, window: int, halflife: float) -> pd.DataFrame:
    """指数加权标准差（均值同为加权均值）。"""
    values = frame.to_numpy(dtype=float)
    length, width = values.shape
    if length < window:
        return pd.DataFrame(np.nan, index=frame.index, columns=frame.columns)
    weights = exponential_weights(window, halflife)
    windows = np.lib.stride_tricks.sliding_window_view(values, window, axis=0)
    mean = (windows * weights).sum(axis=-1)
    variance = ((windows - mean[..., None]) ** 2 * weights).sum(axis=-1)
    result = np.full((length, width), np.nan)
    result[window - 1 :, :] = np.sqrt(variance)
    return pd.DataFrame(result, index=frame.index, columns=frame.columns)


def weighted_mean(frame: pd.DataFrame, window: int, halflife: float) -> pd.DataFrame:
    values = frame.to_numpy(dtype=float)
    length, width = values.shape
    if length < window:
        return pd.DataFrame(np.nan, index=frame.index, columns=frame.columns)
    weights = exponential_weights(window, halflife)
    windows = np.lib.stride_tricks.sliding_window_view(values, window, axis=0)
    result = np.full((length, width), np.nan)
    result[window - 1 :, :] = (windows * weights).sum(axis=-1)
    return pd.DataFrame(result, index=frame.index, columns=frame.columns)


def rolling_regression_beta(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    """价格对时间序号（1..N）的线性回归斜率，价格先除以窗口均值。"""
    values = frame.to_numpy(dtype=float)
    length, width = values.shape
    if length < window:
        return pd.DataFrame(np.nan, index=frame.index, columns=frame.columns)
    x = np.arange(1, window + 1, dtype=float)
    x_centered = x - x.mean()
    denom = (x_centered**2).sum()
    windows = np.lib.stride_tricks.sliding_window_view(values, window, axis=0)
    normalised = windows / windows.mean(axis=-1, keepdims=True)
    beta = (normalised * x_centered).sum(axis=-1) / denom
    result = np.full((length, width), np.nan)
    result[window - 1 :, :] = beta
    return pd.DataFrame(result, index=frame.index, columns=frame.columns)


def cs_zscore(frame: pd.DataFrame) -> pd.DataFrame:
    mean = frame.mean(axis=1)
    std = frame.std(axis=1, ddof=0)
    return frame.sub(mean, axis=0).div(std.replace(0, np.nan), axis=0)


def cs_winsorize(frame: pd.DataFrame, n_std: float = 3.0) -> pd.DataFrame:
    mean = frame.mean(axis=1)
    std = frame.std(axis=1, ddof=0)
    lower = mean - n_std * std
    upper = mean + n_std * std
    return frame.clip(lower=lower, upper=upper, axis=0)


def cs_rank(frame: pd.DataFrame, ascending: bool = True) -> pd.DataFrame:
    return frame.rank(axis=1, pct=True, ascending=ascending)


def cs_residual(target: pd.DataFrame, *regressors: pd.DataFrame) -> pd.DataFrame:
    """逐日横截面 OLS 残差；缺失值按当日可用样本拟合。"""
    y = target.to_numpy(dtype=float)
    xs = np.stack([item.to_numpy(dtype=float) for item in regressors], axis=2)
    result = np.full_like(y, np.nan)
    for i in range(y.shape[0]):
        row_y = y[i]
        row_x = xs[i]
        mask = np.isfinite(row_y) & np.isfinite(row_x).all(axis=1)
        if mask.sum() < row_x.shape[1] + 2:
            continue
        design = np.column_stack([np.ones(mask.sum()), row_x[mask]])
        coefficients, *_ = np.linalg.lstsq(design, row_y[mask], rcond=None)
        result[i, mask] = row_y[mask] - design @ coefficients
    return pd.DataFrame(result, index=target.index, columns=target.columns)


def cs_count(frame: pd.DataFrame) -> pd.Series:
    return frame.notna().sum(axis=1)
