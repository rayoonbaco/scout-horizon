from __future__ import annotations
import feedparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

def _to_iso(dt) -> str:
    if not dt:
        return ""
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
    return ""

def _parse_date(entry) -> datetime | None:
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                return parsedate_to_datetime(val)
            except Exception:
                pass
    # feedparser sometimes provides *_parsed
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None

def fetch(feed: dict, start_dt: datetime, end_dt: datetime, timeout: int = 25):
    """
    Parse a single RSS/Atom feed. Returns a list[dict] events with fields:
    title, link, published, summary, source, evidence, raw
    """
    url = (feed.get("url_or_endpoint") or "").strip()
    if not url:
        return []
    parsed = feedparser.parse(url)
    out = []
    for e in (parsed.entries or []):
        link = (e.get("link") or "").strip()
        title = (e.get("title") or "").strip()
        summary = (e.get("summary") or e.get("description") or "").strip()
        dt = _parse_date(e)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # time window filter if date is present
        if dt:
            if dt < start_dt.replace(tzinfo=timezone.utc) or dt > end_dt.replace(tzinfo=timezone.utc):
                continue
        domain = ""
        try:
            domain = urlparse(link).netloc.lower()
        except Exception:
            domain = ""
        source = (feed.get("source_override") or "").strip() or domain or (feed.get("label") or "RSS")
        out.append({
            "title": title,
            "link": link,
            "published": _to_iso(dt) if dt else "",
            "summary": summary,
            "source": source,
            "evidence": [link] if link else [],
            "raw": {"rss": {"feed": url, "id": e.get("id",""), "domain": domain}}
        })
    return out
