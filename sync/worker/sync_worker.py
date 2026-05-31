from __future__ import annotations

import asyncio
import logging

from sync.config import get_settings
from sync.sync.service import sync_all_items

logger = logging.getLogger(__name__)


class SyncWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="plaid-sync-worker")

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._task is not None:
            await self._task

    def trigger_now(self) -> None:
        """Wake the worker to run a sync cycle immediately."""
        self._wake.set()

    async def _run(self) -> None:
        settings = get_settings()
        logger.info("Sync worker started (interval=%ss)", settings.sync_interval_seconds)

        if settings.sync_on_startup:
            await self._sync_cycle()

        while not self._stop.is_set():
            try:
                await asyncio.wait_for(
                    self._wake.wait(),
                    timeout=settings.sync_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass
            self._wake.clear()
            if self._stop.is_set():
                break
            await self._sync_cycle()

        logger.info("Sync worker stopped")

    async def _sync_cycle(self) -> None:
        logger.info("Starting sync cycle")
        try:
            results = await sync_all_items()
            for r in results:
                if "error" in r:
                    logger.warning("Item %s sync error: %s", r.get("item_id"), r["error"])
                else:
                    logger.info(
                        "Item %s (%s): +%s ~%s -%s (total stored: %s)",
                        r["item_id"],
                        r.get("label"),
                        r.get("added"),
                        r.get("modified"),
                        r.get("removed"),
                        r.get("stored_transactions"),
                    )
        except Exception:
            logger.exception("Sync cycle failed")
