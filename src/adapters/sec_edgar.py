import requests, re

SEC_HEADERS_HINT = "Set a descriptive User-Agent per SEC fair access (include contact email)."

def fetch_company_tickers(url: str, user_agent: str, timeout=25):
    r = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    r.raise_for_status()
    return r.json()

def fetch_submissions(url_template: str, cik10: str, user_agent: str, timeout=25):
    url = url_template.replace("{CIK10}", cik10)
    r = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    r.raise_for_status()
    return r.json()

def filings_to_events(submissions_json: dict, cik10: str, forms_allow: list[str]):
    out = []
    company = (submissions_json.get("name") or "").strip() or f"CIK {cik10}"
    recent = (((submissions_json.get("filings") or {}).get("recent")) or {})
    forms = recent.get("form") or []
    accs = recent.get("accessionNumber") or []
    dates = recent.get("filingDate") or []
    primary_docs = recent.get("primaryDocument") or []
    # Build
    for i, form in enumerate(forms):
        if not form:
            continue
        # allowlist match, supports wildcards like 424B*
        ok = any((fa.endswith("*") and form.startswith(fa[:-1])) or (form == fa) for fa in forms_allow)
        if not ok:
            continue
        accession = (accs[i] if i < len(accs) else "") or ""
        filing_date = (dates[i] if i < len(dates) else "") or ""
        prim = (primary_docs[i] if i < len(primary_docs) else "") or ""
        accession_nodash = accession.replace("-", "")
        link = ""
        if accession_nodash and prim:
            link = f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{accession_nodash}/{prim}"
        elif accession_nodash:
            link = f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{accession_nodash}/"
        out.append({
            "title": f"{company} filed {form}",
            "link": link,
            "published": filing_date,
            "summary": "Official SEC EDGAR filing (structured signal).",            "source": "SEC EDGAR",
            "evidence": [f"accession:{accession}"] if accession else [],
            "raw": {"sec": {"cik": cik10, "accession": accession, "form": form}}
        })
    return out
