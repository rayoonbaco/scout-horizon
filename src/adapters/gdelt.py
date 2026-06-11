import requests
from datetime import datetime, timedelta

def fetch(feed: dict, query: str, start_utc: str, end_utc: str, timeout=25):
    url = feed['url_or_endpoint']
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": 250,
        "sort": "HybridRel",
        "startdatetime": start_utc,
        "enddatetime": end_utc,
    }
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    articles = data.get("articles", []) or []
    out = []
    for a in articles:
        out.append({
            "title": a.get("title","") or "",
            "link": a.get("url","") or "",
            "published": a.get("seendate","") or a.get("date","") or "",
            "summary": a.get("snippet","") or "",
            "source": a.get("domain","") or "GDELT",
            "evidence": [a.get("url","")],
            "raw": {"gdelt": {k:a.get(k) for k in ("sourceCountry","language","domain","url","seendate","socialimage")}}
        })
    return out
