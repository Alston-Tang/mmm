from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from analysis.config import get_settings
from analysis.db.repository import (
    AnalysisReviewRepository,
    AnalysisStateRepository,
    AnalyzedTransactionRepository,
    SourceTransactionRepository,
)
from analysis.llm.client import LLMClient
from analysis.models.schemas import (
    AttentionType,
    LLMAnalysisResponse,
    LLMSourceTransactionResult,
    ProcessingStatus,
    TransactionDuration,
)
from analysis.search.client import WebSearchClient
from analysis.source_metadata import source_metadata_from_transaction, source_transaction_date

logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(self) -> None:
        self._llm = LLMClient()
        self._search = WebSearchClient()
        self._settings = get_settings()

    async def run_cycle(self) -> dict[str, Any]:
        """Fetch a batch of unprocessed transactions, analyze via LLM, persist results."""
        settings = self._settings
        batch = await SourceTransactionRepository.list_in_window(
            window_days=settings.analysis_window_days,
            limit=settings.analysis_batch_size,
            exclude_statuses=[ProcessingStatus.RESOLVED, ProcessingStatus.NEEDS_ATTENTION],
        )

        if not batch:
            logger.info("No unprocessed transactions in window (last %d days)", settings.analysis_window_days)
            return {"processed": 0, "results": 0, "resolved": 0, "needs_attention": 0}

        tx_ids = [tx["transaction_id"] for tx in batch]
        logger.info("Analyzing batch of %d transactions: %s...", len(batch), tx_ids[:3])

        try:
            llm_response = await self._llm.analyze_transactions(batch, pass_label="initial")
        except Exception:
            logger.exception("LLM analysis failed for batch")
            return {"processed": 0, "results": 0, "error": "llm_failed"}

        validation_error = self._validate_response(llm_response, tx_ids, batch)
        if validation_error:
            logger.warning("LLM response validation failed: %s — marking batch as needs_attention", validation_error)
            await self._mark_batch_needs_attention(
                tx_ids,
                reason=f"LLM response validation failed: {validation_error}",
                llm_response=llm_response,
                validation_error=validation_error,
            )
            return {
                "processed": len(batch),
                "results": 0,
                "resolved": 0,
                "needs_attention": len(batch),
                "validation_error": validation_error,
            }

        search_retries = 0
        llm_response, search_retries = await self._retry_uncertain_with_search(batch, llm_response)

        stats = await self._apply_response(llm_response, batch)
        stats["processed"] = len(batch)
        stats["search_retries"] = search_retries
        return stats

    async def _retry_uncertain_with_search(
        self,
        batch: list[dict[str, Any]],
        initial_response: LLMAnalysisResponse,
    ) -> tuple[LLMAnalysisResponse, int]:
        """For uncertain results from the first pass, search the web and re-analyze."""
        if not self._search.enabled:
            return initial_response, 0

        confident, uncertain = self._split_results(initial_response)
        if not uncertain:
            return initial_response, 0

        uncertain_tx_ids = {r.transaction_id for r in uncertain}
        uncertain_batch = [tx for tx in batch if tx["transaction_id"] in uncertain_tx_ids]
        if not uncertain_batch:
            return initial_response, 0

        logger.info(
            "First pass uncertain on %d transactions — searching web for context",
            len(uncertain_batch),
        )

        search_context = await self._search.search_for_transactions(uncertain_batch)
        if not search_context.get("search_results"):
            logger.info("No search results; keeping first-pass uncertain results")
            return initial_response, 0

        try:
            retry_response = await self._llm.analyze_transactions(
                uncertain_batch,
                search_context=search_context,
                pass_label="search_retry",
            )
        except Exception:
            logger.exception("LLM search retry failed; keeping first-pass uncertain results")
            return initial_response, 0

        retry_validation = self._validate_response(retry_response, list(uncertain_tx_ids), uncertain_batch)
        if retry_validation:
            logger.warning(
                "Search retry validation failed: %s — keeping first-pass uncertain results",
                retry_validation,
            )
            return initial_response, 0

        merged = LLMAnalysisResponse(results=confident + retry_response.results)
        logger.info(
            "Search retry merged: %d confident + %d retried results",
            len(confident),
            len(retry_response.results),
        )
        return merged, 1

    def _split_results(
        self,
        response: LLMAnalysisResponse,
    ) -> tuple[list[LLMSourceTransactionResult], list[LLMSourceTransactionResult]]:
        threshold = self._settings.confidence_threshold
        confident: list[LLMSourceTransactionResult] = []
        uncertain: list[LLMSourceTransactionResult] = []

        for result in response.results:
            if self._is_uncertain_result(result, threshold):
                uncertain.append(result)
            else:
                confident.append(result)

        return confident, uncertain

    @staticmethod
    def _is_uncertain_result(result: LLMSourceTransactionResult, threshold: float) -> bool:
        if result.action == "needs_attention":
            return True
        if result.action == "create":
            return any(atx.confidence < threshold for atx in result.analyzed_transactions)
        return True

    async def retry_transaction(self, transaction_id: str) -> bool:
        """Reset a needs_attention transaction so it can be reprocessed."""
        return await AnalysisStateRepository.reset_for_retry(transaction_id)

    @staticmethod
    def _validate_response(
        response: LLMAnalysisResponse,
        expected_ids: list[str],
        batch: list[dict[str, Any]] | None = None,
    ) -> str | None:
        batch_by_id = {tx["transaction_id"]: tx for tx in batch} if batch else {}

        seen: set[str] = set()
        for result in response.results:
            tx_id = result.transaction_id
            if tx_id in seen:
                return f"transaction {tx_id} appears in multiple results"
            if tx_id not in expected_ids:
                return f"unknown transaction_id {tx_id} in LLM response"
            seen.add(tx_id)

        missing = set(expected_ids) - seen
        if missing:
            return f"missing transaction_ids: {sorted(missing)}"

        for result in response.results:
            if result.action == "create":
                if not result.analyzed_transactions:
                    return f"transaction {result.transaction_id} has action create but no analyzed_transactions"
                if len(result.analyzed_transactions) != 1:
                    return (
                        f"transaction {result.transaction_id} must have exactly one "
                        f"analyzed transaction, got {len(result.analyzed_transactions)}"
                    )
                if batch_by_id:
                    source = batch_by_id.get(result.transaction_id)
                    if source:
                        data = source.get("data") or {}
                        source_amount = data.get("amount")
                        if source_amount is not None:
                            atx = result.analyzed_transactions[0]
                            if abs(abs(atx.amount_usd) - abs(float(source_amount))) > 0.02:
                                return (
                                    f"transaction {result.transaction_id} amount_usd "
                                    f"({atx.amount_usd}) does not match source amount ({source_amount})"
                                )
            elif result.action == "needs_attention":
                if not result.attention_reason:
                    return f"transaction {result.transaction_id} needs attention_reason"

        return None

    async def _apply_response(
        self,
        response: LLMAnalysisResponse,
        batch: list[dict[str, Any]],
    ) -> dict[str, Any]:
        batch_by_id = {tx["transaction_id"]: tx for tx in batch}
        resolved = 0
        needs_attention = 0
        analyzed_count = 0
        reviews_created = 0

        for result in response.results:
            analysis_id = str(uuid.uuid4())
            tx_id = result.transaction_id

            if result.action == "needs_attention":
                source_tx = batch_by_id.get(tx_id)
                review_id = await self._save_review(
                    analysis_id=analysis_id,
                    source_transaction_id=tx_id,
                    attention_type=AttentionType.LLM_FLAGGED,
                    attention_reason=result.attention_reason or "LLM flagged for human review",
                    llm_result=result,
                    source_metadata=source_metadata_from_transaction(source_tx) if source_tx else None,
                )
                await AnalysisStateRepository.upsert(
                    tx_id,
                    status=ProcessingStatus.NEEDS_ATTENTION,
                    analysis_id=analysis_id,
                    attention_reason=result.attention_reason,
                )
                needs_attention += 1
                reviews_created += 1
                logger.info("Saved review %s for LLM-flagged transaction %s", review_id, tx_id)
                continue

            low_confidence = [
                atx for atx in result.analyzed_transactions
                if atx.confidence < self._settings.confidence_threshold
            ]
            if low_confidence:
                worst = min(low_confidence, key=lambda a: a.confidence)
                attention_reason = f"Low confidence ({worst.confidence:.2f}): {worst.description}"
                review_id = await self._save_review(
                    analysis_id=analysis_id,
                    source_transaction_id=tx_id,
                    attention_type=AttentionType.LOW_CONFIDENCE,
                    attention_reason=attention_reason,
                    llm_result=result,
                    confidence=worst.confidence,
                    source_metadata=source_metadata_from_transaction(batch_by_id[tx_id])
                    if tx_id in batch_by_id
                    else None,
                )
                await AnalysisStateRepository.upsert(
                    tx_id,
                    status=ProcessingStatus.NEEDS_ATTENTION,
                    analysis_id=analysis_id,
                    confidence=worst.confidence,
                    attention_reason=attention_reason,
                )
                needs_attention += 1
                reviews_created += 1
                logger.info("Saved review %s for low-confidence transaction %s", review_id, tx_id)
                continue

            docs: list[dict[str, Any]] = []
            now = datetime.now(UTC)
            min_confidence = min(atx.confidence for atx in result.analyzed_transactions)
            analyzed_ids: list[str] = []

            source_tx = batch_by_id.get(tx_id)
            source_meta = source_metadata_from_transaction(source_tx) if source_tx else None
            tx_date = source_transaction_date(source_tx)
            if not tx_date and result.analyzed_transactions:
                tx_date = result.analyzed_transactions[0].transaction_date

            for atx in result.analyzed_transactions:
                analyzed_id = str(uuid.uuid4())
                analyzed_ids.append(analyzed_id)

                duration = None
                if atx.duration_value is not None and atx.duration_unit is not None:
                    duration = TransactionDuration(value=atx.duration_value, unit=atx.duration_unit)

                docs.append(
                    {
                        "analyzed_transaction_id": analyzed_id,
                        "source_transaction_id": tx_id,
                        "analysis_id": analysis_id,
                        "flow_direction": atx.flow_direction.value,
                        "amount_usd": atx.amount_usd,
                        "original_amount": atx.original_amount,
                        "original_currency": atx.original_currency,
                        "category": atx.category,
                        "is_subscription": atx.is_subscription,
                        "description": atx.description,
                        "transaction_date": tx_date or atx.transaction_date,
                        "source_metadata": source_meta,
                        "duration": duration.model_dump() if duration else None,
                        "confidence": atx.confidence,
                        "analysis_version": "v1",
                        "llm_reasoning": atx.reasoning,
                        "created_at": now,
                    }
                )

            await AnalyzedTransactionRepository.insert_many(docs)
            analyzed_count += len(docs)

            await AnalysisStateRepository.upsert(
                tx_id,
                status=ProcessingStatus.RESOLVED,
                analyzed_transaction_ids=analyzed_ids,
                analysis_id=analysis_id,
                confidence=min_confidence,
            )
            resolved += 1

        return {
            "results": len(response.results),
            "resolved": resolved,
            "needs_attention": needs_attention,
            "analyzed_transactions_created": analyzed_count,
            "reviews_created": reviews_created,
        }

    async def _save_review(
        self,
        *,
        analysis_id: str,
        source_transaction_id: str,
        attention_type: AttentionType,
        attention_reason: str,
        llm_result: LLMSourceTransactionResult | None = None,
        llm_response: LLMAnalysisResponse | None = None,
        validation_error: str | None = None,
        confidence: float | None = None,
        search_context: dict[str, Any] | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> str:
        review_id = str(uuid.uuid4())
        doc: dict[str, Any] = {
            "review_id": review_id,
            "analysis_id": analysis_id,
            "source_transaction_id": source_transaction_id,
            "attention_type": attention_type.value,
            "attention_reason": attention_reason,
            "created_at": datetime.now(UTC),
        }
        if confidence is not None:
            doc["confidence"] = confidence
        if llm_result is not None:
            doc["llm_result"] = llm_result.model_dump(mode="json")
        if llm_response is not None:
            doc["llm_response"] = llm_response.model_dump(mode="json")
        if validation_error is not None:
            doc["validation_error"] = validation_error
        if search_context is not None:
            doc["search_context"] = search_context
        if source_metadata is not None:
            doc["source_metadata"] = source_metadata

        await AnalysisReviewRepository.insert(doc)
        return review_id

    async def _mark_batch_needs_attention(
        self,
        tx_ids: list[str],
        reason: str,
        *,
        llm_response: LLMAnalysisResponse | None = None,
        validation_error: str | None = None,
    ) -> None:
        source_txs = {
            tx["transaction_id"]: tx
            for tx in await SourceTransactionRepository.get_by_ids(tx_ids)
        }
        for tx_id in tx_ids:
            analysis_id = str(uuid.uuid4())
            source_tx = source_txs.get(tx_id)
            await self._save_review(
                analysis_id=analysis_id,
                source_transaction_id=tx_id,
                attention_type=AttentionType.VALIDATION_FAILED,
                attention_reason=reason,
                llm_response=llm_response,
                validation_error=validation_error,
                source_metadata=source_metadata_from_transaction(source_tx) if source_tx else None,
            )
            await AnalysisStateRepository.upsert(
                tx_id,
                status=ProcessingStatus.NEEDS_ATTENTION,
                analysis_id=analysis_id,
                attention_reason=reason,
            )

    async def get_status(self) -> dict[str, Any]:
        settings = self._settings
        status_counts = await AnalysisStateRepository.count_by_status()
        total_in_window = await SourceTransactionRepository.count_in_window(settings.analysis_window_days)
        analyzed_count = await AnalyzedTransactionRepository.count()
        review_count = await AnalysisReviewRepository.count()

        tracked = sum(status_counts.values())
        pending = max(0, total_in_window - status_counts.get(ProcessingStatus.RESOLVED.value, 0)
                      - status_counts.get(ProcessingStatus.NEEDS_ATTENTION.value, 0))

        return {
            "window_days": settings.analysis_window_days,
            "total_in_window": total_in_window,
            "tracked": tracked,
            "pending_estimate": pending,
            "by_status": status_counts,
            "analyzed_transactions_total": analyzed_count,
            "reviews_total": review_count,
            "confidence_threshold": settings.confidence_threshold,
            "search_enabled": self._search.enabled,
        }
