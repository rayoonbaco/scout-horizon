import os, requests

def fetch(feed: dict, query: str, start_date: str, end_date: str, offset: int = 0, timeout=30):
    api_key = os.getenv("SAM_API_KEY", "").strip()
    if not api_key:
        return [], 0, "Missing SAM_API_KEY"
    url = feed["url_or_endpoint"]
    params = {
        "api_key": api_key,
        "q": query,
        "postedFrom": start_date,
        "postedTo": end_date,
        "limit": 100,
        "offset": offset
    }
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    items = data.get("opportunitiesData", []) or []
    out = []
    for it in items:
        out.append({
            "title": it.get("title", "") or "SAM.gov opportunity",
            "link": it.get("uiLink", "") or "",
            "published": it.get("postedDate", "") or "",
            "summary": (it.get("description", "") or "").strip(),
            "source": "SAM.gov",
            "evidence": [it.get("noticeId", "") or ""],
            "raw": {"sam": {"noticeId": it.get("noticeId")}},
        })
    total = int(data.get("totalRecords", 0) or 0)
    return out, total, None
