from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from viewer.api.routes import router
from viewer.config import get_settings
from viewer.db.mongo import close_client
from viewer.ui import VIEWER_HTML
from viewer.month_ui import MONTH_SUMMARY_HTML

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


app = FastAPI(
    title="MMM Transaction Viewer",
    description="Browse analyzed transactions with filters and sorting",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def viewer_page() -> HTMLResponse:
    return HTMLResponse(VIEWER_HTML)


@app.get("/month", response_class=HTMLResponse, include_in_schema=False)
async def month_summary_page() -> HTMLResponse:
    return HTMLResponse(MONTH_SUMMARY_HTML)


@app.get("/about")
async def about():
    return {
        "service": "mmm-transaction-viewer",
        "ui": "/",
        "month_summary_ui": "/month",
        "docs": "/docs",
        "health": "/api/v1/health",
        "api": "/api/v1/transactions",
        "months_api": "/api/v1/months",
    }


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "viewer.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
