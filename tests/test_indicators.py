"""关键口径的单元测试：季度还原、加权回归、真幅、注册表。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from factor_dashboard.core import indicators as ind
from factor_dashboard.data.financials import cumulative_to_single_quarter


def test_cumulative_to_single_quarter_handles_year_boundary():
    index = pd.to_datetime(["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31", "2024-03-31"])
    cumulative = pd.Series([10.0, 25.0, 40.0, 60.0, 12.0], index=index)
    single = cumulative_to_single_quarter(cumulative)
    assert single.tolist() == [10.0, 15.0, 15.0, 20.0, 12.0]


def test_cumulative_to_single_quarter_falls_back_when_quarter_missing():
    index = pd.to_datetime(["2023-03-31", "2023-09-30"])
    cumulative = pd.Series([10.0, 45.0], index=index)
    single = cumulative_to_single_quarter(cumulative)
    assert single.tolist() == [10.0, 45.0]


def test_safe_div_removes_inf():
    numerator = pd.DataFrame({"a": [1.0, 2.0]})
    denominator = pd.DataFrame({"a": [0.0, 2.0]})
    result = ind.safe_div(numerator, denominator)
    assert np.isnan(result.iloc[0, 0])
    assert result.iloc[1, 0] == 1.0


def test_true_range_uses_previous_close():
    high = pd.DataFrame({"a": [10.0, 12.0]})
    low = pd.DataFrame({"a": [8.0, 9.0]})
    close = pd.DataFrame({"a": [9.0, 11.0]})
    result = ind.true_range(high, low, close)
    # 首日没有前收盘，无法计算真实波幅
    assert np.isnan(result.iloc[0, 0])
    assert result.iloc[1, 0] == 3.0  # max(12-9, 12-9, 11-9) = 3


def test_rolling_regression_beta_recovers_slope():
    window = 20
    x = np.arange(1, window + 1, dtype=float)
    beta = 0.01
    prices = pd.DataFrame({"a": 100 * (1 + beta * (x - x.mean()))}, index=pd.RangeIndex(window))
    normalised = prices / prices.mean()
    expected = np.polyfit(x, normalised["a"].to_numpy(), 1)[0]
    result = ind.rolling_regression_beta(prices, window)
    assert abs(result["a"].iloc[-1] - expected) < 1e-9


def test_weighted_std_matches_manual_for_constant_series():
    frame = pd.DataFrame({"a": np.full(10, 3.0)})
    result = ind.weighted_std(frame, 5, 2.0)
    assert result["a"].iloc[-1] == 0.0


def test_cs_residual_removes_linear_exposure():
    index = pd.date_range("2024-01-01", periods=3)
    size = pd.DataFrame(
        np.arange(1, 13).reshape(3, 4), index=index, columns=list("abcd"), dtype=float
    )
    target = 2.0 * size + 1.0
    residual = ind.cs_residual(target, size)
    assert np.allclose(residual.to_numpy(), 0.0, atol=1e-9)
