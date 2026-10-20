"""配置加载与校验。

普通参数统一放在 ``configs/default.yaml``，本模块是唯一的加载入口。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "default.yaml"


class ConfigError(ValueError):
    """配置缺失、无法解析或字段非法。"""


@dataclass(frozen=True)
class RunConfig:
    seed: int = 42
    output_dir: Path = PROJECT_ROOT / "outputs"


@dataclass(frozen=True)
class UniverseConfig:
    index_code: str = "000905"
    limit: int | None = 50
    exclude_bj: bool = True


@dataclass(frozen=True)
class MarketConfig:
    index_code: str = "000902"
    fallback_index_code: str = "000905"


@dataclass(frozen=True)
class DataConfig:
    start_date: str = "2022-09-01"
    end_date: str = ""
    adjust: str = "qfq"
    cache_dir: Path = PROJECT_ROOT / "data" / "cache"
    max_workers: int = 4
    retries: int = 3
    fetch_unadjusted: bool = True
    financial_cache_days: int = 7


@dataclass(frozen=True)
class OutputConfig:
    start_date: str | None = "2024-01-01"
    min_coverage: float = 0.2


@dataclass(frozen=True)
class WebConfig:
    max_preview_factors: int = 8
    preview_days: int = 250


@dataclass(frozen=True)
class AppConfig:
    run: RunConfig
    universe: UniverseConfig
    market: MarketConfig
    data: DataConfig
    output: OutputConfig
    web: WebConfig
    project_root: Path = field(default=PROJECT_ROOT)

    def resolve(self, path: str | Path) -> Path:
        """把相对路径解析到项目根目录。"""
        candidate = Path(path)
        return candidate if candidate.is_absolute() else self.project_root / candidate


_TOP_LEVEL_KEYS = {"run", "universe", "market", "data", "output", "web"}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"配置文件不存在：{path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"配置文件无法解析：{path}（{exc}）") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"配置文件顶层必须是映射：{path}")
    return payload


def _section(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"配置段 {name} 必须是映射")
    return value


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{field_name} 必须是正整数，当前为 {value!r}")
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """映射递归合并，列表与标量整体替换。"""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path | None = None) -> AppConfig:
    """加载并校验配置。

    未提供路径时读取 ``configs/default.yaml``；提供变体配置时，先加载默认配置，
    再用变体做递归合并，因此变体只需要写差异项。
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    payload = _load_yaml(config_path)
    if config_path.resolve() != DEFAULT_CONFIG_PATH.resolve():
        payload = _deep_merge(_load_yaml(DEFAULT_CONFIG_PATH), payload)

    unknown = set(payload) - _TOP_LEVEL_KEYS
    if unknown:
        raise ConfigError(f"存在未知配置段：{sorted(unknown)}")

    run_raw = _section(payload, "run")
    universe_raw = _section(payload, "universe")
    market_raw = _section(payload, "market")
    data_raw = _section(payload, "data")
    output_raw = _section(payload, "output")
    web_raw = _section(payload, "web")

    limit = universe_raw.get("limit", 50)
    if limit is not None:
        limit = _positive_int(limit, "universe.limit")

    data = DataConfig(
        start_date=str(data_raw.get("start_date", "2022-09-01")),
        end_date=str(data_raw.get("end_date", "")),
        adjust=str(data_raw.get("adjust", "qfq")),
        cache_dir=(PROJECT_ROOT / str(data_raw.get("cache_dir", "data/cache"))),
        max_workers=_positive_int(data_raw.get("max_workers", 4), "data.max_workers"),
        retries=_positive_int(data_raw.get("retries", 3), "data.retries"),
        fetch_unadjusted=bool(data_raw.get("fetch_unadjusted", True)),
        financial_cache_days=_positive_int(
            data_raw.get("financial_cache_days", 7), "data.financial_cache_days"
        ),
    )

    output = OutputConfig(
        start_date=output_raw.get("start_date", "2024-01-01") or None,
        min_coverage=float(output_raw.get("min_coverage", 0.2)),
    )
    if not 0.0 <= output.min_coverage <= 1.0:
        raise ConfigError("output.min_coverage 必须位于 [0, 1]")

    return AppConfig(
        run=RunConfig(
            seed=int(run_raw.get("seed", 42)),
            output_dir=PROJECT_ROOT / str(run_raw.get("output_dir", "outputs")),
        ),
        universe=UniverseConfig(
            index_code=str(universe_raw.get("index_code", "000905")),
            limit=limit,
            exclude_bj=bool(universe_raw.get("exclude_bj", True)),
        ),
        market=MarketConfig(
            index_code=str(market_raw.get("index_code", "000902")),
            fallback_index_code=str(market_raw.get("fallback_index_code", "000905")),
        ),
        data=data,
        output=output,
        web=WebConfig(
            max_preview_factors=_positive_int(
                web_raw.get("max_preview_factors", 6), "web.max_preview_factors"
            ),
            preview_days=_positive_int(web_raw.get("preview_days", 250), "web.preview_days"),
        ),
    )
