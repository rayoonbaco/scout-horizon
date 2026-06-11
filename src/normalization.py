import re
from datetime import datetime
from dateutil import parser as dtparser

LANES = [
  "market_signals","competitive_intel","hiring_signals","regulatory",
  "cybersecurity","science_trends","margin_protection","construction_capex"
]

def parse_dt(dt_str: str):
    if not dt_str:
        return None
    try:
        return dtparser.parse(dt_str)
    except Exception:
        return None

def normalize_published(dt_str: str) -> str:
    dt = parse_dt(dt_str)
    if not dt:
        return ""
    # ISO without timezone (viewer can interpret as UTC/local as needed)
    return dt.replace(tzinfo=None).isoformat(timespec="seconds")

def map_region(text: str, regions_map: dict) -> tuple[str, float]:
    if not text:
        return ("", 0.0)
    t = text.lower()
    best = ("", 0.0)
    for region, tokens in regions_map.items():
        hits = 0
        for tok in tokens:
            if tok and tok.lower() in t:
                hits += 1
        if hits > 0:
            conf = min(1.0, 0.35 + 0.15*hits)
            if conf > best[1]:
                best = (region, conf)
    return best

def tag_service_line(text: str, topics_cfg: dict) -> tuple[str, str, float]:
    # Returns (service_line, topic_name, confidence)
    if not text:
        return ("", "", 0.0)
    t = text.lower()
    best = ("", "", 0.0)
    for svc, items in topics_cfg.get("service_lines", {}).items():
        for it in items:
            # very lightweight: match a few key tokens from the query string
            q = it.get("query","")
            # extract candidate tokens (words/phrases)
            tokens = [w.strip("'\"()") for w in re.split(r"\s+OR\s+|\s+AND\s+|\W+", q) if w and len(w) > 3]
            hits = 0
            for tok in tokens[:20]:
                if tok.lower() in t:
                    hits += 1
            if hits:
                conf = min(1.0, 0.30 + 0.08*hits)
                if conf > best[2]:
                    best = (svc, it.get("name",""), conf)
    return best

def lane_from_tags(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["cve","kev","ransomware","isa 62443","iec 62443","exploit"]):
        return "cybersecurity"
    if any(k in t for k in ["warning letter","consent decree","recall","osha","fda","compliance"]):
        return "regulatory"
    if any(k in t for k in ["job","hiring","recruit","career","openings"]):
        return "hiring_signals"
    if any(k in t for k in ["groundbreaking","permit","construction","capex","expansion","facility"]):
        return "construction_capex"
    if any(k in t for k in ["trial","phase","clinical","nct"]):
        return "science_trends"
    if any(k in t for k in ["pricing","inflation","lead time","shortage","margin"]):
        return "margin_protection"
    if any(k in t for k in ["acquisition","partnership","competitor","launch"]):
        return "competitive_intel"
    return "market_signals"
