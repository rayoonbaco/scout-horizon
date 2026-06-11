from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List
import json
import math
import re

# Scout Horizon Pass 17D: company-aware strategy scoring and honest adjacent-result labeling.
# This is demo-safe decision support. It does not claim validated enterprise/GxP intelligence.

ONTOLOGY: Dict[str, Dict[str, Any]] = {
    "glp1_manufacturing_pressure": {"label": "GLP-1 manufacturing pressure", "terms": ["glp-1", "glp1", "obesity", "diabetes", "semaglutide", "tirzepatide", "wegovy", "ozempic", "mounjaro", "zepbound", "injectable", "incretin", "peptide", "lilly", "novo", "demand"]},
    "fill_finish_capacity": {"label": "Fill-finish / sterile capacity", "terms": ["fill-finish", "fill finish", "sterile", "aseptic", "injectable", "vial", "syringe", "cartridge", "finish line", "capacity", "expansion", "packaging", "parenteral"]},
    "cdmo_outsourcing": {"label": "CDMO / outsourcing", "terms": ["cdmo", "cmo", "contract manufacturing", "contract manufacturer", "outsourcing", "external manufacturing", "partner", "supplier", "tech transfer", "technology transfer", "manufacturing partner"]},
    "fda_gmp_pressure": {"label": "FDA / GMP pressure", "terms": ["fda", "gmp", "cgmp", "warning letter", "inspection", "483", "form 483", "compliance", "quality", "remediation", "validation", "data integrity", "recall"]},
    "automation_bms_commissioning": {"label": "Automation / BMS / commissioning", "terms": ["automation", "bms", "building management", "commissioning", "qualification", "csv", "computer system validation", "process control", "scada", "mes", "digital manufacturing"]},
    "cold_chain_supply": {"label": "Cold chain / supply resilience", "terms": ["cold chain", "temperature", "refrigerated", "supply chain", "logistics", "shortage", "inventory", "distribution", "warehouse", "resilience"]},
    "cyber_ot_risk": {"label": "Cyber / OT risk", "terms": ["cyber", "cisa", "cve", "ransomware", "ot", "ics", "scada", "vulnerability", "industrial control", "security", "kev"]},
    "competitive_strategy": {"label": "Competitive / partnership strategy", "terms": ["partnership", "deal", "acquisition", "collaboration", "pipeline", "launch", "market", "competitive", "hiring", "investment", "capex", "alliance", "asco", "conference"]},
}

HIGH_VALUE_SOURCES = ["fda", "sec", "edgar", "clinicaltrials", "ema", "pharma manufacturing", "biopharma dive", "fierce", "endpoints", "stat", "ispe"]
CYBER_SOURCES = ["cisa", "nvd", "cve", "kev"]
GENERIC_PIPELINE_TERMS = ["asco", "conference", "pipeline", "oncology", "deal", "abstract", "presentation", "biotech rise"]
MANUFACTURING_LANES = {"fill_finish_capacity", "cdmo_outsourcing", "fda_gmp_pressure", "automation_bms_commissioning", "cold_chain_supply"}

