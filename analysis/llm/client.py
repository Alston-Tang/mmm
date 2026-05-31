from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from analysis.categories import PREDEFINED_CATEGORIES
from analysis.config import get_settings
from analysis.models.schemas import LLMAnalysisResponse

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)

SYSTEM_PROMPT = """You are a financial transaction analyst. You receive raw bank transactions from Plaid and analyze each one independently.

For EACH source transaction, either:
- Create exactly ONE normalized analyzed transaction (action: "create"), OR
- Mark it as needing human attention (action: "needs_attention") if confidence is low or the situation is ambiguous.

Rules:
- Return exactly one result entry per input transaction_id.
- Every input transaction_id must appear exactly once in results.
- Each source transaction maps to exactly ONE analyzed transaction — do NOT split a charge across multiple categories or multiple analyzed records.
- Assign the full transaction amount to a single best-fit category, even if the purchase mixed multiple item types.
- Do NOT merge or group multiple source transactions together — analyze each independently.
- Be CONSERVATIVE: if unsure about category, flow direction, or amount, use action "needs_attention" instead of guessing.
- confidence must reflect your certainty (0.0 to 1.0). Use needs_attention when confidence < {confidence_threshold}.

For the analyzed transaction, determine:
- flow_direction: "reduction" (money out/consumption), "addition" (money in like payroll), or "transfer" (between accounts or payment-platform settlement)
- amount_usd: the full source transaction amount in USD (convert from other currencies using reasonable exchange rates for the transaction date)
- original_amount / original_currency: if not USD
- category: exactly ONE category from the predefined list — the type of spending (e.g. entertainment for Netflix, food for a meal kit). Do NOT use "subscription" as a category.
- is_subscription: true if this charge is from an auto-renewing recurring subscription (e.g. Netflix, Spotify, Amazon Prime, Bilibili membership); false for one-time purchases
- description: concise human-readable summary
- transaction_date: ISO date (YYYY-MM-DD), usually same as the source transaction date
- duration: optional billing period when is_subscription is true (e.g. monthly -> value=1, unit="month"; yearly -> value=1, unit="year")

Predefined categories:
{categories}

Plaid amount convention: positive amount = money leaving the account, negative = money entering.

Respond with valid JSON matching this schema:
{{
  "results": [
    {{
      "transaction_id": "id1",
      "action": "create" | "needs_attention",
      "attention_reason": "only if needs_attention",
      "analyzed_transactions": [
        {{
          "flow_direction": "reduction",
          "amount_usd": 12.34,
          "original_amount": null,
          "original_currency": null,
          "category": "food",
          "is_subscription": false,
          "description": "Lunch at restaurant",
          "transaction_date": "2026-05-28",
          "duration_value": null,
          "duration_unit": null,
          "confidence": 0.95,
          "reasoning": "Clear restaurant charge"
        }}
      ]
    }}
  ]
}}

The analyzed_transactions array must contain exactly one entry when action is "create".
Every analyzed transaction MUST include "confidence" (0.0 to 1.0). Use duration_value and duration_unit for billing periods, not a duration object."""


