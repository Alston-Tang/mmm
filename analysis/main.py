from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from analysis.api.routes import router
from analysis.config import get_settings
from analysis.db.mongo import close_client, ensure_indexes
from analysis.worker.analysis_worker import AnalysisWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    worker = AnalysisWorker()
    worker.start()
    app.state.analysis_worker = worker
    yield
    await worker.stop()
    await close_client()


app = FastAPI(
    title="MMM Transaction Analysis Service",
    description="Analyze Plaid transactions via LLM and produce normalized transaction records",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/")
async def root():
    return {
        "service": "mmm-transaction-analysis",
        "docs": "/docs",
        "health": "/api/v1/health",
        "status": "/api/v1/status",
    }


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "analysis.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
