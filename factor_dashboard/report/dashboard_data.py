"""生成因子看板所需的数据（聚宽绩效指标 + 本地因子值时间序列）。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from ..core.registry import FactorResult


def _number(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _round(value, digits: int = 6) -> float | None:
    number = _number(value)
    return None if number is None else round(number, digits)


def _block(row: dict, prefix: str, fields: tuple[str, ...]) -> list:
    return [_round(row.get(f"{prefix}{field}")) for field in fields]


def _clean(series: pd.Series, digits: int = 4) -> list:
    return [None if pd.isna(value) else round(float(value), digits) for value in series]


def _write_series(
    results: dict[str, FactorResult], directory: Path, calendar: list[str]
) -> int:
    """为每个已实现因子写一个按需加载的经典脚本。"""
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = 0
    for name, result in results.items():
        values = result.values
        if values is None or values.empty:
            continue
        frame = values.reindex(pd.DatetimeIndex(calendar))
        median = frame.median(axis=1)
        lower = frame.quantile(0.25, axis=1)
        upper = frame.quantile(0.75, axis=1)
        coverage = frame.notna().sum(axis=1) / max(frame.shape[1], 1)
        payload = {
            "m": _clean(median),
            "l": _clean(lower),
            "u": _clean(upper),
            "c": _clean(coverage, 3),
        }
        script = (
            'window.SERIES_POOL=window.SERIES_POOL||{};window.SERIES_POOL['
            + json.dumps(name)
            + "]="
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            + ";"
        )
        (directory / f"{name}.js").write_text(script, encoding="utf-8")
        written += 1
    return written


def build_dashboard_data(
    catalog_path: Path,
    summary: pd.DataFrame,
    results: dict[str, FactorResult],
    output_path: Path,
    run_meta: dict,
) -> dict:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    summary_by_name = {row["name"]: row for _, row in summary.iterrows()}
    benchmark = _round(payload["factors"][0].get("annual_return_bm")) if payload["factors"] else None

    calendar: list[str] = []
    for result in results.values():
        if result.values is not None and not result.values.empty:
            calendar = [str(item.date()) for item in result.values.index]
            break

    series_dir = output_path.parent / "series"
    series_count = _write_series(results, series_dir, calendar) if calendar else 0

    factors: list[dict] = []
    for item in payload["factors"]:
        name = item["name"]
        local = summary_by_name.get(name)
        group = (local["group"] if local is not None else "") or "未实现"
        factors.append(
            {
                "n": name,
                "i": item.get("intro", ""),
                "f": item.get("algorithmIntro", "").strip(),
                "g": group,
                "s": 1 if local is not None and local["status"] == "implemented" else 0,
                "c": _round(local["coverage"], 4) if local is not None else 0.0,
                "k": int(local["stocks_with_value"]) if local is not None else 0,
                "r": (local["reason"] if local is not None else "") or "",
                "e": (local["error"] if local is not None else "") or "",
                "ic": _round(item.get("ic_mean")),
                "ir": _round(item.get("ir")),
                "gi": _round(item.get("good_ic")),
                "q1": _block(
                    item,
                    "",
                    (
                        "compound_return_1q",
                        "annual_return_1q",
                        "annual_ex_return_1q",
                        "max_drawdown_1q",
                        "sharpe_1q",
                        "turnover_mean_1q",
                    ),
                ),
                "q5": _block(
                    item,
                    "",
                    (
                        "compound_return_5q",
                        "annual_return_5q",
                        "annual_ex_return_5q",
                        "max_drawdown_5q",
                        "sharpe_5q",
                        "turnover_mean_5q",
                    ),
                ),
                "ls": _block(
                    item,
                    "",
                    (
                        "compound_return_ls",
                        "annual_return_ls",
                        "max_drawdown_ls",
                        "sharpe_ls",
                        "turnover_mean_ls",
                    ),
                ),
                "l2": _block(
                    item,
                    "",
                    (
                        "compound_return_ls2",
                        "annual_return_ls2",
                        "max_drawdown_ls2",
                        "sharpe_ls2",
                        "turnover_mean_ls2",
                    ),
                ),
            }
        )

    strongest_ic = max(
        (item for item in factors if item["ic"] is not None), key=lambda x: abs(x["ic"])
    )
    strongest_ls = max(
        (item for item in factors if item["ls"][1] is not None), key=lambda x: x["ls"][1]
    )

    data = {
        "meta": {
            "run_id": run_meta.get("run_id", datetime.now().strftime("%Y%m%d-%H%M%S")),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "universe": run_meta.get("universe", {}),
            "dates": run_meta.get("dates", {}),
            "benchmark": benchmark,
            "total": len(factors),
            "implemented": sum(1 for item in factors if item["s"]),
            "unsupported": sum(1 for item in factors if not item["s"]),
            "strongest_ic": {"name": strongest_ic["n"], "value": strongest_ic["ic"]},
            "strongest_ls": {"name": strongest_ls["n"], "value": strongest_ls["ls"][1]},
            "params": payload.get("params", {}),
            "calendar": calendar,
            "series_count": series_count,
        },
        "factors": factors,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "window.FACTOR_BOARD = "
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        + ";",
        encoding="utf-8",
    )
    return data
