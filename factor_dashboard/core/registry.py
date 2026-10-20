"""因子注册表：把聚宽因子目录与本地实现对应起来。"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .context import FactorContext
from .financial_factors import FINANCIAL_FACTORS
from .price_factors import PRICE_FACTORS
from .style_factors import STYLE_FACTORS

logger = logging.getLogger(__name__)

IMPLEMENTED = {**PRICE_FACTORS, **FINANCIAL_FACTORS, **STYLE_FACTORS}

UNSUPPORTED_REASONS: dict[str, str] = {
    "predicted_earnings_to_price_ratio": "需要分析师一致预期，AKShare 无稳定历史接口",
    "short_term_predicted_earnings_growth": "需要分析师一致预期，AKShare 无稳定历史接口",
    "long_term_predicted_earnings_growth": "需要分析师一致预期，AKShare 无稳定历史接口",
    "growth": "复合因子，其中 29% 权重来自分析师预期",
    "earnings_yield": "复合因子，核心子项为预期市盈率",
    "divyild": "复合因子，含分析师预期股息率",
    "long_growth": "复合因子，70% 权重来自长期预期盈利增长",
    "earnvar": "复合因子，含分析师预测离散度",
    "earnyild": "复合因子，含预期盈利市值比",
    "adjusted_profit_to_total_profit": "扣非净利润不在新浪三大报表口径内",
    "non_recurring_gain_loss": "非经常性损益无对应报表科目",
    "net_interest_expense": "新浪利润表只有利息支出/利息费用，缺利息收入",
    "size_v2": "聚宽未提供计算公式",
    "liquidity_v2": "聚宽未提供计算公式",
    "dividend_yield_v2": "聚宽未提供计算公式",
    "quality_v2": "聚宽未提供计算公式",
    "value_v2": "聚宽未提供计算公式",
    "growth_v2": "聚宽未提供计算公式",
    "momentum_v2": "聚宽未提供计算公式",
    "volatility_v2": "聚宽未提供计算公式",
    "sentiment_v2": "聚宽未提供计算公式",
    "relative_momentum": "子因子 historical_alpha 未定义",
    "ltrevrsl": "子因子 long_term_historical_alpha 未定义",
    "profit": "子因子 gross_profitability 系列未定义",
    "invsqlty": "子因子 issuance_growth 未定义",
    "earnqlty": "子因子 accruals 系列未定义",
}

VOLUME_PREFIXES = ("VOL", "VEMA", "TVMA", "TVSTD", "VSTD", "VROC", "DAVOL")
VOLUME_NAMES = {
    "VR",
    "BR",
    "AR",
    "ARBR",
    "WVAD",
    "MAWVAD",
    "VDIFF",
    "VDEA",
    "VMACD",
    "VOSC",
    "MFI14",
    "CR20",
    "PSY",
    "turnover_volatility",
    "money_flow_20",
    "single_day_VPT",
    "single_day_VPT_6",
    "single_day_VPT_12",
    "Volume1M",
    "share_turnover_monthly",
    "average_share_turnover_quarterly",
    "average_share_turnover_annual",
}


def classify_group(name: str) -> str:
    if name in FINANCIAL_FACTORS:
        return "财务"
    if name in STYLE_FACTORS:
        return "风格"
    if name in PRICE_FACTORS:
        if name.startswith(VOLUME_PREFIXES) or name in VOLUME_NAMES:
            return "量能"
        return "价格技术"
    return "未实现"


@dataclass(frozen=True)
class FactorMeta:
    name: str
    intro: str
    formula: str
    group: str
    status: str  # implemented | unsupported
    reason: str = ""


@dataclass
class FactorResult:
    meta: FactorMeta
    values: pd.DataFrame | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.values is not None and self.error is None


class FactorRegistry:
    def __init__(self, metas: list[FactorMeta]) -> None:
        self.metas = metas
        self._by_name = {meta.name: meta for meta in metas}

    @classmethod
    def from_catalog(cls, catalog_path: Path) -> FactorRegistry:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        metas: list[FactorMeta] = []
        for item in payload["factors"]:
            name = item["name"]
            if name in IMPLEMENTED:
                status, reason = "implemented", ""
            else:
                status = "unsupported"
                reason = UNSUPPORTED_REASONS.get(name, "未在本地实现，且未登记原因")
            metas.append(
                FactorMeta(
                    name=name,
                    intro=item.get("intro", ""),
                    formula=item.get("algorithmIntro", "").strip(),
                    group=classify_group(name),
                    status=status,
                    reason=reason,
                )
            )
        registry = cls(metas)
        unknown = [m.name for m in metas if m.status == "unsupported" and not m.reason]
        if unknown:
            logger.warning("以下因子未实现且缺少原因：%s", unknown)
        return registry

    @property
    def implemented(self) -> list[FactorMeta]:
        return [meta for meta in self.metas if meta.status == "implemented"]

    @property
    def unsupported(self) -> list[FactorMeta]:
        return [meta for meta in self.metas if meta.status == "unsupported"]

    def compute(self, ctx: FactorContext) -> dict[str, FactorResult]:
        results: dict[str, FactorResult] = {}
        for meta in self.metas:
            if meta.status != "implemented":
                results[meta.name] = FactorResult(meta=meta)
                continue
            func: Callable[[FactorContext], pd.DataFrame] = IMPLEMENTED[meta.name]
            try:
                values = func(ctx)
                values = values.reindex(index=ctx.dates, columns=ctx.codes)
                results[meta.name] = FactorResult(meta=meta, values=values.astype("float32"))
            except Exception as exc:  # 单个因子失败不应中断整体运行
                logger.exception("因子 %s 计算失败", meta.name)
                results[meta.name] = FactorResult(meta=meta, error=f"{type(exc).__name__}: {exc}")
        return results
