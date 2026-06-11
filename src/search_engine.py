import os, hashlib, json, re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from html import unescape
import requests
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"

# If Google is unavailable/misconfigured, Web Assist can fall back to RSS feeds.
DEFAULT_RSS_FEEDS = [
    {"name": "Fierce Pharma", "url": "https://www.fiercepharma.com/rss/xml"},
    {"name": "BioPharma Dive", "url": "https://www.biopharmadive.com/feeds/news/"},
    {"name": "Endpoints News", "url": "https://endpts.com/feed/"},
    {"name": "STAT", "url": "https://www.statnews.com/feed/"},
    {"name": "FDA Press Releases", "url": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml"},
]

class SearchConfigError(RuntimeError):
    """Raised when Web Assist search is not configured (missing API key / cx)."""
    pass


def _clean_text(value: Any) -> str:
    text = unescape(str(value or ''))
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _stable_id(prefix: str, s: str) -> str:
    h = hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()[:24]
    return f"{prefix}_{h}"

def _domain(url: str) -> str:
    try:
        d = urlparse(url).netloc.lower()
        if d.startswith("www."):
            d = d[4:]
        return d
    except Exception:
        return ""

def _load_google_config(explicit: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Resolve Google PSE config from:
      1) explicit dict (api_key, cx)
      2) environment vars GOOGLE_PSE_KEY, GOOGLE_PSE_CX
    """
    if explicit and explicit.get("api_key") and explicit.get("cx"):
        return {"api_key": explicit["api_key"], "cx": explicit["cx"]}

    key = (os.getenv("GOOGLE_PSE_KEY") or "").strip()
    cx  = (os.getenv("GOOGLE_PSE_CX") or "").strip()
    if not key or not cx:
        raise SearchConfigError(
            "Web Assist is not configured. Add GOOGLE_PSE_KEY and GOOGLE_PSE_CX in the dashboard Setup panel (one-time), then try again."
        )
    return {"api_key": key, "cx": cx}


def _load_rss_feeds() -> List[Dict[str, str]]:
    """Load RSS feeds from config/rss_feeds.json (if present), else defaults."""
    cfg_path = os.path.join(os.getcwd(), "config", "rss_feeds.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            feeds = json.load(f)
        if isinstance(feeds, dict):
            feeds = feeds.get("feeds") or []
        out = []
        for x in feeds or []:
            name = (x.get("name") or "").strip()
            url = (x.get("url") or "").strip()
            if name and url:
                out.append({"name": name, "url": url})
        return out or DEFAULT_RSS_FEEDS
    except Exception:
        return DEFAULT_RSS_FEEDS


def _rss_parse(xml_text: str) -> List[Dict[str, str]]:
    """Parse RSS/Atom into a normalized list of {title,url,snippet}."""
    items: List[Dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return items

    # RSS 2.0: <rss><channel><item>...
    channel = root.find("channel")
    if channel is not None:
        for it in channel.findall("item"):
            title = _clean_text((it.findtext("title") or "").strip())
            link = (it.findtext("link") or "").strip()
            desc = _clean_text((it.findtext("description") or it.findtext("summary") or "").strip())
            if link:
                items.append({"title": title or link, "url": link, "snippet": desc})
        return items

    # Atom: <feed><entry>...
    for entry in root.findall(".//{*}entry"):
        title = _clean_text((entry.findtext("{*}title") or "").strip())
        link = ""
        for ln in entry.findall("{*}link"):
            href = ln.attrib.get("href")
            rel = (ln.attrib.get("rel") or "").lower()
            if href and (rel in ("", "alternate")):
                link = href
                break
        if not link:
            link = (entry.findtext("{*}link") or "").strip()
        summary = _clean_text((entry.findtext("{*}summary") or entry.findtext("{*}content") or "").strip())
        if link:
            items.append({"title": title or link, "url": link, "snippet": summary})
    return items


def rss_search(query: str, forced_source: Optional[str] = None, num: int = 6) -> List[Dict[str, Any]]:
    """A ToS-safe, no-keys fallback search that pulls from a curated RSS/Atom feed list."""
    feeds = _load_rss_feeds()
    num = max(1, min(int(num or 6), 20))

    # Normalize query: drop "site:domain" (RSS can't honor it); keep the terms.
    q = (query or "").strip()
    if q.lower().startswith("site:"):
        parts = q.split(None, 1)
        q = parts[1] if len(parts) > 1 else ""

    tokens = [t.strip().lower() for t in q.replace(",", " ").split() if t.strip()]
    if not tokens:
        return []

    selected = feeds
    if forced_source:
        fs = forced_source.strip().lower()
        match = [f for f in feeds if f["name"].strip().lower() == fs]
        if not match:
            match = [f for f in feeds if fs.replace(" ", "") in f["name"].lower().replace(" ", "")]
        if match:
            selected = match

    out: List[Dict[str, Any]] = []
    seen = set()

    for feed in selected:
        try:
            r = requests.get(feed["url"], timeout=25, headers={"User-Agent": "StrategicRadar/1.0"})
            if not r.ok:
                continue
            items = _rss_parse(r.text)
        except Exception:
            continue

        for it in items:
            text = f"{it.get('title','')} {it.get('snippet','')}".lower()
            if all(tok in text for tok in tokens):
                url = (it.get("url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                out.append({
                    "url": url,
                    "name": it.get("title") or url,
                    "snippet": (it.get("snippet") or "")[:400],
                    "displayLink": _domain(url),
                    "_forced_source": feed["name"],
                })
                if len(out) >= num:
                    break
        if len(out) >= num:
            break

    return out

def google_pse_search(query: str, num: int = 6, start: int = 1, explicit_cfg: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    Google Programmable Search Engine (Custom Search JSON API).
    - num: 1..10 per request
    - start: 1..91 (in steps of num) depending on quota
    Returns list of dicts with keys compatible with map_result_to_signal().
    """
    cfg = _load_google_config(explicit_cfg)
    num = max(1, min(int(num or 6), 10))
    start = max(1, min(int(start or 1), 91))

    params = {
        "key": cfg["api_key"],
        "cx": cfg["cx"],
        "q": query,
        "num": num,
        "start": start,
        "safe": "active",
    }
    r = requests.get(GOOGLE_CSE_ENDPOINT, params=params, timeout=25)
    if r.status_code == 403:
        # Typically: invalid key, quota, or API not enabled
        raise SearchConfigError(f"Google PSE request was forbidden (403). Check API key, API enabled, and quota. Details: {r.text[:200]}")
    if not r.ok:
        raise RuntimeError(f"Google PSE search failed: HTTP {r.status_code} {r.text[:200]}")

    data = r.json()
    items = data.get("items") or []
    out: List[Dict[str, Any]] = []
    for it in items:
        out.append({
            "url": it.get("link") or "",
            "name": it.get("title") or "",
            "snippet": it.get("snippet") or "",
            "displayLink": it.get("displayLink") or "",
        })
    return out


