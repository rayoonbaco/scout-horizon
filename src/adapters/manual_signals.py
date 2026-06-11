from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_PATHS = [
    Path("inputs") / "manual_signals.csv",
    Path("inputs") / "manual_urls.csv",
]

def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def fetch(feed: dict, project_dir: Path):
    """
    Ingest user-curated signals (copy/paste from Googling) in a ToS-safe way.
    Expected file: inputs/manual_signals.csv

    Columns (minimum): url
    Recommended: title, summary, source, published
    Optional: lane, account, account_type, region, service_line, topic, tags, is_partnership, partner_a, partner_b, deal_value, modality, deal_stage, deal_geography
    """
    paths = []
    for p in (feed.get("paths") or []):
        paths.append(project_dir / p)
    if not paths:
        paths = [project_dir / p for p in DEFAULT_PATHS]

    found = None
    for p in paths:
        if p.exists():
            found = p
            break
    if not found:
        return []

    out = []
    with found.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or row.get("link") or "").strip()
            if not url:
                continue
            title = (row.get("title") or "").strip() or url
            summary = (row.get("summary") or row.get("snippet") or "").strip()
            published = (row.get("published") or "").strip() or _now_iso()
            source = (row.get("source") or "").strip()
            if not source:
                try:
                    source = urlparse(url).netloc.lower()
                except Exception:
                    source = "manual"
            tags = (row.get("tags") or "").strip()
            tags_list = [t.strip() for t in tags.split(";") if t.strip()] if tags else ["manual"]
            out.append({
                "title": title,
                "link": url,
                "published": published,
                "summary": summary,
                "source": source,
                "lane": (row.get("lane") or "").strip(),
                "account": (row.get("account") or "").strip(),
                "account_type": (row.get("account_type") or "").strip(),
                "region": (row.get("region") or "").strip(),
                "service_line": (row.get("service_line") or "").strip(),
                "topic": (row.get("topic") or "").strip(),
                "tags": tags_list,
                "is_partnership": str(row.get("is_partnership") or "").strip().lower() in ("1","true","yes","y"),
                "partner_a": (row.get("partner_a") or "").strip(),
                "partner_b": (row.get("partner_b") or "").strip(),
                "deal_value": (row.get("deal_value") or "").strip(),
                "modality": (row.get("modality") or "").strip(),
                "deal_stage": (row.get("deal_stage") or "").strip(),
                "deal_geography": (row.get("deal_geography") or "").strip(),
                "evidence": [url],
                "raw": {"manual": {"file": str(found.name)}},
            })
    return out
