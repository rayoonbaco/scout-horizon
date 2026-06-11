import requests

def fetch(feed: dict, timeout=25):
    r = requests.get(feed["url_or_endpoint"], timeout=timeout)
    r.raise_for_status()
    data = r.json()
    vulns = data.get("vulnerabilities", []) or []
    out = []
    for v in vulns:
        cve = v.get("cveID","") or ""
        out.append({
            "title": f"CISA KEV: {cve} — {v.get('product','')}".strip(),
            "link": v.get("notes","") or "",
            "published": v.get("dateAdded","") or "",
            "summary": (v.get("shortDescription","") or "").strip(),
            "source": "CISA",
            "evidence": [cve],
            "raw": {"kev": v}
        })
    return out