def webassist_search(query: str, num: int = 6, start: int = 1, explicit_cfg: Optional[Dict[str, str]] = None, forced_source: Optional[str] = None) -> List[Dict[str, Any]]:
    """Try Google PSE first; if it fails, fall back to RSS."""
    try:
        return google_pse_search(query=query, num=num, start=start, explicit_cfg=explicit_cfg)
    except SearchConfigError:
        return rss_search(query=query, forced_source=forced_source, num=num)
    except Exception:
        return rss_search(query=query, forced_source=forced_source, num=num)

def build_queries(keyword: str, company: str, targets: List[Dict[str, Any]], include_general: bool = True) -> List[Tuple[str, Optional[str]]]:
    """
    Build query list.
    - If targets include domains, we use site:domain keyword/company combos.
    - forced_source is a friendly label from target (e.g., 'FiercePharma') to use in the dropdown.
    """
    keyword = (keyword or "").strip()
    company = (company or "").strip()
    base_terms = " ".join([t for t in [keyword, company] if t]).strip()
    if not base_terms:
        return []

    queries: List[Tuple[str, Optional[str]]] = []

    # General query (no site restriction) – useful for broad "Google it" behavior
    if include_general:
        queries.append((base_terms, None))

    for t in targets or []:
        name = t.get("name")
        domains = t.get("domains") or []
        # If a "target" is a label without domains, skip (can't site-restrict)
        for d in domains:
            d = (d or "").strip()
            if not d:
                continue
            queries.append((f"site:{d} {base_terms}", name))

    # de-dupe queries while preserving order
    seen=set()
    uniq=[]
    for q, s in queries:
        k=(q, s or "")
        if k in seen: 
            continue
        seen.add(k)
        uniq.append((q, s))
    return uniq

def map_result_to_signal(res: Dict[str, Any], forced_source: Optional[str] = None) -> Dict[str, Any]:
    url = res.get("url") or ""
    title = _clean_text(res.get("name") or res.get("title") or url)
    snippet = _clean_text(res.get("snippet") or "")
    dom = _domain(url)
    source = forced_source or dom or "web"

    return {
        "id": _stable_id("web", url),
        "title": title,
        "url": url,
        "source": source,
        "source_domain": dom,
        "lane": "web_search",
        "time": _utcnow_iso(),
        "priority": 0.50,
        "confidence": 0.65,
        "why_it_matters": "Web Assist search result (public web).",
        "observation": snippet,
        "recommended_action": "Open the link and confirm relevance.",
        "evidence": [{"type":"link","url":url}],
        "tags": ["web_assist"],
    }

def merge_into_cache(cache_path: str, new_signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge web signals into radar cache JSON at cache_path.
    - Dedup by URL
    - Append to events list
    - Store last ingest metadata in active_filters
    """
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        payload = {"events": [], "active_filters": {}}

    events = payload.get("events") or payload.get("items") or []
    if isinstance(events, dict):
        events = list(events.values())

    existing_urls = set()
    for e in events:
        u = (e.get("url") or "").strip()
        if u:
            existing_urls.add(u)

    added = 0
    for s in new_signals:
        u = (s.get("url") or "").strip()
        if not u or u in existing_urls:
            continue
        events.append(s)
        existing_urls.add(u)
        added += 1

    payload["events"] = events
    af = payload.get("active_filters") or {}
    af["last_web_ingest_at"] = _utcnow_iso()
    af["last_web_ingest_added"] = added
    payload["active_filters"] = af
    return payload
