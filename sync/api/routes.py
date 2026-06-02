from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from sync.api.schemas import (
    AccountResponse,
    HealthResponse,
    ItemResponse,
    LinkExchangeRequest,
    LinkExchangeResponse,
    LinkTokenResponse,
    SyncTriggerResponse,
    WeChatUploadResponse,
)
from sync.db.mongo import get_database
from sync.db.repository import AccountRepository, ItemRepository, TransactionRepository
from sync.db.wechat_repository import WeChatTransactionRepository
from sync.plaid.link import create_link_token, exchange_public_token
from sync.sync.service import sync_all_items, sync_item
from sync.wechat.parser import WeChatBillParseError, parse_wechat_bill
from sync.worker.sync_worker import SyncWorker

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
        item_id = item["item_id"]
        tx_count = await TransactionRepository.count_for_item(item_id)
        acct_count = len(await AccountRepository.list_for_item(item_id))
        result.append(
            ItemResponse(
                item_id=item_id,
                label=item["label"],
                institution_name=item.get("institution_name"),
                status=item["status"],
                created_at=item.get("created_at"),
                last_sync_at=item.get("last_sync_at"),
                last_sync_error=item.get("last_sync_error"),
                transaction_count=tx_count,
                account_count=acct_count,
            )
        )
    return result


def _to_account_response(doc: dict) -> AccountResponse:
    return AccountResponse(
        account_id=doc["account_id"],
        item_id=doc["item_id"],
        item_label=doc.get("item_label"),
        display_name=doc.get("display_name"),
        name=doc.get("name"),
        official_name=doc.get("official_name"),
        type=doc.get("type"),
        subtype=doc.get("subtype"),
        mask=doc.get("mask"),
        institution_name=doc.get("institution_name"),
        current_balance=doc.get("current_balance"),
        updated_at=doc.get("updated_at"),
    )


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(account_id: str) -> AccountResponse:
    doc = await AccountRepository.get_by_account_id(account_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Account not found")
    return _to_account_response(doc)


@router.get("/items/{item_id}/accounts", response_model=list[AccountResponse])
async def list_item_accounts(item_id: str) -> list[AccountResponse]:
    item = await ItemRepository.get_by_item_id(item_id)
    if not item or item.get("status") != "active":
        raise HTTPException(status_code=404, detail="Item not found")
    accounts = await AccountRepository.list_for_item(item_id)
    return [_to_account_response(a) for a in accounts]


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
  <p><a href="/api/v1/wechat">Upload WeChat transactions</a></p>
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


WECHAT_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>MMM — Upload WeChat transactions</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }
    input, button { font-size: 1rem; padding: 0.45rem; margin: 0.25rem 0; width: 100%; box-sizing: border-box; }
    pre { background: #f4f4f4; padding: 1rem; overflow-x: auto; font-size: 0.85rem; white-space: pre-wrap; }
    .ok { color: #060; }
    .err { color: #a00; }
    .meta { color: #666; font-size: 0.9rem; }
    a { color: #0366d6; }
  </style>
</head>
<body>
  <h1>Upload WeChat transactions</h1>
  <p class="meta">
    Import a personal WeChat Pay bill XLSX (from 微信 → 服务 → 钱包 → 账单 → 下载账单).
    These records are stored separately and used as context when analyzing credit card charges.
  </p>
  <p><a href="/api/v1/link">Link bank account</a></p>
  <form id="upload-form">
    <label>WeChat bill XLSX<input type="file" id="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required /></label>
    <button type="submit">Upload</button>
  </form>
  <div id="out"></div>
  <script>
    const api = window.location.origin;
    document.getElementById('upload-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const fileInput = document.getElementById('file');
      const out = document.getElementById('out');
      if (!fileInput.files.length) return;
      const file = fileInput.files[0];
      out.innerHTML = '<p>Uploading…</p>';
      const form = new FormData();
      form.append('file', file);
      try {
        const res = await fetch(api + '/api/v1/wechat/upload', { method: 'POST', body: form });
        const data = await res.json();
        if (!res.ok) {
          out.innerHTML = '<pre class="err">' + JSON.stringify(data, null, 2) + '</pre>';
          return;
        }
        out.innerHTML = '<pre class="ok">' + JSON.stringify(data, null, 2) + '</pre>';
      } catch (err) {
        out.innerHTML = '<pre class="err">' + err + '</pre>';
      }
    });
  </script>
</body>
</html>"""


@router.get("/wechat", response_class=HTMLResponse, include_in_schema=False)
async def wechat_upload_page() -> HTMLResponse:
    return HTMLResponse(WECHAT_PAGE_HTML)


@router.post("/wechat/upload", response_model=WeChatUploadResponse)
async def upload_wechat_bill(file: UploadFile = File(...)) -> WeChatUploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    lower_name = file.filename.lower()
    if not (lower_name.endswith(".xlsx") or lower_name.endswith(".csv")):
        raise HTTPException(status_code=400, detail="Only XLSX or CSV WeChat bill files are supported")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        parsed = parse_wechat_bill(raw, filename=file.filename)
    except WeChatBillParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    import_id = str(uuid.uuid4())
    stats = await WeChatTransactionRepository.insert_import_batch(
        import_id=import_id,
        source_filename=file.filename,
        transactions=parsed,
    )
    dates = sorted({tx.transaction_date for tx in parsed})
    stored_total = await WeChatTransactionRepository.count()

    return WeChatUploadResponse(
        import_id=import_id,
        filename=file.filename,
        inserted=stats["inserted"],
        skipped_duplicates=stats["skipped_duplicates"],
        total_in_file=stats["total_in_file"],
        stored_total=stored_total,
        date_from=dates[0] if dates else None,
        date_to=dates[-1] if dates else None,
    )


@router.get("/wechat/transactions")
async def list_wechat_transactions(limit: int = 50) -> list[dict]:
    return await WeChatTransactionRepository.list_recent(limit=min(limit, 200))
