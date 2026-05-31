from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from analysis.api.schemas import (
    AnalysisReviewResponse,
    AnalysisStatusResponse,
    AnalysisTriggerResponse,
    AnalyzedTransactionResponse,
    HealthResponse,
    NeedsAttentionItem,
    RetryResponse,
)
from analysis.db.mongo import ping_database
from analysis.db.repository import (
    AnalysisReviewRepository,
    AnalysisStateRepository,
    AnalyzedTransactionRepository,
)
from analysis.engine.service import AnalysisService
from analysis.worker.analysis_worker import AnalysisWorker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def _source_transaction_id(doc: dict) -> str:
    if doc.get("source_transaction_id"):
        return doc["source_transaction_id"]
    ids = doc.get("source_transaction_ids") or []
    return ids[0] if ids else ""


def _analysis_id(doc: dict) -> str:
    return doc.get("analysis_id") or doc.get("group_id") or ""


def _to_analyzed_response(doc: dict) -> AnalyzedTransactionResponse:
    return AnalyzedTransactionResponse(
        analyzed_transaction_id=doc["analyzed_transaction_id"],
        source_transaction_id=_source_transaction_id(doc),
        analysis_id=_analysis_id(doc),
        flow_direction=doc["flow_direction"],
        amount_usd=doc["amount_usd"],
        original_amount=doc.get("original_amount"),
        original_currency=doc.get("original_currency"),
        category=doc["category"],
        is_subscription=doc.get("is_subscription", False),
        description=doc["description"],
        transaction_date=doc["transaction_date"],
        source_metadata=doc.get("source_metadata"),
        duration=doc.get("duration"),
        confidence=doc["confidence"],
        created_at=doc.get("created_at"),
    )


def get_worker(request: Request) -> AnalysisWorker:
    return request.app.state.analysis_worker


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


@router.get("/status", response_model=AnalysisStatusResponse)
async def analysis_status() -> AnalysisStatusResponse:
    status = await AnalysisService().get_status()
    return AnalysisStatusResponse(**status)


@router.post("/analyze", response_model=AnalysisTriggerResponse)
async def trigger_analysis(request: Request) -> AnalysisTriggerResponse:
    get_worker(request).trigger_now()
    service = AnalysisService()
    result = await service.run_cycle()
    return AnalysisTriggerResponse(result=result)


@router.get("/analyzed", response_model=list[AnalyzedTransactionResponse])
async def list_analyzed(limit: int = 50) -> list[AnalyzedTransactionResponse]:
    docs = await AnalyzedTransactionRepository.list_recent(limit=limit)
    return [_to_analyzed_response(d) for d in docs]


@router.get("/analyzed/{transaction_id}", response_model=list[AnalyzedTransactionResponse])
async def get_analyzed_for_source(transaction_id: str) -> list[AnalyzedTransactionResponse]:
    docs = await AnalyzedTransactionRepository.get_by_source_id(transaction_id)
    if not docs:
        raise HTTPException(status_code=404, detail="No analyzed transactions for this source")
    return [_to_analyzed_response(d) for d in docs]


@router.get("/needs-attention", response_model=list[NeedsAttentionItem])
async def list_needs_attention(limit: int = 100) -> list[NeedsAttentionItem]:
    docs = await AnalysisStateRepository.list_needs_attention(limit=limit)
    return [
        NeedsAttentionItem(
            transaction_id=d["transaction_id"],
            attention_reason=d.get("attention_reason"),
            analysis_id=d.get("analysis_id") or d.get("group_id"),
            updated_at=d.get("updated_at"),
        )
        for d in docs
    ]


def _to_review_response(doc: dict) -> AnalysisReviewResponse:
    source_id = doc.get("source_transaction_id")
    if not source_id:
        ids = doc.get("source_transaction_ids") or []
        source_id = ids[0] if ids else ""
    return AnalysisReviewResponse(
        review_id=doc["review_id"],
        analysis_id=_analysis_id(doc),
        source_transaction_id=source_id,
        attention_type=doc["attention_type"],
        attention_reason=doc["attention_reason"],
        confidence=doc.get("confidence"),
        llm_result=doc.get("llm_result") or doc.get("llm_group"),
        llm_response=doc.get("llm_response"),
        validation_error=doc.get("validation_error"),
        search_context=doc.get("search_context"),
        source_metadata=doc.get("source_metadata"),
        created_at=doc.get("created_at"),
    )


@router.get("/reviews", response_model=list[AnalysisReviewResponse])
async def list_reviews(limit: int = 50) -> list[AnalysisReviewResponse]:
    docs = await AnalysisReviewRepository.list_recent(limit=limit)
    return [_to_review_response(d) for d in docs]


@router.get("/reviews/by-source/{transaction_id}", response_model=list[AnalysisReviewResponse])
async def get_reviews_for_source(transaction_id: str) -> list[AnalysisReviewResponse]:
    docs = await AnalysisReviewRepository.get_by_source_id(transaction_id)
    if not docs:
        raise HTTPException(status_code=404, detail="No reviews for this source transaction")
    return [_to_review_response(d) for d in docs]


@router.get("/reviews/{review_id}", response_model=AnalysisReviewResponse)
async def get_review(review_id: str) -> AnalysisReviewResponse:
    doc = await AnalysisReviewRepository.get_by_review_id(review_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Review not found")
    return _to_review_response(doc)


@router.post("/retry/{transaction_id}", response_model=RetryResponse)
async def retry_transaction(transaction_id: str, request: Request) -> RetryResponse:
    service = AnalysisService()
    reset = await service.retry_transaction(transaction_id)
    if not reset:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found in needs_attention state",
        )
    get_worker(request).trigger_now()
    return RetryResponse(transaction_id=transaction_id, reset=True)


@router.get("/categories")
async def list_categories() -> dict[str, list[str]]:
    from analysis.categories import PREDEFINED_CATEGORIES

    return {"categories": PREDEFINED_CATEGORIES}
