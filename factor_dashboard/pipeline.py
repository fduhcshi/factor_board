"""因子计算主流程：选股 → 取数 → 构建上下文 → 逐因子计算 → 落盘。"""

from __future__ import annotations

import logging
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from .core.context import FactorContext
from .core.registry import FactorRegistry
from .data.client import AkshareClient
from .data.financials import FinancialPanel, FinancialRepository
from .data.prices import PriceRepository
from .report.dashboard_data import build_dashboard_data
from .report.summary import summarise, write_outputs
from .report.webdata import build_page_data, write_page_data
from .settings import AppConfig

logger = logging.getLogger(__name__)


class FactorPipeline:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_dir = config.run.output_dir / "runs" / self.run_id

    def _select_universe(self, client: AkshareClient) -> pd.DataFrame:
        cache_path = (
            self.config.data.cache_dir / f"universe_{self.config.universe.index_code}.csv"
        )
        if cache_path.exists():
            age_days = (pd.Timestamp.today() - pd.Timestamp(cache_path.stat().st_mtime, unit="s")).days
            if age_days <= 30:
                constituents = pd.read_csv(cache_path, dtype={"code": str})
                constituents["code"] = constituents["code"].str.zfill(6)
                logger.info("使用缓存的股票池（%d 天前）", age_days)
            else:
                constituents = None
        else:
            constituents = None
        if constituents is None:
            constituents = client.index_constituents(self.config.universe.index_code)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            constituents.to_csv(cache_path, index=False, encoding="utf-8-sig")
        if self.config.universe.exclude_bj:
            constituents = constituents[~constituents["exchange"].str.contains("北京")]
        constituents = constituents.sort_values("code").reset_index(drop=True)
        if self.config.universe.limit:
            constituents = constituents.head(self.config.universe.limit)
        if constituents.empty:
            raise RuntimeError("股票池为空，请检查 universe 配置")
        return constituents

    def _load_market(self, client: AkshareClient) -> pd.Series:
        end_date = self.config.data.end_date or datetime.today().strftime("%Y-%m-%d")
        try:
            frame = client.index_bars(self.config.market.index_code, self.config.data.start_date, end_date)
        except Exception as exc:
            logger.warning("市场指数 %s 取数失败，改用 %s：%s", self.config.market.index_code, self.config.market.fallback_index_code, exc)
            frame = client.index_bars(
                self.config.market.fallback_index_code, self.config.data.start_date, end_date
            )
        return frame.set_index("date")["close"].astype(float)

    def run(self) -> Path:
        config = self.config
        self.run_dir.mkdir(parents=True, exist_ok=True)
        logger.info("运行目录：%s", self.run_dir)

        client = AkshareClient(retries=config.data.retries)
        universe = self._select_universe(client)
        codes = universe["code"].tolist()
        logger.info("股票池：%s 共 %d 只", config.universe.index_code, len(codes))

        market_close = self._load_market(client)

        price_repo = PriceRepository(
            client=client,
            cache_dir=config.data.cache_dir,
            adjust=config.data.adjust,
            fetch_unadjusted=config.data.fetch_unadjusted,
            max_workers=config.data.max_workers,
            start_date=config.data.start_date,
            end_date=config.data.end_date,
        )
        price_data = price_repo.load(codes)
        price_panel = price_repo.build_panel(price_data, market_close)
        logger.info(
            "行情面板：%d 个交易日 × %d 只股票（%s ~ %s）",
            len(price_panel.dates),
            len(price_panel.codes),
            price_panel.dates[0].date(),
            price_panel.dates[-1].date(),
        )

        financial_repo = FinancialRepository(
            client=client,
            cache_dir=config.data.cache_dir,
            max_workers=config.data.max_workers,
            max_age_days=config.data.financial_cache_days,
        )
        quarters = financial_repo.load(price_panel.codes)
        financial_panel = FinancialPanel(quarters, price_panel.dates)

        ctx = FactorContext(
            price=price_panel, financial=financial_panel, market_close=market_close
        )

        catalog_path = config.project_root / "joinquant_factors.json"
        registry = FactorRegistry.from_catalog(catalog_path)
        logger.info(
            "因子目录：%d 个（已实现 %d，未实现 %d）",
            len(registry.metas),
            len(registry.implemented),
            len(registry.unsupported),
        )

        results = registry.compute(ctx)

        if config.output.start_date:
            cutoff = pd.Timestamp(config.output.start_date)
            for result in results.values():
                if result.values is not None:
                    result.values = result.values.loc[result.values.index >= cutoff]

        summary = summarise(results)
        failed = summary[(summary["status"] == "implemented") & (summary["error"] != "")]
        if not failed.empty:
            logger.warning("有 %d 个因子计算失败：%s", len(failed), failed["name"].tolist())

        metadata = {
            "run_id": self.run_id,
            "started_at": self.run_id,
            "universe": {
                "index_code": config.universe.index_code,
                "limit": config.universe.limit,
                "n_stocks": len(price_panel.codes),
                "codes": price_panel.codes,
            },
            "dates": {
                "start": str(price_panel.dates[0].date()),
                "end": str(price_panel.dates[-1].date()),
                "trading_days": len(price_panel.dates),
            },
            "factors": {
                "total": len(summary),
                "implemented": int((summary["status"] == "implemented").sum()),
                "unsupported": int((summary["status"] == "unsupported").sum()),
                "failed": len(failed),
            },
            "config": {
                "data": asdict(config.data),
                "output": asdict(config.output),
            },
        }

        paths = write_outputs(
            results,
            output_dir=self.run_dir,
            min_coverage=config.output.min_coverage,
            metadata=metadata,
        )
        shutil.copy2(config.project_root / "configs" / "default.yaml", self.run_dir / "config.yaml")

        page_data = build_page_data(
            results,
            summary,
            metadata,
            preview_days=config.web.preview_days,
            max_preview_factors=config.web.max_preview_factors,
        )
        write_page_data(page_data, config.project_root / "docs" / "data" / "page-data.js")

        build_dashboard_data(
            catalog_path=catalog_path,
            summary=summary,
            results=results,
            output_path=config.project_root / "docs" / "data" / "factor-metrics.js",
            run_meta=metadata,
        )

        logger.info("因子值：%s", paths["values"])
        logger.info("因子汇总：%s", paths["summary"])
        return self.run_dir
