"""行情数据的缓存与面板构建。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .client import AkshareClient

logger = logging.getLogger(__name__)

PANEL_FIELDS = ("open", "high", "low", "close", "volume", "amount", "turnover", "float_shares")


@dataclass
class PricePanel:
    """日期 × 股票 的行情面板集合。"""

    fields: dict[str, pd.DataFrame]
    close_raw: pd.DataFrame
    index_close: pd.Series

    @property
    def dates(self) -> pd.DatetimeIndex:
        return self.fields["close"].index

    @property
    def codes(self) -> list[str]:
        return list(self.fields["close"].columns)

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.fields[name]


class PriceRepository:
    def __init__(
        self,
        client: AkshareClient,
        cache_dir: Path,
        adjust: str,
        fetch_unadjusted: bool,
        max_workers: int,
        start_date: str,
        end_date: str,
    ) -> None:
        self.client = client
        self.cache_dir = cache_dir / "prices"
        self.adjust = adjust
        self.fetch_unadjusted = fetch_unadjusted
        self.max_workers = max_workers
        self.start_date = start_date
        self.end_date = end_date
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, code: str, kind: str) -> Path:
        return self.cache_dir / f"{code}_{kind}.parquet"

    def _load_cached(self, code: str, kind: str) -> pd.DataFrame | None:
        path = self._cache_path(code, kind)
        if not path.exists():
            return None
        try:
            frame = pd.read_parquet(path)
        except Exception:  # 缓存损坏时重新拉取
            return None
        if frame.empty:
            return None
        if frame["date"].min() > pd.Timestamp(self.start_date) + pd.Timedelta(days=7):
            return None
        requested_end = (
            pd.Timestamp(self.end_date) if self.end_date else pd.Timestamp.today().normalize()
        )
        # 缓存必须覆盖「最近一个工作日」，否则会漏掉当天行情
        target = requested_end
        while target.weekday() >= 5:
            target -= pd.Timedelta(days=1)
        if frame["date"].max().normalize() < target.normalize():
            return None
        return frame

    def _fetch(self, code: str, kind: str) -> pd.DataFrame:
        adjust = self.adjust if kind == "adj" else ""
        frame = self.client.daily_bars(code, self.start_date, self.end_date, adjust)
        frame.to_parquet(self._cache_path(code, kind), index=False)
        return frame

    def load_one(self, code: str) -> tuple[str, pd.DataFrame, pd.DataFrame | None]:
        adjusted = self._load_cached(code, "adj")
        if adjusted is None:
            adjusted = self._fetch(code, "adj")
        raw = None
        if self.fetch_unadjusted:
            raw = self._load_cached(code, "raw")
            if raw is None:
                raw = self._fetch(code, "raw")
        return code, adjusted, raw

    def load(self, codes: list[str]) -> dict[str, tuple[pd.DataFrame, pd.DataFrame | None]]:
        result: dict[str, tuple[pd.DataFrame, pd.DataFrame | None]] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self.load_one, code): code for code in codes}
            for future in as_completed(futures):
                code = futures[future]
                try:
                    _, adjusted, raw = future.result()
                    result[code] = (adjusted, raw)
                except Exception as exc:
                    logger.error("行情获取失败 %s：%s", code, exc)
        missing = sorted(set(codes) - set(result))
        if missing:
            logger.warning("以下股票行情缺失，已从面板剔除：%s", missing)
        return result

    def build_panel(
        self,
        data: dict[str, tuple[pd.DataFrame, pd.DataFrame | None]],
        index_close: pd.Series,
    ) -> PricePanel:
        if not data:
            raise RuntimeError("没有任何股票行情数据，请检查网络或数据源")
        fields: dict[str, list[pd.Series]] = {name: [] for name in PANEL_FIELDS}
        raw_close: list[pd.Series] = []
        for code, (adjusted, raw) in data.items():
            indexed = adjusted.set_index("date")
            for name in PANEL_FIELDS:
                series = indexed[name].astype(float)
                series.name = code
                fields[name].append(series)
            if raw is not None:
                series = raw.set_index("date")["close"].astype(float)
                series.name = code
                raw_close.append(series)

        panel_fields = {
            name: pd.concat(series_list, axis=1).sort_index()
            for name, series_list in fields.items()
            if series_list
        }
        if raw_close:
            close_raw = pd.concat(raw_close, axis=1).sort_index()
        else:
            close_raw = panel_fields["close"].copy()
        codes = list(panel_fields["close"].columns)
        close_raw = close_raw.reindex(columns=codes)
        return PricePanel(
            fields=panel_fields,
            close_raw=close_raw.reindex(panel_fields["close"].index).ffill(),
            index_close=index_close,
        )
