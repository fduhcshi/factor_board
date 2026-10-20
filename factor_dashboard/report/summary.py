"""因子结果的汇总统计与落盘。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.registry import FactorResult


def summarise(results: dict[str, FactorResult]) -> pd.DataFrame:
    rows = []
    for name, result in results.items():
        meta = result.meta
        record = {
            "name": name,
            "intro": meta.intro,
            "group": meta.group,
            "status": meta.status,
            "reason": meta.reason,
            "error": result.error or "",
            "coverage": 0.0,
            "non_null_cells": 0,
            "stocks_with_value": 0,
            "first_date": "",
            "last_date": "",
            "latest_mean": np.nan,
            "latest_std": np.nan,
            "latest_median": np.nan,
        }
        values = result.values
        if values is not None and not values.empty:
            total = values.shape[0] * values.shape[1]
            non_null = int(values.notna().sum().sum())
            record["non_null_cells"] = non_null
            record["coverage"] = round(non_null / total, 6) if total else 0.0
            valid_counts = values.notna().sum(axis=1)
            if (valid_counts > 0).any():
                valid_dates = values.index[valid_counts > 0]
                record["first_date"] = str(valid_dates[0].date())
                record["last_date"] = str(valid_dates[-1].date())
            last_row = values.ffill().iloc[-1] if len(values) else pd.Series(dtype=float)
            if last_row.notna().any():
                record["stocks_with_value"] = int(last_row.notna().sum())
                record["latest_mean"] = float(last_row.mean())
                record["latest_std"] = float(last_row.std(ddof=0))
                record["latest_median"] = float(last_row.median())
        rows.append(record)
    return pd.DataFrame(rows)


def factor_catalog(results: dict[str, FactorResult]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "name": item.meta.name,
                "intro": item.meta.intro,
                "formula": item.meta.formula,
                "group": item.meta.group,
                "status": item.meta.status,
                "reason": item.meta.reason,
            }
            for item in results.values()
        ]
    )


def values_to_long(
    results: dict[str, FactorResult], min_coverage: float = 0.0, summary: pd.DataFrame | None = None
) -> pd.DataFrame:
    keep = {
        row["name"]
        for _, row in (summary.iterrows() if summary is not None else [])
        if row["status"] == "implemented" and row["coverage"] >= min_coverage
    }
    frames = []
    for name, result in results.items():
        if result.values is None or (keep and name not in keep):
            continue
        frame = (
            result.values.reset_index(names="date")
            .melt(id_vars="date", var_name="code", value_name="value")
            .dropna(subset=["value"])
        )
        if frame.empty:
            continue
        frame["factor"] = name
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["date", "code", "factor", "value"])
    combined = pd.concat(frames, ignore_index=True)
    combined["value"] = combined["value"].astype("float32")
    return combined[["date", "code", "factor", "value"]]


def write_outputs(
    results: dict[str, FactorResult],
    output_dir: Path,
    min_coverage: float,
    metadata: dict,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarise(results)
    catalog = factor_catalog(results)

    summary_path = output_dir / "factor_summary.csv"
    catalog_path = output_dir / "factor_catalog.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    catalog.to_csv(catalog_path, index=False, encoding="utf-8-sig")

    long_frame = values_to_long(results, min_coverage=min_coverage, summary=summary)
    values_path = output_dir / "factor_values.parquet"
    long_frame.to_parquet(values_path, index=False)

    meta_path = output_dir / "metadata.json"
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return {
        "summary": summary_path,
        "catalog": catalog_path,
        "values": values_path,
        "metadata": meta_path,
    }
