import os, requests

def fetch(feed: dict, query: str, start_iso: str, end_iso: str, offset: int = 0, timeout=30):
    url = feed["url_or_endpoint"]
    params = {
        "keywordSearch": query,
        "pubStartDate": start_iso,
        "pubEndDate": end_iso,
        "resultsPerPage": 200,
        "startIndex": offset
    }
    headers = {}
    api_key = os.getenv("NVD_API_KEY","").strip()
    if api_key:
        headers["apiKey"] = api_key
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    vulns = (data.get("vulnerabilities") or [])
    out = []
    for vv in vulns:
        cve = (vv.get("cve") or {})
        cve_id = cve.get("id","") or ""
        descs = cve.get("descriptions") or []
        desc = ""
        for d in descs:
            if d.get("lang") == "en":
                desc = d.get("value","") or ""
                break
        out.append({
            "title": f"NVD CVE: {cve_id}".strip(),
            "link": f"https://nvd.nist.gov/vuln/detail/{cve_id}" if cve_id else "",
            "published": cve.get("published","") or "",
            "summary": desc.strip(),
            "source": "NIST NVD",
            "evidence": [cve_id],
            "raw": {"nvd": {"id": cve_id, "published": cve.get("published"), "lastModified": cve.get("lastModified")}}
        })
    return out, data.get("totalResults", 0)
