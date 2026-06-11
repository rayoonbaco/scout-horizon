from __future__ import annotations
import math
from datetime import datetime, timedelta
from dateutil import parser as dtparser

def freshness_boost(published_iso: str, half_life_days: float = 14.0) -> float:
    if not published_iso:
        return 1.0
    try:
        dt = dtparser.parse(published_iso)
    except Exception:
        return 1.0
    age_days = max(0.0, (datetime.utcnow() - dt).total_seconds() / 86400.0)
    # exponential decay, bounded
    return float(max(0.65, min(1.35, math.exp(-age_days/half_life_days) + 0.35)))

def compute_confidence(event: dict, source_reliability: float) -> tuple[float, list[str]]:
    reasons = []
    c = 0.0
    
    # Source reliability anchor
    c += 0.55 * float(source_reliability)
    reasons.append(f"source_reliability={source_reliability:.2f}")
    
    # Evidence strength
    evidence = event.get("evidence", []) or []
    if isinstance(evidence, str):
        evidence = [evidence]
    if any("sec" in (e or "").lower() or "accession" in (e or "").lower() for e in evidence):
        c += 0.20
        reasons.append("authoritative_evidence=sec")
    elif any("nct" in (e or "").lower() for e in evidence):
        c += 0.15
        reasons.append("authoritative_evidence=clinicaltrials")
    elif any("cve" in (e or "").lower() for e in evidence):
        c += 0.15
        reasons.append("authoritative_evidence=cve")
    elif event.get("link"):
        c += 0.08
        reasons.append("evidence=link")
    
    # Match strength heuristics
    if event.get("account"):
        c += 0.08
        reasons.append("account_match")
    if event.get("region"):
        c += 0.05
        reasons.append("region_match")
    if event.get("service_line"):
        c += 0.05
        reasons.append("service_line_match")

    # Normalize
    c = max(0.05, min(0.99, c))
    return c, reasons

def apply_question_mode(score: float, lane: str, mode_weights: dict, mode: str | None) -> float:
    if not mode:
        return score
    w = (mode_weights.get(mode, {}) or {}).get(lane, 1.0)
    return score * float(w)
