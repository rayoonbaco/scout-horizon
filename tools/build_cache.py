import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import json
from datetime import datetime
from src.filters import parse_term_list, passes_include_exclude

OUT_DIR = ROOT / "outputs"
CACHE_DIR = ROOT / "cache"
CFG_DIR = ROOT / "config"
CACHE_DIR.mkdir(exist_ok=True)
CFG_DIR.mkdir(exist_ok=True)


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(p: Path, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")


def safe_list(x):
    if not x:
        return []
    if isinstance(x, list):
        return x
    return [x]


def url_for_cve(cve_id: str) -> str:
    cve_id = (cve_id or "").strip()
    if cve_id.startswith("CVE-"):
        return f"https://nvd.nist.gov/vuln/detail/{cve_id}"
    return ""


def cisa_url_for_cve(cve_id: str) -> str:
    cve_id = (cve_id or "").strip()
    if cve_id.startswith("CVE-"):
        return "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
    return ""


def first(lst, default=""):
    try:
        if isinstance(lst, list) and lst:
            return lst[0]
    except Exception:
        pass
    return default


def load_settings():
    p = CFG_DIR / "radar_settings.json"
    if p.exists():
        return load_json(p)
    return {"filters": {"include_text": "", "exclude_text": ""}}


def make_partnership_analysis(item: dict) -> tuple[str, str, str]:
    facets = item.get("facets") or {}
    partner_a = first(facets.get("partnership_partner_a", []), "")
    partner_b = first(facets.get("partnership_partner_b", []), "")
    deal_value = first(facets.get("deal_values", []), "")
    modality = first(facets.get("modalities", []), "")
    geography = first(facets.get("deal_geographies", []), "")
    stage = first(facets.get("deal_stages", []), "")

    obs = f"Partnership or deal signal detected: {item.get('title','')}"
    details = [x for x in [partner_a, partner_b, deal_value, modality, geography, stage] if x]
    if details:
        obs += ". Key details: " + ", ".join(details) + "."

    why = "Partnerships often foreshadow manufacturing demand, technology transfer, outsourcing shifts, or competitive repositioning."
    if modality:
        why += f" Modality focus: {modality}."
    if geography:
        why += f" Geography: {geography}."

    rec = "Check whether this changes account access, capacity demand, or partner ecosystem strategy."
    if partner_a or partner_b:
        rec += " Add these companies to watchlists and review adjacent hiring, capex, and regulatory signals."
    return obs, why, rec


def make_analysis(item: dict) -> dict:
    lane = (item.get("lane") or "market_signals").lower()
    title = item.get("title", "")
    refs = item.get("references") or []
    is_kev = any("known exploited" in (r.get("label", "").lower()) or "cisa kev" in (title or "").lower() for r in refs)
    acct = first((item.get("facets") or {}).get("accounts", []), "")
    region = first((item.get("facets") or {}).get("chris_regions", []), "")
    svc = first((item.get("facets") or {}).get("service_lines", []), "")
    is_partnership = bool((item.get("facets") or {}).get("partnerships"))

    if is_partnership:
        obs, why, rec = make_partnership_analysis(item)
    elif lane == "cybersecurity":
        if is_kev:
            obs = f"CISA KEV alert: {title}. KEV means the vulnerability is known to be actively exploited in the real world."
            why = "Actively exploited vulnerabilities are higher urgency because they can affect uptime, validation, and cyber resilience in regulated facilities."
            rec = "Confirm whether the affected product exists in your IT, OT, BAS, or automation stack; if yes, patch or mitigate quickly and document compensating controls."
        else:
            obs = f"Cyber signal detected: {title}."
            why = "OT and facility cyber issues can create downtime, validation impacts, and contractual risk."
            rec = "Review applicability to your OT stack, then decide whether to patch, isolate, or monitor."
    elif lane == "regulatory":
        obs = f"Regulatory signal detected: {title}."
        why = "Regulatory actions can lead to remediation work, quality-system pressure, and accelerated facility upgrades."
        rec = "Identify the affected site, process, and likely service-line impact, then prepare response options."
    elif lane == "construction_capex":
        obs = f"Capex or construction signal: {title}."
        why = "Expansions and new builds often precede demand for automation, commissioning, cleanroom, and validation support."
        rec = "Tag the account and region, then determine whether the project is in planning, permitting, design, or execution."
    elif lane == "hiring_signals":
        obs = f"Hiring signal detected: {title}."
        why = "Role surges can reveal expansion, capability build-out, or operational stress before financial results show it."
        rec = "Compare role types, locations, and functions to see whether this is growth, replacement, or a new capability bet."
    elif lane == "science_trends":
        obs = f"Science or pipeline signal: {title}."
        why = "Pipeline changes can point to future manufacturing demand, modality shifts, and scale-up work."
        rec = "Watch for modality, geography, and account concentration; prioritize the items most likely to trigger facility work."
    elif lane == "competitive_intel":
        obs = f"Competitive or market-movement signal: {title}."
        why = "Competitor movement can change pursuit probability, pricing pressure, and adjacent-service demand."
        rec = "Check whether this creates a threat, a pursuit opening, or a need to reposition messaging."
    elif lane == "margin_protection":
        obs = f"Margin/risk signal: {title}."
        why = "Supply, compliance, or cyber shocks can reduce delivery reliability and compress margins."
        rec = "Update assumptions for cost, schedule, exposure, and contingency plans."
    else:
        obs = f"Market signal: {title}."
        why = "This may indicate emerging demand, investments, or risk relevant to regulated-facilities strategy."
        rec = "Tag it to an account, topic, or region and decide whether to pursue, mitigate, or monitor."

    if acct:
        why += f" Account focus: {acct}."
    if region:
        why += f" Region focus: {region}."
    if svc:
        rec += f" Service line emphasis: {svc}."

    item["observation"] = obs
    item["why_it_matters"] = why
    item["recommendation"] = rec
    item["recommended_action"] = rec
    item.setdefault("internal_corroboration", "—")
    return item


def main():
    signals_path = OUT_DIR / "radar_signals.json"
    summary_path = OUT_DIR / "radar_summary.json"
    if not signals_path.exists() or not summary_path.exists():
        raise SystemExit("Missing outputs. Run the engine first to create outputs/radar_signals.json and outputs/radar_summary.json")

    raw = load_json(signals_path)
    summary = load_json(summary_path)
    settings = load_settings()
    include_terms = parse_term_list((settings.get("filters") or {}).get("include_text", ""))
    exclude_terms = parse_term_list((settings.get("filters") or {}).get("exclude_text", ""))

    items = []
    key_counts = {}
    for s in raw:
        acct = s.get("account", "") or ""
        lane = s.get("lane", "") or ""
        region = s.get("region", "") or ""
        k = (acct, lane, region)
        key_counts[k] = key_counts.get(k, 0) + 1

    for s in raw:
        searchable = " ".join([
            s.get("title", ""),
            s.get("summary", ""),
            s.get("account", ""),
            s.get("service_line", ""),
            s.get("topic", ""),
            s.get("partner_a", ""),
            s.get("partner_b", ""),
            s.get("deal_value", ""),
            s.get("modality", ""),
            s.get("deal_stage", ""),
        ])
        if not passes_include_exclude(searchable, include_terms, exclude_terms):
            continue

        url = s.get("link", "") or ""
        ev = safe_list(s.get("evidence", []))
        cve_id = next((e for e in ev if isinstance(e, str) and e.startswith("CVE-")), "")
        if (not url) and cve_id:
            url = url_for_cve(cve_id)

        lane = s.get("lane", "market_signals")
        acct = s.get("account", "") or ""
        region = s.get("region", "") or ""
        svc = s.get("service_line", "") or ""
        published = s.get("published", "") or now_iso()

        refs = []
        if url:
            refs.append({"url": url, "label": s.get("source", url)})
        for e in ev:
            if isinstance(e, str) and e.startswith("CVE-"):
                refs.append({"url": url_for_cve(e), "label": f"NVD {e}"})
                refs.append({"url": cisa_url_for_cve(e), "label": f"CISA KEV catalog ({e})"})
            elif isinstance(e, str) and e.startswith("accession:"):
                refs.append({"url": url or "", "label": e})
            elif isinstance(e, str) and e.startswith("http"):
                refs.append({"url": e, "label": e})
            elif isinstance(e, str) and e:
                refs.append({"url": "", "label": e})

        seen_ref = set()
        dedup_refs = []
        for r in refs:
            k = (r.get("url", ""), r.get("label", ""))
            if k in seen_ref:
                continue
            seen_ref.add(k)
            dedup_refs.append(r)

        item = {
            "id": s.get("id", ""),
            "title": s.get("title", ""),
            "url": url,
            "summary": s.get("summary", ""),
            "source": s.get("source", ""),
            "lane": lane,
            "earliest_event_time_utc": published,
            "latest_event_time_utc": published,
            "published": published,
            "priority_score": float(s.get("score", 0) or 0),
            "confidence": float(s.get("confidence", 0) or 0),
            "recommendation": "",
            "references": dedup_refs,
            "account_type": (s.get("account_type", "") or "").lower(),
            "regulators": "—",
            "sources": s.get("source", "") or "—",
            "facets": {
                "accounts": [acct] if acct else [],
                "service_lines": [svc] if svc else [],
                "chris_regions": [region] if region else [],
                "account_types": [((s.get("account_type", "") or "other").lower())] if acct or s.get("account_type") else ["other"],
                "source_types": [s.get("source", "")] if s.get("source") else [],
                "partnerships": ["partnership"] if s.get("is_partnership") else [],
                "partnership_partner_a": [s.get("partner_a", "")] if s.get("partner_a") else [],
                "partnership_partner_b": [s.get("partner_b", "")] if s.get("partner_b") else [],
                "deal_values": [s.get("deal_value", "")] if s.get("deal_value") else [],
                "modalities": [s.get("modality", "")] if s.get("modality") else [],
                "deal_geographies": [s.get("deal_geography", "")] if s.get("deal_geography") else [],
                "deal_stages": [s.get("deal_stage", "")] if s.get("deal_stage") else [],
            },
        }

        k = (acct, lane, region)
        c = key_counts.get(k, 1)
        if lane == "cybersecurity" and item.get("references"):
            item["internal_corroboration"] = f"{c} related cybersecurity signals in the current window."
        elif c >= 3 and acct:
            item["internal_corroboration"] = f"{c} related signals for {acct} in lane={lane} (region={region or 'n/a'})."
        else:
            item["internal_corroboration"] = "None detected in the current window."

        item = make_analysis(item)
        items.append(item)

    payload = {
        "generated_at_utc": summary.get("generated_at_utc") or now_iso(),
        "items": items,
        "active_filters": {
            "include_text": include_terms,
            "exclude_text": exclude_terms,
        },
    }
    save_json(CACHE_DIR / "radar_signals.json", payload)
    save_json(CACHE_DIR / "radar_summary.json", summary)

    prof_path = CFG_DIR / "chris_profile.json"
    prof = load_json(prof_path) if prof_path.exists() else {}
    prof.setdefault("decision_lenses", [
        {"id": "ALL", "label": "All signals", "lanes": [], "min_score": 0},
        {"id": "GROW", "label": "Where to grow", "lanes": ["market_signals", "construction_capex", "competitive_intel", "science_trends"], "min_score": 0},
        {"id": "HIRE", "label": "Where to hire", "lanes": ["hiring_signals", "construction_capex", "market_signals"], "min_score": 0},
        {"id": "EXPOSED", "label": "Where I'm exposed", "lanes": ["margin_protection", "regulatory", "cybersecurity"], "min_score": 0},
        {"id": "CYBER", "label": "OT cyber mandates", "lanes": ["cybersecurity", "regulatory"], "min_score": 0},
        {"id": "DEALS", "label": "Partnerships / deals", "lanes": ["competitive_intel", "market_signals"], "min_score": 0},
    ])
    save_json(prof_path, prof)

    print(f"cache/radar_signals.json written with {len(items)} items.")
    print("cache/radar_summary.json updated.")
    print("config/chris_profile.json ensured.")


if __name__ == "__main__":
    main()
