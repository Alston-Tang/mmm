from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.api.schemas import (
    HealthResponse,
    ItemResponse,
    LinkExchangeRequest,
    LinkExchangeResponse,
    LinkTokenResponse,
    SyncTriggerResponse,
)
from app.db.mongo import get_database
from app.db.repository import ItemRepository, TransactionRepository
from app.plaid.link import create_link_token, exchange_public_token
from app.sync.service import sync_all_items, sync_item
from app.worker.sync_worker import SyncWorker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def get_worker(request: Request) -> SyncWorker:
    return request.app.state.sync_worker


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        await get_database().command("ping")
        mongo_status = "ok"
    except Exception as exc:
        mongo_status = f"error: {exc}"
    return HealthResponse(
        status="ok" if mongo_status == "ok" else "degraded",
        mongodb=mongo_status,
    )


@router.get("/items", response_model=list[ItemResponse])
async def list_items() -> list[ItemResponse]:
    items = await ItemRepository.list_active()
    result: list[ItemResponse] = []
    for item in items:
        count = await TransactionRepository.count_for_item(item["item_id"])
        result.append(
            ItemResponse(
                item_id=item["item_id"],
                label=item["label"],
                institution_name=item.get("institution_name"),
                status=item["status"],
                created_at=item.get("created_at"),
                last_sync_at=item.get("last_sync_at"),
                last_sync_error=item.get("last_sync_error"),
                transaction_count=count,
            )
        )
    return result


@router.post("/link/token", response_model=LinkTokenResponse)
async def link_token(user_id: str = "default-user") -> LinkTokenResponse:
    token = await asyncio.to_thread(create_link_token, user_id=user_id)
    return LinkTokenResponse(link_token=token)


@router.post("/link/exchange", response_model=LinkExchangeResponse)
async def link_exchange(body: LinkExchangeRequest, request: Request) -> LinkExchangeResponse:
    existing = await ItemRepository.list_active()
    for item in existing:
        if item["label"] == body.label:
            raise HTTPException(status_code=409, detail=f"Label '{body.label}' already exists")

    exchange = await asyncio.to_thread(exchange_public_token, body.public_token)
    item_id = exchange["item_id"]
    access_token = exchange["access_token"]

    if await ItemRepository.get_by_item_id(item_id):
        raise HTTPException(status_code=409, detail="This bank connection is already linked")

    await ItemRepository.create(
        item_id=item_id,
        label=body.label,
        access_token=access_token,
    )

    get_worker(request).trigger_now()
    return LinkExchangeResponse(item_id=item_id, label=body.label)


@router.post("/items/{item_id}/sync", response_model=SyncTriggerResponse)
async def sync_one_item(item_id: str, reset: bool = False) -> SyncTriggerResponse:
    item = await ItemRepository.get_by_item_id(item_id)
    if not item or item.get("status") != "active":
        raise HTTPException(status_code=404, detail="Item not found")
    result = await sync_item(item, reset_cursor=reset)
    return SyncTriggerResponse(results=[result])


@router.post("/sync", response_model=SyncTriggerResponse)
async def trigger_sync_all(reset: bool = False) -> SyncTriggerResponse:
    results = await sync_all_items(reset_cursor=reset)
    return SyncTriggerResponse(results=results)


@router.post("/items/{item_id}/reset", response_model=SyncTriggerResponse)
async def reset_item_cursor(item_id: str) -> SyncTriggerResponse:
    item = await ItemRepository.get_by_item_id(item_id)
    if not item or item.get("status") != "active":
        raise HTTPException(status_code=404, detail="Item not found")
    await ItemRepository.update_cursor(item_id, None)
    result = await sync_item({**item, "cursor": None}, reset_cursor=True)
    return SyncTriggerResponse(results=[result])


@router.delete("/items/{item_id}", status_code=204)
async def deactivate_item(item_id: str) -> None:
    if not await ItemRepository.deactivate(item_id):
        raise HTTPException(status_code=404, detail="Item not found")


@router.post("/webhooks/plaid")
async def plaid_webhook(request: Request) -> dict:
    """Handle Plaid webhooks (e.g. SYNC_UPDATES_AVAILABLE)."""
    payload = await request.json()
    webhook_type = payload.get("webhook_type")
    webhook_code = payload.get("webhook_code")
    item_id = payload.get("item_id")

    logger.info("Plaid webhook: %s / %s item=%s", webhook_type, webhook_code, item_id)

    if webhook_type == "TRANSACTIONS" and webhook_code in (
        "SYNC_UPDATES_AVAILABLE",
        "INITIAL_UPDATE",
        "HISTORICAL_UPDATE",
        "DEFAULT_UPDATE",
    ):
        get_worker(request).trigger_now()

    return {"received": True}


LINK_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>MMM — Link bank</title>
  <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 32rem; margin: 2rem auto; padding: 0 1rem; }
    input, button { font-size: 1rem; padding: 0.4rem; margin: 0.25rem 0; width: 100%; box-sizing: border-box; }
    pre { background: #f4f4f4; padding: 1rem; overflow-x: auto; font-size: 0.85rem; }
    .ok { color: #060; }
    .err { color: #a00; }
  </style>
</head>
<body>
  <h1>Link a bank account</h1>
  <p>Adds an account to the running sync service (saved in MongoDB).</p>
  <label>Label <input id="label" placeholder="e.g. chase-checking" /></label>
  <button id="open">Connect with Plaid</button>
  <div id="out"></div>
  <script>
    const api = window.location.origin;
    document.getElementById('open').onclick = async () => {
      const label = document.getElementById('label').value.trim();
      if (!label) { alert('Enter a label'); return; }
      const out = document.getElementById('out');
      out.innerHTML = '<p>Loading link token…</p>';
      try {
        const res = await fetch(api + '/api/v1/link/token', { method: 'POST' });
        const { link_token } = await res.json();
        if (!link_token) throw new Error('No link_token');
        const handler = Plaid.create({
          token: link_token,
          onSuccess: async (public_token) => {
            out.innerHTML = '<p>Linking…</p>';
            const ex = await fetch(api + '/api/v1/link/exchange', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ public_token, label }),
            });
            const data = await ex.json();
            if (!ex.ok) {
              out.innerHTML = '<pre class="err">' + JSON.stringify(data, null, 2) + '</pre>';
              return;
            }
            out.innerHTML = '<pre class="ok">' + JSON.stringify(data, null, 2) +
              '\\n\\nSync worker will pick this up automatically.</pre>';
          },
          onExit: (err) => {
            if (err) out.innerHTML = '<pre class="err">' + JSON.stringify(err, null, 2) + '</pre>';
          },
        });
        handler.open();
      } catch (e) {
        out.innerHTML = '<pre class="err">' + e + '</pre>';
      }
    };
  </script>
</body>
</html>"""


@router.get("/link", response_class=HTMLResponse, include_in_schema=False)
async def link_page() -> HTMLResponse:
    return HTMLResponse(LINK_PAGE_HTML)