COMPANY_ALIASES: Dict[str, List[str]] = {
    "pfizer": ["pfizer", "pfe"], "amgen": ["amgen"], "eli lilly": ["eli lilly", "lilly", "lly"], "lilly": ["eli lilly", "lilly", "lly"],
    "novo nordisk": ["novo nordisk", "novo", "nvo"], "novo": ["novo nordisk", "novo", "nvo"], "roche": ["roche", "genentech"],
    "merck": ["merck", "mrk", "msd"], "astrazeneca": ["astrazeneca", "azn"], "sanofi": ["sanofi"], "catalent": ["catalent"], "lonza": ["lonza"],
    "novartis": ["novartis"], "gsk": ["gsk", "glaxosmithkline"], "regeneron": ["regeneron"], "moderna": ["moderna"],
    "thermo fisher": ["thermo fisher", "thermo fisher scientific"], "samsung biologics": ["samsung biologics"], "wuxi": ["wuxi", "wuxi biologics"],
    "fujifilm diosynth": ["fujifilm diosynth", "fujifilm"], "takeda": ["takeda"], "abbvie": ["abbvie"], "bayer": ["bayer"], "gilead": ["gilead"], "vertex": ["vertex"],
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except Exception:
            value = str(value)
    return re.sub(r"\s+", " ", str(value)).strip()


def _lower(value: Any) -> str:
    return _clean(value).lower().replace("_", " ")


def _text(signal: Dict[str, Any]) -> str:
    parts: List[str] = []
    for value in signal.values():
        if isinstance(value, (str, int, float)):
            parts.append(str(value))
        elif isinstance(value, list):
            parts.extend(_clean(v) for v in value)
        elif isinstance(value, dict):
            parts.append(_clean(value))
    return _lower(" ".join(parts))


def _source(signal: Dict[str, Any]) -> str:
    return _clean(signal.get("source") or signal.get("source_name") or signal.get("source_domain") or signal.get("displayLink") or signal.get("publisher") or signal.get("url") or signal.get("link") or "current source")


def _title(signal: Dict[str, Any]) -> str:
    return _clean(signal.get("title") or signal.get("name") or signal.get("headline") or signal.get("summary") or signal.get("observation") or signal.get("text") or "Untitled signal")


def _numeric(signal: Dict[str, Any], keys: Iterable[str], default: float = 0.50) -> float:
    for key in keys:
        try:
            val = signal.get(key)
            if val not in (None, ""):
                parsed = float(val)
                if math.isfinite(parsed):
                    return max(0.01, min(0.99, parsed))
        except Exception:
            pass
    return default


def _tokens(value: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9\-]+", _lower(value)) if len(t) >= 3]


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(_lower(term) in text for term in terms)


def _matches(text: str, terms: Iterable[str]) -> List[str]:
    return sorted({term for term in terms if _lower(term) in text})


def company_aliases(company: str) -> List[str]:
    key = _lower(company)
    if not key:
        return []
    return COMPANY_ALIASES.get(key, [key])


def signal_mentions_company(signal: Dict[str, Any], company: str) -> bool:
    text = _text(signal)
    return bool(company and any(alias in text for alias in company_aliases(company)))


def infer_company_from_text(signal: Dict[str, Any], known_companies: Iterable[str] | None = None) -> str:
    direct = _clean(signal.get("company") or signal.get("account") or signal.get("organization") or signal.get("company_name"))
    if direct:
        return direct
    text = _text(signal)
    ordered = list(known_companies or []) + ["Eli Lilly", "Novo Nordisk", "Pfizer", "Amgen", "Roche", "Merck", "AstraZeneca", "Sanofi", "Catalent", "Lonza", "Novartis", "GSK", "Regeneron", "Moderna", "Thermo Fisher", "Samsung Biologics", "WuXi", "Fujifilm Diosynth", "Takeda", "AbbVie", "Bayer", "Gilead", "Vertex"]
    for name in ordered:
        if signal_mentions_company(signal, name):
            return name
    return ""


def active_topic_lanes(state: Dict[str, Any]) -> List[str]:
    focus = _lower(" ".join([state.get("keyword") or "", state.get("query") or "", state.get("mode") or ""]))
    lanes = []
    for lane, cfg in ONTOLOGY.items():
        if _contains_any(focus, cfg["terms"]) or _contains_any(focus, [cfg["label"]]):
            lanes.append(lane)
    return lanes


def source_truth_level(signal: Dict[str, Any]) -> str:
    text = _text(signal)
    src = _lower(_source(signal))
    if any(s in src or s in text for s in ["fda", "sec", "edgar", "clinicaltrials", "ema", "cisa", "nvd", "cve"]):
        return "authoritative public source"
    if signal.get("url") or signal.get("link"):
        return "linked public source"
    return "demo/fallback source"


def score_signal(signal: Dict[str, Any], state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    state = state or {}
    text = _text(signal)
    source = _lower(_source(signal))
    base = _numeric(signal, ["strategic_relevance", "priority_score", "priority", "score", "confidence"], 0.50)
    keyword = _clean(state.get("keyword") or state.get("query") or "")
    company = _clean(state.get("company") or "")
    keyword_tokens = _tokens(keyword)
    active_lanes = active_topic_lanes(state)
    selected_company_match = signal_mentions_company(signal, company)
    points = 0.0
    reasons: List[str] = []
    warnings: List[str] = []
    lane_scores: Dict[str, float] = {}

    if keyword_tokens:
        hits = [t for t in keyword_tokens if t in text]
        if hits:
            points += min(0.22, 0.045 * len(set(hits)))
            reasons.append("matched scan topic")
        else:
            points -= 0.10
            warnings.append("topic words not obvious in signal")

    if company:
        if selected_company_match:
            points += 0.34
            reasons.append(f"matched selected company: {company}")
        else:
            points -= 0.22
            warnings.append(f"No {company}-specific signal found in this item; showing adjacent market signal.")

    for lane, cfg in ONTOLOGY.items():
        hits = _matches(text, cfg["terms"])
        if hits:
            lane_points = min(0.30, 0.045 * len(hits))
            if lane in active_lanes:
                lane_points *= 1.7
            lane_scores[lane] = lane_points
            points += lane_points
            reasons.append(f"{cfg['label']} match: " + ", ".join(hits[:4]))

    if active_lanes and not any(lane in lane_scores for lane in active_lanes):
        points -= 0.14
        warnings.append("weak match for selected strategy lane")
    if any(src in source for src in HIGH_VALUE_SOURCES):
        points += 0.04
        reasons.append("recognized public life-sciences source")
    if any(src in source or src in text for src in CYBER_SOURCES) and "cyber_ot_risk" not in active_lanes:
        points -= 0.24
        warnings.append("cyber item downweighted because scan is not cyber-focused")

    manufacturing_scan = any(lane in active_lanes for lane in ["glp1_manufacturing_pressure", "fill_finish_capacity", "cdmo_outsourcing", "fda_gmp_pressure", "automation_bms_commissioning", "cold_chain_supply"])
    mfg_lane_hit = any(lane in lane_scores for lane in MANUFACTURING_LANES)
    glp_hit = "glp1_manufacturing_pressure" in lane_scores
    generic_hit = _contains_any(text, GENERIC_PIPELINE_TERMS)
    if manufacturing_scan:
        if glp_hit and mfg_lane_hit:
            points += 0.24
            reasons.append("best-fit combination: GLP-1 plus manufacturing pressure")
        elif mfg_lane_hit:
            points += 0.16
            reasons.append("manufacturing-specific signal")
        elif glp_hit:
            points -= 0.16
            warnings.append("GLP-1-adjacent but not manufacturing-specific")
        else:
            points -= 0.28
            warnings.append("weak match for GLP-1/manufacturing pressure")
        if generic_hit and not mfg_lane_hit:
            points -= 0.28
            warnings.append("generic pipeline/deal/conference signal without operational pressure")

    final = max(0.01, min(0.99, base + points))
    best_lane = max(lane_scores.items(), key=lambda x: x[1])[0] if lane_scores else (active_lanes[0] if active_lanes else "broad_life_sciences")
    level = "High" if final >= 0.78 else "Moderate" if final >= 0.60 else "Early"
    natural_company = infer_company_from_text(signal)
    company_adjacent_only = bool(company and not selected_company_match)
    if company_adjacent_only:
        label = f"No {company}-specific match found; showing adjacent broad-market signal."
    elif company and selected_company_match:
        label = f"Company match found: {company}."
    elif natural_company:
        label = f"{natural_company} surfaced naturally; no company was locked."
    else:
        label = "No company locked; broad scan."
    return {
        "strategy_score": round(final, 3), "strategic_relevance": round(final, 3), "strategy_level": level,
        "strategy_lane": best_lane, "strategic_lane": ONTOLOGY.get(best_lane, {}).get("label", "Broad life-sciences signal"), "strategy_lane_label": ONTOLOGY.get(best_lane, {}).get("label", "Broad life-sciences signal"),
        "strategy_reasons": reasons[:8] or ["broad public/sample signal available for review"], "why_this_signal_won": reasons[:8] or ["broad public/sample signal available for review"], "strategic_warnings": warnings[:8],
        "source_truth_level": source_truth_level(signal), "natural_company": natural_company, "selected_company": company,
        "company_match": bool(selected_company_match), "company_adjacent_only": company_adjacent_only, "company_truth_label": label, "manufacturing_specific": bool(mfg_lane_hit),
    }


def why_leadership_should_care(signal: Dict[str, Any], state: Dict[str, Any] | None = None, scored: Dict[str, Any] | None = None) -> str:
    scored = scored or score_signal(signal, state)
    lane = scored.get("strategy_lane")
    if scored.get("company_adjacent_only"):
        return scored.get("company_truth_label", "No company-specific match found.") + " Use this as market context, not company-specific evidence."
    if lane == "glp1_manufacturing_pressure":
        return "GLP-1 demand can create pressure around injectable capacity, fill-finish slots, CDMO support, validation work, and launch readiness."
    if lane == "fill_finish_capacity":
        return "Capacity or sterile manufacturing movement can signal future demand for commissioning, validation, automation, quality, or partner support."
    if lane == "cdmo_outsourcing":
        return "Outsourcing or partner activity can reveal where sponsors may need tech-transfer, supplier governance, validation, and readiness support."
    if lane == "fda_gmp_pressure":
        return "Regulatory or quality pressure can turn into remediation, validation, inspection-readiness, and executive risk review."
    if lane == "automation_bms_commissioning":
        return "Automation and commissioning signals can reveal where facilities may need controls, qualification, validation, or digital manufacturing help."
    if lane == "cold_chain_supply":
        return "Cold-chain or supply stress can affect launch readiness, patient access, inventory resilience, and partner selection."
    if lane == "cyber_ot_risk":
        return "Cyber/OT exposure can affect regulated manufacturing uptime, quality systems, and executive risk posture."
    if lane == "competitive_strategy":
        return "Competitive, partnership, and pipeline moves can foreshadow demand, market pressure, account strategy, or partner ecosystem shifts."
    return "This may point to pressure, opportunity, or change. Treat it as a lead to verify, not a final conclusion."


def recommended_next_move(signal: Dict[str, Any], state: Dict[str, Any] | None = None, scored: Dict[str, Any] | None = None) -> str:
    scored = scored or score_signal(signal, state)
    lane = scored.get("strategy_lane")
    if scored.get("company_adjacent_only"):
        company = scored.get("selected_company") or "the selected company"
        return f"No direct {company} signal is available in the current source set. Either clear the company filter for market-wide context or add/source a {company}-specific item before making a company claim."
    if lane in {"glp1_manufacturing_pressure", "fill_finish_capacity", "cdmo_outsourcing"}:
        return "Build a short watchlist of CDMOs, fill-finish capacity expansions, FDA/GMP signals, validation needs, and automation/commissioning vendors tied to this demand."
    if lane == "fda_gmp_pressure":
        return "Open the evidence, confirm the regulatory context, then flag likely remediation, validation, quality, and supplier-readiness implications."
    if lane == "automation_bms_commissioning":
        return "Check whether this creates commissioning, controls, qualification, CSV, or validation follow-up work."
    if lane == "cold_chain_supply":
        return "Check cold-chain, inventory, and distribution constraints before treating the signal as a commercial opportunity."
    if lane == "cyber_ot_risk":
        return "Map affected OT/manufacturing systems, then decide whether uptime, quality, or compliance risk should be escalated."
    return "Open Evidence, confirm the source, then narrow by company, lane, or source if leadership wants a focused follow-up."


def enrich_signal(signal: Dict[str, Any], state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    scored = score_signal(signal, state)
    enriched = dict(signal)
    enriched.update(scored)
    enriched["why_leadership_should_care"] = why_leadership_should_care(signal, state, scored)
    enriched["recommended_next_move"] = recommended_next_move(signal, state, scored)
    return enriched


def rank_signals(items: List[Dict[str, Any]], state: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    enriched = [enrich_signal(item, state) for item in items if isinstance(item, dict)]
    return sorted(enriched, key=lambda item: item.get("strategy_score", item.get("score", 0)), reverse=True)


def strategy_audit(items: List[Dict[str, Any]], state: Dict[str, Any] | None = None, source_targets: List[Dict[str, Any]] | None = None, google_configured: bool = False) -> Dict[str, Any]:
    state = state or {}
    ranked = rank_signals(items, state)
    top = ranked[0] if ranked else {}
    lane_counts = Counter(item.get("strategy_lane_label") or item.get("strategy_lane") or "unclassified" for item in ranked)
    source_counts = Counter(_source(item) for item in ranked)
    company = _clean(state.get("company") or "")
    company_matches = sum(1 for item in ranked if item.get("company_match"))
    warnings = []
    if not google_configured:
        warnings.append("Google Programmable Search is not configured; demo/RSS/fallback paths may be used.")
    if company and company_matches == 0:
        warnings.append(f"No {company}-specific signal was found; results should be labeled as adjacent market context.")
    if top and top.get("company_adjacent_only"):
        warnings.append(top.get("company_truth_label"))
    if top and (top.get("strategy_score") or 0) < 0.60:
        warnings.append("Top signal is still early/moderate; verify source before using it as a leadership claim.")
    return {
        "ok": True, "strategy_engine": "pass17d_company_filter_truthfulness", "state": state, "google_configured": bool(google_configured),
        "source_targets_available": len(source_targets or []), "signals_reviewed": len(ranked), "company_filter": company, "company_specific_matches": company_matches,
        "counts_by_strategy_lane": dict(lane_counts), "counts_by_source": dict(source_counts.most_common(12)),
        "top_signal": {
            "title": _title(top), "source": _source(top), "strategy_score": top.get("strategy_score"), "strategy_level": top.get("strategy_level"), "strategy_lane": top.get("strategy_lane_label"),
            "source_truth_level": top.get("source_truth_level"), "why_this_signal_won": top.get("why_this_signal_won"), "strategic_warnings": top.get("strategic_warnings"),
            "company_match": top.get("company_match"), "company_adjacent_only": top.get("company_adjacent_only"), "company_truth_label": top.get("company_truth_label"),
            "why_leadership_should_care": top.get("why_leadership_should_care"), "recommended_next_move": top.get("recommended_next_move"), "natural_company": top.get("natural_company"),
        } if top else {},
        "warnings": [w for w in warnings if w],
        "model_limits": [
            "This is a demo-safe public/sample intelligence workflow, not validated GxP or enterprise production software.",
            "Scores are decision-support heuristics; source evidence should be checked before leadership action.",
            "If a selected company has no direct match, the app must label broad-market results as adjacent context.",
        ],
    }

# PASS 17H - scan mode weighting repair START
# Purpose: make the scan-mode control materially affect scoring, labels, and audit evidence.
# Broad should behave like market/environmental reconnaissance.
# Targeted should behave like stricter account/source/topic pursuit.
# Broad + targeted should remain the balanced executive default.
try:
    _PASS17H_BASE_SCORE_SIGNAL
except NameError:
    _PASS17H_BASE_SCORE_SIGNAL = score_signal

try:
    _PASS17H_BASE_ENRICH_SIGNAL
except NameError:
    _PASS17H_BASE_ENRICH_SIGNAL = enrich_signal

try:
    _PASS17H_BASE_RANK_SIGNALS
except NameError:
    _PASS17H_BASE_RANK_SIGNALS = rank_signals


def _pass17h_mode(state: Dict[str, Any] | None = None) -> str:
    raw = _lower((state or {}).get("mode") or (state or {}).get("coverage") or "broad_targeted")
    raw = raw.replace("and", "_").replace("-", "_").replace(" ", "_")
    if raw in {"targeted", "targeted_only", "source_targeted", "company_targeted"}:
        return "targeted"
    if raw in {"broad", "broad_only", "market", "environmental"}:
        return "broad"
    return "broad_targeted"


def _pass17h_sources(state: Dict[str, Any] | None = None) -> List[str]:
    raw = (state or {}).get("sources") or (state or {}).get("source") or (state or {}).get("source_filter") or []
    if isinstance(raw, str):
        raw = [raw]
    return [_clean(x) for x in raw if _clean(x)]


def _pass17h_mode_profile(mode: str) -> str:
    if mode == "targeted":
        return "targeted scan: prioritizes exact company, topic, and selected-source evidence; labels adjacent results when direct evidence is thin"
    if mode == "broad":
        return "broad scan: prioritizes market-wide pressure, source diversity, and strategic context over exact company binding"
    return "broad + targeted scan: balances market context with company/topic/source relevance"


def _pass17h_company_match(text: str, company: str) -> bool:
    if not company:
        return False
    aliases = {
        "pfizer": ["pfizer", "pfe"],
        "amgen": ["amgen"],
        "eli lilly": ["eli lilly", "lilly", "lly"],
        "novo nordisk": ["novo nordisk", "novo", "nvo"],
        "roche": ["roche", "genentech"],
        "merck": ["merck", "mrk", "msd"],
        "astrazeneca": ["astrazeneca", "azn"],
        "sanofi": ["sanofi"],
        "catalent": ["catalent"],
        "lonza": ["lonza"],
    }
    terms = aliases.get(_lower(company), [_lower(company)])
    return any(term and term in text for term in terms)


def _pass17h_selected_source_match(signal: Dict[str, Any], selected_sources: List[str]) -> bool:
    if not selected_sources:
        return False
    src_text = _lower(" ".join([_source(signal), signal.get("source_domain") or "", signal.get("url") or "", signal.get("link") or ""]))
    for source in selected_sources:
        compact = _lower(source).replace(" ", "")
        if _lower(source) in src_text or compact in src_text.replace(" ", ""):
            return True
    return False


def score_signal(signal: Dict[str, Any], state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    state = state or {}
    result = dict(_PASS17H_BASE_SCORE_SIGNAL(signal, state))
    mode = _pass17h_mode(state)
    text = _text(signal)
    source = _lower(_source(signal))
    company = _clean(state.get("company") or "")
    keyword = _clean(state.get("keyword") or "")
    selected_sources = _pass17h_sources(state)
    active_lanes = active_topic_lanes(state)
    lane = result.get("strategy_lane") or "broad_life_sciences"

    topic_tokens = _tokens(keyword)
    topic_hits = [t for t in topic_tokens if t in text]
    direct_topic = bool(topic_hits) or (lane in active_lanes if active_lanes else False)
    direct_company = _pass17h_company_match(text, company)
    direct_source = _pass17h_selected_source_match(signal, selected_sources)

    delta = 0.0
    reasons = list(result.get("strategy_reasons") or [])

    if mode == "targeted":
        if direct_topic:
            delta += 0.055
            reasons.append("targeted mode rewarded direct topic evidence")
        else:
            delta -= 0.075
            reasons.append("targeted mode penalized weak topic evidence")
        if company:
            if direct_company:
                delta += 0.115
                reasons.append("targeted mode rewarded exact company evidence")
            else:
                delta -= 0.145
                reasons.append("targeted mode labeled company result as adjacent because exact evidence was not visible")
        if selected_sources:
            if direct_source:
                delta += 0.075
                reasons.append("targeted mode rewarded selected-source match")
            else:
                delta -= 0.080
                reasons.append("targeted mode penalized weak selected-source fit")

    elif mode == "broad":
        # Broad mode is allowed to prefer market context even when company/source binding is thin.
        if any(src in source or src in text for src in HIGH_VALUE_SOURCES):
            delta += 0.060
            reasons.append("broad mode rewarded recognized market/regulatory source context")
        if lane in {"competitive_strategy", "glp1_manufacturing_pressure", "fill_finish_capacity", "fda_gmp_pressure", "cyber_ot_risk"}:
            delta += 0.045
            reasons.append("broad mode rewarded market-wide pressure lane")
        if company and not direct_company:
            delta += 0.045
            reasons.append("broad mode did not over-penalize missing exact company evidence")
        if selected_sources and not direct_source:
            delta += 0.020
            reasons.append("broad mode treated selected source as contextual rather than a hard directness requirement")

    else:
        if direct_topic:
            delta += 0.035
            reasons.append("broad + targeted mode rewarded topic fit")
        if company and direct_company:
            delta += 0.055
            reasons.append("broad + targeted mode rewarded company fit")
        elif company:
            delta -= 0.035
            reasons.append("broad + targeted mode marked company evidence as adjacent")
        if selected_sources and direct_source:
            delta += 0.040
            reasons.append("broad + targeted mode rewarded source fit")

    score = float(result.get("strategy_score") or result.get("score") or 0.50)
    result["strategy_score"] = round(max(0.01, min(0.99, score + delta)), 3)
    result["strategy_level"] = "High" if result["strategy_score"] >= 0.78 else "Moderate" if result["strategy_score"] >= 0.60 else "Early"
    result["scan_mode_used"] = mode
    result["scan_mode_profile"] = _pass17h_mode_profile(mode)
    result["scan_mode_delta"] = round(delta, 3)
    result["strategy_reasons"] = reasons[:10]
    return result


def enrich_signal(signal: Dict[str, Any], state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    state = state or {}
    scored = score_signal(signal, state)
    enriched = dict(signal)
    enriched.update(scored)

    mode = scored.get("scan_mode_used") or _pass17h_mode(state)
    company = _clean(state.get("company") or "")
    selected_sources = _pass17h_sources(state)
    text = _text(signal)
    direct_company = _pass17h_company_match(text, company) if company else False
    direct_source = _pass17h_selected_source_match(signal, selected_sources) if selected_sources else False

    truth_bits = [_pass17h_mode_profile(mode)]
    if company:
        truth_bits.append("direct company match" if direct_company else "company-adjacent: no exact company evidence visible in the selected signal")
    if selected_sources:
        truth_bits.append("direct selected-source match" if direct_source else "source-adjacent: selected source did not clearly appear in the selected signal")
    existing_truth = _clean(enriched.get("truth_label"))
    if existing_truth:
        truth_bits.append(existing_truth)

    enriched["truth_label"] = " | ".join(dict.fromkeys([b for b in truth_bits if b]))
    enriched["why_leadership_should_care"] = why_leadership_should_care(signal, state, scored)
    enriched["recommended_next_move"] = recommended_next_move(signal, state, scored)
    enriched["why_this_signal_won"] = "; ".join(scored.get("strategy_reasons") or [])
    return enriched


def rank_signals(items: List[Dict[str, Any]], state: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    enriched = [enrich_signal(item, state) for item in items if isinstance(item, dict)]
    mode = _pass17h_mode(state or {})
    # Stable mode-aware tiebreaker so the mode control has visible, testable behavior without inventing facts.
    def mode_sort_key(item: Dict[str, Any]) -> tuple:
        score = float(item.get("strategy_score") or item.get("score") or 0)
        mode_bonus = 0.0
        text = _text(item)
        if mode == "targeted":
            if "direct company match" in _lower(item.get("truth_label") or ""):
                mode_bonus += 0.010
            if "direct selected-source match" in _lower(item.get("truth_label") or ""):
                mode_bonus += 0.008
        elif mode == "broad":
            if any(src in _lower(_source(item)) or src in text for src in HIGH_VALUE_SOURCES):
                mode_bonus += 0.008
        return (score + mode_bonus, _title(item))
    return sorted(enriched, key=mode_sort_key, reverse=True)
# PASS 17H - scan mode weighting repair END
