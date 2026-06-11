from __future__ import annotations
import re
from typing import Iterable

QUOTED_OR_WORD = re.compile(r'"([^"]+)"|([^,]+)')


def parse_term_list(text: str | None) -> list[str]:
    if not text:
        return []
    terms: list[str] = []
    for m in QUOTED_OR_WORD.finditer(text):
        term = (m.group(1) or m.group(2) or '').strip()
        if term:
            terms.append(term.lower())
    return terms


def any_term_in_text(text: str, terms: Iterable[str]) -> bool:
    low = (text or '').lower()
    return any(term in low for term in terms if term)


def passes_include_exclude(text: str, include_terms: list[str], exclude_terms: list[str]) -> bool:
    if include_terms and not any_term_in_text(text, include_terms):
        return False
    if exclude_terms and any_term_in_text(text, exclude_terms):
        return False
    return True
