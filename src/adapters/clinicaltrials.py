from __future__ import annotations
import requests


def fetch(feed: dict, query: str, page_token: str | None = None, page_size: int = 100, timeout: int = 30):
    url = feed["url_or_endpoint"]
    params = {
        "query.term": query,
        "pageSize": max(1, min(int(page_size or 100), 100)),
        "format": "json"
    }
    if page_token:
        params["pageToken"] = page_token
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    studies = data.get("studies", []) or []
    next_token = data.get("nextPageToken")
    out = []
    for s in studies:
        ps = (s.get("protocolSection") or {})
        idmod = (ps.get("identificationModule") or {})
        status = (ps.get("statusModule") or {})
        desc = (ps.get("descriptionModule") or {})
        cond = (ps.get("conditionsModule") or {})
        design = (ps.get("designModule") or {})
        elig = (ps.get("eligibilityModule") or {})
        contacts = (ps.get("contactsLocationsModule") or {})
        sponsor = ((ps.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}).get("name", "")
        nct = idmod.get("nctId", "") or ""
        title = idmod.get("briefTitle", "") or ""
        summary = (desc.get("briefSummary") or "").strip()
        out.append({
            "title": f"Clinical Trial: {title}".strip(),
            "link": f"https://clinicaltrials.gov/study/{nct}" if nct else "",
            "published": status.get("lastUpdatePostDateStruct", {}).get("date", "") or status.get("studyFirstPostDateStruct", {}).get("date", "") or "",
            "summary": summary,
            "source": "ClinicalTrials.gov",
            "evidence": [nct] if nct else [],
            "raw": {
                "clinicaltrials": {
                    "nctId": nct,
                    "sponsor": sponsor,
                    "conditions": cond.get("conditions", []) or [],
                    "keywords": cond.get("keywords", []) or [],
                    "studyType": design.get("studyType", "") or "",
                    "healthyVolunteers": elig.get("healthyVolunteers", False),
                    "eligibility": elig,
                    "locations": contacts.get("locations", []) or []
                }
            }
        })
    return out, next_token
