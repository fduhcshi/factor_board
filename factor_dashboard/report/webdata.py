"""为网页生成轻量数据资产（window.PAGE_DATA）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.registry import FactorResult


def _histogram(values: pd.Series, bins: int = 12) -> dict:
    data = values.dropna().to_numpy()
    if data.size == 0:
        return {"edges": [], "counts": []}
    counts, edges = np.histogram(data, bins=bins, range=(0.0, 1.0))
    return {
        "edges": [round(float(edge), 4) for edge in edges],
        "counts": [int(count) for count in counts],
    }


PREFERRED_PREVIEW = [
    "VOL20",
    "VR",
    "MAC20",
    "BIAS20",
    "roe_ttm",
    "gross_income_ratio",
    "book_to_price_ratio",
    "resvol",
    "beta",
]


def _preview_series(
    results: dict[str, FactorResult], summary: pd.DataFrame, days: int, max_factors: int
) -> list[dict]:
    implemented = summary[summary["status"] == "implemented"].sort_values(
        "coverage", ascending=False
    )
    available = set(implemented["name"])
    picks: list[str] = [name for name in PREFERRED_PREVIEW if name in available]
    if len(picks) < max_factors:
        per_group = max(1, max_factors // max(len(implemented["group"].unique()), 1))
        for group in implemented["group"].unique():
            block = implemented[implemented["group"] == group].head(per_group)
            picks.extend([name for name in block["name"] if name not in picks])
    picks = picks[:max_factors]

    series = []
    for name in picks:
        values = results[name].values
        if values is None or values.empty:
            continue
        tail = values.tail(days)
        stats = tail.quantile([0.25, 0.5, 0.75], axis=1)
        series.append(
            {
                "factor": name,
                "dates": [str(item.date()) for item in tail.index],
                "median": [None if pd.isna(v) else round(float(v), 6) for v in stats.loc[0.5]],
                "p25": [None if pd.isna(v) else round(float(v), 6) for v in stats.loc[0.25]],
                "p75": [None if pd.isna(v) else round(float(v), 6) for v in stats.loc[0.75]],
                "coverage": [
                    round(float(v), 4) for v in tail.notna().sum(axis=1) / max(len(tail.columns), 1)
                ],
            }
        )
    return series


def build_page_data(
    results: dict[str, FactorResult],
    summary: pd.DataFrame,
    metadata: dict,
    preview_days: int,
    max_preview_factors: int = 8,
) -> dict:
    implemented = summary[summary["status"] == "implemented"]
    unsupported = summary[summary["status"] == "unsupported"]
    failed = summary[(summary["status"] == "implemented") & (summary["error"] != "")]

    groups = []
    for group, block in summary.groupby("group"):
        groups.append(
            {
                "name": group,
                "implemented": int((block["status"] == "implemented").sum()),
                "unsupported": int((block["status"] == "unsupported").sum()),
                "failed": int(((block["status"] == "implemented") & (block["error"] != "")).sum()),
                "avg_coverage": round(float(block.loc[block["status"] == "implemented", "coverage"].mean() or 0), 4),
            }
        )

    factors = []
    for _, row in summary.iterrows():
        factors.append(
            {
                "name": row["name"],
                "intro": row["intro"],
                "group": row["group"],
                "status": row["status"],
                "reason": row["reason"],
                "error": row["error"],
                "coverage": round(float(row["coverage"]), 4),
                "non_null_cells": int(row["non_null_cells"]),
                "stocks_with_value": int(row["stocks_with_value"]),
                "first_date": row["first_date"],
                "last_date": row["last_date"],
                "latest_mean": None if pd.isna(row["latest_mean"]) else round(float(row["latest_mean"]), 6),
                "latest_std": None if pd.isna(row["latest_std"]) else round(float(row["latest_std"]), 6),
                "formula": "",
            }
        )

    catalog = {meta.name: meta for meta in (result.meta for result in results.values())}
    for item in factors:
        item["formula"] = catalog[item["name"]].formula if item["name"] in catalog else ""

    coverage_values = implemented["coverage"].astype(float)
    payload = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "run_id": metadata.get("run_id", ""),
            "universe": metadata.get("universe", {}),
            "dates": metadata.get("dates", {}),
            "counts": {
                "total": len(summary),
                "implemented": len(implemented),
                "unsupported": len(unsupported),
                "failed": len(failed),
                "coverage_median": round(float(coverage_values.median()), 4),
            },
        },
        "groups": groups,
        "factors": factors,
        "coverage_hist": _histogram(coverage_values),
        "series": _preview_series(results, summary, preview_days, max_preview_factors),
    }
    return payload


def write_page_data(payload: dict, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "window.PAGE_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";"
    target.write_text(text, encoding="utf-8")
    return target