class LLMClient:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def analyze_transactions(
        self,
        transactions: list[dict[str, Any]],
        *,
        search_context: dict[str, Any] | None = None,
        pass_label: str = "initial",
    ) -> LLMAnalysisResponse:
        if not transactions:
            return LLMAnalysisResponse(results=[])

        system = SYSTEM_PROMPT.format(
            confidence_threshold=self._settings.confidence_threshold,
            categories="\n".join(f"- {c}" for c in PREDEFINED_CATEGORIES),
        )
        user_payload = self._format_user_payload(transactions, search_context)
        tx_ids = [tx.get("transaction_id") for tx in transactions]
        logger.info(
            "LLM analyze request (%s): model=%s transactions=%d ids=%s search=%s",
            pass_label,
            self._settings.llm_model,
            len(transactions),
            tx_ids,
            bool(search_context and search_context.get("search_results")),
        )
        logger.debug("LLM input (system):\n%s", system)
        logger.info("LLM input (user):\n%s", user_payload)
        raw = await self._chat_completion(system, user_payload)
        logger.info("LLM output (%s):\n%s", pass_label, raw)
        return self._parse_response(raw)

    @staticmethod
    def _format_user_payload(
        transactions: list[dict[str, Any]],
        search_context: dict[str, Any] | None,
    ) -> str:
        payload: dict[str, Any] = {
            "transactions": LLMClient._simplify_transactions(transactions),
        }
        if search_context and search_context.get("search_results"):
            payload["web_search_context"] = search_context["search_results"]
            payload["_note"] = (
                "web_search_context contains internet search results for ambiguous merchants. "
                "Use this to clarify transaction type, category, and duration. "
                "Increase confidence if search results are conclusive."
            )
        return json.dumps(payload, indent=2)

    @staticmethod
    def _simplify_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        simplified = []
        for tx in transactions:
            data = tx.get("data") or {}
            simplified.append(
                {
                    "transaction_id": tx.get("transaction_id"),
                    "date": data.get("date"),
                    "amount": data.get("amount"),
                    "name": data.get("name"),
                    "merchant_name": data.get("merchant_name"),
                    "original_description": data.get("original_description"),
                    "pending": data.get("pending"),
                    "iso_currency_code": data.get("iso_currency_code"),
                    "payment_channel": data.get("payment_channel"),
                    "account_display_name": tx.get("account_display_name"),
                    "account_type": tx.get("account_type"),
                    "account_subtype": tx.get("account_subtype"),
                    "personal_finance_category": data.get("personal_finance_category"),
                    "pending_transaction_id": data.get("pending_transaction_id"),
                }
            )
        return simplified

    async def _chat_completion(self, system: str, user: str) -> str:
        url = f"{self._settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": self._settings.llm_max_tokens,
        }
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.error(
                "LLM request failed: %s\nLLM input (user):\n%s",
                exc,
                user,
            )
            raise

        elapsed = time.monotonic() - started
        content, finish_reason = self._extract_message_content(data)
        usage = data.get("usage")
        if usage:
            logger.info(
                "LLM request completed in %.2fs finish_reason=%s "
                "(prompt_tokens=%s completion_tokens=%s total_tokens=%s)",
                elapsed,
                finish_reason,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                usage.get("total_tokens"),
            )
        else:
            logger.info(
                "LLM request completed in %.2fs finish_reason=%s",
                elapsed,
                finish_reason,
            )

        if finish_reason == "length":
            logger.warning(
                "LLM output was truncated (finish_reason=length). "
                "Increase LLM_MAX_TOKENS or reduce ANALYSIS_BATCH_SIZE."
            )

        if not content or not content.strip():
            logger.error(
                "LLM returned empty content. Response body:\n%s",
                json.dumps(data, indent=2)[:4000],
            )
            raise ValueError("LLM returned empty content")

        return content

    @staticmethod
    def _extract_message_content(data: dict[str, Any]) -> tuple[str, str | None]:
        if "error" in data:
            error = data["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise ValueError(f"LLM API error: {message}")

        choices = data.get("choices")
        if not choices:
            raise ValueError(
                f"LLM response missing choices. Body: {json.dumps(data, indent=2)[:2000]}"
            )

        choice = choices[0]
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason")

        content = message.get("content")
        reasoning = message.get("reasoning_content")

        logger.info(
            "LLM response fields: finish_reason=%s content_chars=%s reasoning_chars=%s",
            finish_reason,
            len(content) if content else 0,
            len(reasoning) if reasoning else 0,
        )

        if content and content.strip():
            return content, finish_reason

        # Some DeepSeek reasoning/thinking models put output in reasoning_content.
        if reasoning and reasoning.strip():
            logger.warning(
                "LLM content empty; falling back to reasoning_content "
                "(common with thinking/reasoning models)"
            )
            return reasoning, finish_reason

        return content or "", finish_reason

    @staticmethod
    def _normalize_json_text(raw: str) -> str:
        text = raw.strip()
        fenced = _JSON_FENCE_RE.match(text)
        if fenced:
            text = fenced.group(1).strip()
        return text

    @staticmethod
    def _parse_response(raw: str) -> LLMAnalysisResponse:
        normalized_text = LLMClient._normalize_json_text(raw)
        try:
            parsed = json.loads(normalized_text)
            LLMClient._warn_missing_confidence(parsed)
            return LLMAnalysisResponse.model_validate(parsed)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.error("Failed to parse LLM response: %s\nRaw output:\n%s", exc, raw)
            raise ValueError(f"Invalid LLM response: {exc}") from exc

    @staticmethod
    def _warn_missing_confidence(parsed: dict[str, Any]) -> None:
        for result in parsed.get("results", []):
            for atx in result.get("analyzed_transactions", []):
                if not isinstance(atx, dict):
                    continue
                if atx.get("confidence") is None and "confidence" not in atx:
                    logger.warning(
                        "LLM omitted confidence for transaction %s — defaulting to 0.5",
                        result.get("transaction_id"),
                    )
