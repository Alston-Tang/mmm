from __future__ import annotations

import asyncio
import logging
from typing import Any

from analysis.config import get_settings
from analysis.engine.service import AnalysisService

logger = logging.getLogger(__name__)


class AnalysisWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._service = AnalysisService()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="transaction-analysis-worker")

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._task is not None:
            await self._task

    def trigger_now(self) -> None:
        """Wake the worker to run an analysis cycle immediately."""
        self._wake.set()

    async def _run(self) -> None:
        settings = get_settings()
        logger.info(
            "Analysis worker started (interval=%ss, window=%dd, batch=%d)",
            settings.analysis_interval_seconds,
            settings.analysis_window_days,
            settings.analysis_batch_size,
        )

        skip_first_cycle = not settings.analysis_on_startup

        while not self._stop.is_set():
            if skip_first_cycle:
                skip_first_cycle = False
            else:
                result = await self._analysis_cycle()
                if result.get("processed", 0) > 0:
                    # Backlog remains — process next batch immediately.
                    continue

            try:
                await asyncio.wait_for(
                    self._wake.wait(),
                    timeout=settings.analysis_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

        logger.info("Analysis worker stopped")

    async def _analysis_cycle(self) -> dict[str, Any]:
        logger.info("Starting analysis cycle")
        try:
            result = await self._service.run_cycle()
            logger.info("Analysis cycle complete: %s", result)
            return result
        except Exception:
            logger.exception("Analysis cycle failed")
            return {"processed": 0, "error": "cycle_failed"}
