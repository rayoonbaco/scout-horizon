from __future__ import annotations
import re

MONEY_RE = re.compile(r'(\$\s?\d+[\d\.,]*\s?(?:million|billion|m|bn)?)', re.I)
PARTNER_SPLIT_RE = re.compile(r'\b(?:partners? with|collaborates? with|teams? up with|joins? forces with|and)\b', re.I)


def detect_partnership(text: str, keywords: list[str]) -> bool:
    low = (text or '').lower()
    return any(k.lower() in low for k in (keywords or []))


def extract_partnership_fields(title: str, summary: str, account: str = '', known_accounts: list[str] | None = None, modalities: list[str] | None = None, stages: list[str] | None = None) -> dict:
    text = ' '.join([title or '', summary or '']).strip()
    low = text.lower()
    known_accounts = known_accounts or []
    modalities = modalities or []
    stages = stages or []

    matches = []
    for acct in known_accounts:
        if acct and acct.lower() in low and acct not in matches:
            matches.append(acct)

    partner_a = account or (matches[0] if matches else '')
    partner_b = matches[1] if len(matches) > 1 else ''

    if not partner_b and title:
        bits = [b.strip(' .,:;') for b in PARTNER_SPLIT_RE.split(title) if b.strip()]
        if len(bits) >= 2:
            first, second = bits[0], bits[1]
            if len(first.split()) <= 6 and len(second.split()) <= 8:
                partner_a = partner_a or first
                partner_b = second

    money = ''
    m = MONEY_RE.search(text)
    if m:
        money = m.group(1).replace('  ', ' ').strip()

    modality = next((m for m in modalities if m.lower() in low), '')
    stage = next((s for s in stages if s.lower() in low), '')

    geography = ''
    geo_tokens = ['massachusetts', 'new jersey', 'pennsylvania', 'california', 'ohio', 'illinois', 'north carolina', 'bay area', 'chicago', 'columbus', 'so cal', 'socal']
    for token in geo_tokens:
        if token in low:
            geography = token.title()
            break

    return {
        'is_partnership': bool(partner_a or partner_b or money or modality or stage),
        'partner_a': partner_a,
        'partner_b': partner_b,
        'deal_value': money,
        'modality': modality,
        'geography': geography,
        'stage': stage,
    }
