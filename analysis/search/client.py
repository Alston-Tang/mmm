from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from analysis.config import get_settings

logger = logging.getLogger(__name__)

# Skip search for generic bank/payment descriptions that won't yield useful results.
_SKIP_SEARCH_PATTERNS = re.compile(
    r"^(automatic payment|autopay|auto pay|direct dep|payroll|transfer|payment - thank)",
    re.IGNORECASE,
)


class WebSearchClient:
    """Search the web for merchant/transaction context (Tavily or Serper)."""

    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def enabled(self) -> bool:
        return self._settings.search_enabled and bool(self._settings.search_api_key)

    async def search_for_transactions(
        self,
        transactions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Search for context about ambiguous transactions.

        Returns a payload suitable for inclusion in the LLM user message.
        """
        if not self.enabled or not transactions:
            return {"search_results": []}

        queries = self._build_queries(transactions)
        if not queries:
            logger.info("No searchable merchants in uncertain batch")
            return {"search_results": []}

        logger.info(
            "Searching web for %d queries (provider=%s)",
            len(queries),
            self._settings.search_provider,
        )

        sem = asyncio.Semaphore(self._settings.search_max_concurrent)
        results: list[dict[str, Any]] = []

        async def run_one(query_info: dict[str, Any]) -> dict[str, Any] | None:
            async with sem:
                try:
                    hits = await self._search(query_info["query"])
                    if not hits:
                        return None
                    return {
                        "query": query_info["query"],
                        "transaction_ids": query_info["transaction_ids"],
                        "results": hits,
                    }
                except Exception:
                    logger.exception("Search failed for query: %s", query_info["query"])
                    return None

        search_outcomes = await asyncio.gather(*(run_one(q) for q in queries))
        results = [r for r in search_outcomes if r is not None]

        logger.info("Web search returned results for %d/%d queries", len(results), len(queries))
        return {"search_results": results}

    def _build_queries(self, transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deduplicate search queries across transactions."""
        seen_queries: set[str] = set()
        queries: list[dict[str, Any]] = []

        for tx in transactions:
            tx_id = tx.get("transaction_id")
            data = tx.get("data") or {}
            query = self._query_for_transaction(data)
            if not query or query in seen_queries:
                if query and tx_id:
                    for q in queries:
                        if q["query"] == query and tx_id not in q["transaction_ids"]:
                            q["transaction_ids"].append(tx_id)
                continue
            seen_queries.add(query)
            queries.append({"query": query, "transaction_ids": [tx_id] if tx_id else []})

        return queries[: self._settings.search_max_queries]

    @staticmethod
    def _query_for_transaction(data: dict[str, Any]) -> str | None:
        merchant = (data.get("merchant_name") or "").strip()
        name = (data.get("name") or "").strip()
        label = merchant or name
        if not label:
            return None
        if _SKIP_SEARCH_PATTERNS.search(label):
            return None
        # Strip common bank noise prefixes
        label = re.sub(r"^(ALP\*|SQ \*|TST\*|PP\*|POS )", "", label, flags=re.IGNORECASE).strip()
        if not label:
            return None
        return f"what is {label}"

    async def _search(self, query: str) -> list[dict[str, str]]:
        provider = self._settings.search_provider.lower()
        if provider == "tavily":
            return await self._search_tavily(query)
        if provider == "serper":
            return await self._search_serper(query)
        raise ValueError(f"Unknown search provider: {provider}")

    async def _search_tavily(self, query: str) -> list[dict[str, str]]:
        url = "https://api.tavily.com/search"
        body = {
            "api_key": self._settings.search_api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": self._settings.search_max_results,
            "include_answer": True,
        }
        async with httpx.AsyncClient(timeout=self._settings.search_timeout_seconds) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            data = response.json()

        hits: list[dict[str, str]] = []
        answer = data.get("answer")
        if answer:
            hits.append({"title": "Summary", "content": answer, "url": ""})

        for item in data.get("results", [])[: self._settings.search_max_results]:
            hits.append(
                {
                    "title": item.get("title") or "",
                    "content": item.get("content") or "",
                    "url": item.get("url") or "",
                }
            )
        logger.info("Tavily search %r -> %d results", query, len(hits))
        return hits

    async def _search_serper(self, query: str) -> list[dict[str, str]]:
        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": self._settings.search_api_key,
            "Content-Type": "application/json",
        }
        body = {"q": query, "num": self._settings.search_max_results}
        async with httpx.AsyncClient(timeout=self._settings.search_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

        hits: list[dict[str, str]] = []
        for item in data.get("organic", [])[: self._settings.search_max_results]:
            hits.append(
                {
                    "title": item.get("title") or "",
                    "content": item.get("snippet") or "",
                    "url": item.get("link") or "",
                }
            )
        logger.info("Serper search %r -> %d results", query, len(hits))
        return hits
