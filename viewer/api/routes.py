from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from common.categories import merge_category_options
from viewer.api.schemas import (
    AnalyzedTransactionItem,
    FilterOptionsResponse,
    HealthResponse,
    MonthListResponse,
    MonthSummaryResponse,
    MonthCategoryTransactionsResponse,
    RequeueRequest,
    RequeueResponse,
    SortField,
    SortOrder,
    SourceTransactionResponse,
    TransactionListResponse,
    TransactionViewItem,
    ViewFilter,
)
from viewer.config import get_settings
from viewer.db.mongo import ping_database
from viewer.db.repository import (
    AnalyzedTransactionViewerRepository,
    MonthSummaryRepository,
    NeedsAttentionViewerRepository,
    PendingRetryViewerRepository,
    SourceTransactionViewerRepository,
    TransactionFeedbackRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

PENDING_RETRY_STATUS = "pending_retry"
_MERGE_FETCH_CAP = 10_000


def _apply_analysis_state(
    item: dict[str, Any],
    state: dict[str, Any] | None,
) -> None:
    if not state:
        return
    status = state.get("status")
    comment = (state.get("user_comment") or "").strip() or None
    item["analysis_status"] = status
    item["user_comment"] = comment
    item["pending_reanalysis"] = status == PENDING_RETRY_STATUS


def _to_view_item(doc: dict[str, Any]) -> TransactionViewItem:
    kind = doc.get("kind", "analyzed")
    source_id = doc.get("source_transaction_id")
    if not source_id:
        ids = doc.get("source_transaction_ids") or []
        source_id = ids[0] if ids else None

    needs_attention = kind == "needs_attention"
    pending_reanalysis = kind == "pending_retry" or bool(doc.get("pending_reanalysis"))

    return TransactionViewItem(
        kind=kind,
        source_transaction_id=source_id,
        analyzed_transaction_id=doc.get("analyzed_transaction_id"),
        analysis_id=doc.get("analysis_id") or doc.get("group_id"),
        review_id=doc.get("review_id"),
        flow_direction=doc.get("flow_direction"),
        amount_usd=doc.get("amount_usd"),
        original_amount=doc.get("original_amount"),
        original_currency=doc.get("original_currency"),
        category=doc.get("category"),
        is_subscription=doc.get("is_subscription", False),
        description=doc["description"],
        transaction_date=doc.get("transaction_date"),
        attention_reason=doc.get("attention_reason"),
        attention_type=doc.get("attention_type"),
        source_metadata=doc.get("source_metadata"),
        duration=doc.get("duration"),
        confidence=doc.get("confidence"),
        user_comment=doc.get("user_comment"),
        analysis_status=doc.get("analysis_status"),
        pending_reanalysis=pending_reanalysis,
        needs_attention=needs_attention,
        source_available=doc.get("source_available", True),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


def _sort_key(item: dict[str, Any], sort_by: SortField) -> Any:
    if sort_by == "updated_at":
        return item.get("updated_at") or ""
    if sort_by == "amount_usd":
        return item.get("amount_usd") or 0
    if sort_by == "category":
        return item.get("category") or ""
    if sort_by == "confidence":
        return item.get("confidence") or 0
    if sort_by == "created_at":
        return item.get("created_at") or ""
    return item.get("transaction_date") or ""


def _merge_and_page(
    docs: list[dict[str, Any]],
    *,
    sort_by: SortField,
    sort_order: SortOrder,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    reverse = sort_order == "desc"
    docs.sort(key=lambda item: _sort_key(item, sort_by), reverse=reverse)
    total = len(docs)
    return docs[offset : offset + limit], total


def _tag_docs(docs: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    tagged: list[dict[str, Any]] = []
    for doc in docs:
        item = dict(doc)
        item["kind"] = kind
        tagged.append(item)
    return tagged


async def _enrich_with_state(docs: list[dict[str, Any]]) -> None:
    source_ids = [
        doc.get("source_transaction_id")
        for doc in docs
        if doc.get("source_transaction_id")
    ]
    state_by_id = await PendingRetryViewerRepository.get_status_by_source_ids(source_ids)
    for doc in docs:
        sid = doc.get("source_transaction_id")
        if sid:
            _apply_analysis_state(doc, state_by_id.get(sid))


async def _enrich_source_availability(docs: list[dict[str, Any]]) -> None:
    source_ids = list(
        {doc.get("source_transaction_id") for doc in docs if doc.get("source_transaction_id")},
    )
    existing = await TransactionFeedbackRepository.existing_source_transaction_ids(source_ids)
    for doc in docs:
        sid = doc.get("source_transaction_id")
        doc["source_available"] = bool(sid and sid in existing)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        await ping_database()
        mongo_status = "ok"
    except Exception as exc:
        mongo_status = f"error: {exc}"
    return HealthResponse(
        status="ok" if mongo_status == "ok" else "degraded",
        mongodb=mongo_status,
    )


@router.get("/filters", response_model=FilterOptionsResponse)
async def filter_options() -> FilterOptionsResponse:
    stored = await AnalyzedTransactionViewerRepository.distinct_categories()
    categories = merge_category_options(stored)
    flow_directions = await AnalyzedTransactionViewerRepository.distinct_flow_directions()
    return FilterOptionsResponse(categories=categories, flow_directions=flow_directions)


@router.get("/months", response_model=MonthListResponse)
async def list_months() -> MonthListResponse:
    months = await MonthSummaryRepository.list_months()
    return MonthListResponse(months=months)


@router.get("/months/{month}", response_model=MonthSummaryResponse)
async def get_month_summary(month: str) -> MonthSummaryResponse:
    try:
        summary = await MonthSummaryRepository.get_month_summary(month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MonthSummaryResponse(**summary)


@router.get("/months/{month}/transactions", response_model=MonthCategoryTransactionsResponse)
async def list_month_category_transactions(
    month: str,
    flow_direction: str = Query(..., pattern="^(addition|reduction|transfer)$"),
    category: str = Query(..., min_length=1),
) -> MonthCategoryTransactionsResponse:
    try:
        items = await MonthSummaryRepository.list_category_transactions(
            month,
            flow_direction=flow_direction,
            category=category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MonthCategoryTransactionsResponse(
        month=month,
        flow_direction=flow_direction,
        category=category,
        items=items,
    )


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    date_from: str | None = Query(None, description="ISO date YYYY-MM-DD (inclusive)"),
    date_to: str | None = Query(None, description="ISO date YYYY-MM-DD (inclusive)"),
    category: str | None = None,
    flow_direction: str | None = None,
    is_subscription: bool | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    min_confidence: float | None = Query(None, ge=0, le=1),
    q: str | None = Query(None, description="Search description, merchant, account"),
    view: ViewFilter | None = Query(
        None,
        description="analyzed | needs_attention | pending_retry; omit for all",
    ),
    needs_attention: bool | None = Query(
        None,
        deprecated=True,
        description="Legacy filter; use view=needs_attention or view=analyzed instead",
    ),
    sort_by: SortField = "transaction_date",
    sort_order: SortOrder = "desc",
    limit: int | None = None,
    offset: int = Query(0, ge=0),
    focus_analyzed_transaction_id: str | None = Query(
        None,
        description="Jump to the page containing this analyzed transaction",
    ),
) -> TransactionListResponse:
    settings = get_settings()
    page_size = limit if limit is not None else settings.default_page_size
    page_size = min(max(page_size, 1), settings.max_page_size)

    if view is None and needs_attention is True:
        view = "needs_attention"
    elif view is None and needs_attention is False:
        view = "analyzed"

    analyzed_sort = sort_by if sort_by != "updated_at" else "transaction_date"
    resolved_focus: str | None = None
    if focus_analyzed_transaction_id:
        view = "analyzed"
        page_offset = await AnalyzedTransactionViewerRepository.find_page_offset(
            focus_analyzed_transaction_id,
            sort_by=analyzed_sort,
            sort_order=sort_order,
            date_from=date_from,
            date_to=date_to,
            category=category,
            flow_direction=flow_direction,
            is_subscription=is_subscription,
            min_amount=min_amount,
            max_amount=max_amount,
            min_confidence=min_confidence,
            limit=page_size,
        )
        if page_offset is None:
            raise HTTPException(status_code=404, detail="Transaction not found")
        offset = page_offset
        resolved_focus = focus_analyzed_transaction_id

    merged_docs: list[dict[str, Any]] = []
    analyzed_total = 0
    needs_attention_total = 0
    pending_retry_total = 0

    if view in (None, "analyzed", "needs_attention", "pending_retry"):
        if view in (None, "needs_attention"):
            na_limit = page_size if view == "needs_attention" else _MERGE_FETCH_CAP
            na_offset = offset if view == "needs_attention" else 0
            na_docs, needs_attention_total = await NeedsAttentionViewerRepository.list_needs_attention(
                q=q,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=na_limit,
                offset=na_offset,
            )
            if view == "needs_attention":
                merged_docs = _tag_docs(na_docs, "needs_attention")
            elif view is None:
                merged_docs.extend(_tag_docs(na_docs, "needs_attention"))

        if view in (None, "pending_retry"):
            pr_limit = page_size if view == "pending_retry" else _MERGE_FETCH_CAP
            pr_offset = offset if view == "pending_retry" else 0
            pr_docs, pending_retry_total = await PendingRetryViewerRepository.list_pending_retry(
                q=q,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=pr_limit,
                offset=pr_offset,
            )
            if view == "pending_retry":
                merged_docs = _tag_docs(pr_docs, "pending_retry")
            elif view is None:
                merged_docs.extend(_tag_docs(pr_docs, "pending_retry"))

        if view in (None, "analyzed"):
            az_limit = page_size if view == "analyzed" else _MERGE_FETCH_CAP
            az_offset = offset if view == "analyzed" else 0
            analyzed_docs, analyzed_total = await AnalyzedTransactionViewerRepository.list_transactions(
                date_from=date_from,
                date_to=date_to,
                category=category,
                flow_direction=flow_direction,
                is_subscription=is_subscription,
                min_amount=min_amount,
                max_amount=max_amount,
                min_confidence=min_confidence,
                q=q,
                sort_by=analyzed_sort,
                sort_order=sort_order,
                limit=az_limit,
                offset=az_offset,
            )
            if view == "analyzed":
                merged_docs = _tag_docs(analyzed_docs, "analyzed")
            elif view is None:
                merged_docs.extend(_tag_docs(analyzed_docs, "analyzed"))

    await _enrich_with_state(merged_docs)
    await _enrich_source_availability(merged_docs)

    if view is None:
        page_docs, total = _merge_and_page(
            merged_docs,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=page_size,
            offset=offset,
        )
    elif view == "analyzed":
        total = analyzed_total
        page_docs = merged_docs
    elif view == "needs_attention":
        total = needs_attention_total
        page_docs = merged_docs
    else:
        total = pending_retry_total
        page_docs = merged_docs

    return TransactionListResponse(
        items=[_to_view_item(d) for d in page_docs],
        total=total,
        analyzed_total=analyzed_total,
        needs_attention_total=needs_attention_total,
        pending_retry_total=pending_retry_total,
        limit=page_size,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        focus_analyzed_transaction_id=resolved_focus,
    )


@router.get("/transactions/{analyzed_transaction_id}", response_model=AnalyzedTransactionItem)
async def get_transaction(analyzed_transaction_id: str) -> AnalyzedTransactionItem:
    doc = await AnalyzedTransactionViewerRepository.get_by_id(analyzed_transaction_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Transaction not found")
    doc["kind"] = "analyzed"
    source_id = doc.get("source_transaction_id")
    if source_id:
        states = await PendingRetryViewerRepository.get_status_by_source_ids([source_id])
        _apply_analysis_state(doc, states.get(source_id))
    item = _to_view_item(doc)
    return AnalyzedTransactionItem(**item.model_dump())


@router.get("/source-transactions/{transaction_id}", response_model=SourceTransactionResponse)
async def get_source_transaction(transaction_id: str) -> SourceTransactionResponse:
    doc = await SourceTransactionViewerRepository.get_by_id(transaction_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Source transaction not found")
    return SourceTransactionResponse(**doc)


@router.post("/transactions/requeue", response_model=RequeueResponse)
async def requeue_transaction(body: RequeueRequest) -> RequeueResponse:
    if not body.source_transaction_id and not body.analyzed_transaction_id:
        raise HTTPException(
            status_code=400,
            detail="Provide source_transaction_id or analyzed_transaction_id",
        )

    source_id = await TransactionFeedbackRepository.resolve_source_transaction_id(
        source_transaction_id=body.source_transaction_id,
        analyzed_transaction_id=body.analyzed_transaction_id,
    )
    if not source_id:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if not await TransactionFeedbackRepository.source_transaction_exists(source_id):
        raise HTTPException(
            status_code=404,
            detail=(
                "Source transaction no longer exists. It may have been replaced when the "
                "charge posted; re-queue the posted transaction instead."
            ),
        )

    try:
        result = await TransactionFeedbackRepository.submit_comment(
            source_transaction_id=source_id,
            comment=body.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info(
        "Queued %s for re-analysis with user comment (%d chars)",
        source_id,
        len(body.comment),
    )
    return RequeueResponse(**result)
