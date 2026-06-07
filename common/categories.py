"""Transaction category taxonomy shared by analysis and viewer.

When this list changes:
- New analysis uses the updated list (LLM prompt + validation).
- Existing rows in analyzed_transactions keep their stored category unchanged.
- The viewer filter dropdown shows current categories plus any legacy values still in the DB.
"""

from __future__ import annotations

PREDEFINED_CATEGORIES: list[str] = [
    "car",
    "gas",
    "ski",
    "rental",
    "utilities",
    "electricity device",
    "running",
    "travel",
    "food",
    "coffee and beverage",
    "daily life",
    "flight training",
    "commute",
    "interest",
    "capital gain/loss",
    "payroll",
    "healthcare",
    "entertainment",
    "insurance",
    "education",
    "shopping",
    "transfer",
    "fees",
    "tax",
    "other",
]

_PREDEFINED_SET = frozenset(PREDEFINED_CATEGORIES)


def is_valid_category(category: str) -> bool:
    return category in _PREDEFINED_SET


def merge_category_options(stored_categories: list[str]) -> list[str]:
    """Current taxonomy first, then legacy categories from stored transactions."""
    seen: set[str] = set()
    merged: list[str] = []
    for category in PREDEFINED_CATEGORIES:
        if category not in seen:
            merged.append(category)
            seen.add(category)
    for category in sorted(stored_categories):
        if category and category not in seen:
            merged.append(category)
            seen.add(category)
    return merged
