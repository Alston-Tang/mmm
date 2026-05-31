from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from sync.api.routes import router
from sync.config import get_settings
from sync.db.mongo import close_client, ensure_indexes
from sync.worker.sync_worker import SyncWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    worker = SyncWorker()
    worker.start()
    app.state.sync_worker = worker
    yield
    await worker.stop()
    await close_client()


app = FastAPI(
    title="MMM Plaid Sync Service",
    description="Continuously sync Plaid transactions to MongoDB",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/")
async def root():
    return {
        "service": "mmm-plaid-sync",
        "docs": "/docs",
        "link_ui": "/api/v1/link",
        "health": "/api/v1/health",
    }


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "sync.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
