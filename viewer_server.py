import asyncio
import json
import os
import re
import subprocess
import sys
import traceback
from html import unescape
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.search_engine import SearchConfigError, build_queries, google_pse_search, map_result_to_signal, rss_search
from src.strategy_intel import rank_signals, strategy_audit

ROOT = Path(__file__).resolve().parent
VIEWER_DIR = ROOT / "viewer"
CACHE_PATH = ROOT / "cache" / "radar_signals.json"
STATE_PATH = ROOT / "config" / "webassist_state.json"
GOOGLE_CFG_PATH = ROOT / "config" / "webassist_google_pse.json"
TARGETS_PATH = ROOT / "config" / "source_targets.json"
RUN_LOG_PATH = ROOT / "outputs" / "run_log.json"
APP_VERSION = str(int(datetime.now(timezone.utc).timestamp()))
DEMO_KEYWORD = "pharma partnership"
DEMO_DEFAULT_MAX_SIGNALS = 12
DEMO_TARGETS = ["Fierce Pharma", "BioPharma Dive", "Endpoints News", "FDA Press Releases", "STAT"]
STATIC_DEMO_SIGNALS = [
    {"title": "Fierce Pharma latest deal and manufacturing coverage", "url": "https://www.fiercepharma.com/", "snippet": "Built-in fallback item focused on life sciences, pharma operations, and business moves.", "source": "Fierce Pharma"},
    {"title": "BioPharma Dive latest operations and policy coverage", "url": "https://www.biopharmadive.com/", "snippet": "Built-in fallback item focused on biopharma operations, regulation, and strategy.", "source": "BioPharma Dive"},
    {"title": "Endpoints News biotech and pharma feed", "url": "https://endpts.com/feed/", "snippet": "Built-in fallback item focused on biotech, drug development, and deal activity.", "source": "Endpoints News"},
    {"title": "FDA press release monitor", "url": "https://www.fda.gov/news-events/fda-newsroom/press-announcements", "snippet": "Built-in fallback item focused on U.S. drug and facility regulatory developments.", "source": "FDA Press Releases"},
    {"title": "FDA warning letters search", "url": "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters", "snippet": "Built-in fallback item focused on inspections, compliance, and warning letters.", "source": "FDA (Warning Letters / Inspections)"},
    {"title": "SEC filings company search", "url": "https://www.sec.gov/edgar/search/", "snippet": "Built-in fallback item focused on public company filings and disclosures.", "source": "SEC Filings (EDGAR)"},
    {"title": "ISPE guidance resources", "url": "https://ispe.org/publications/guidance-documents", "snippet": "Built-in fallback item focused on pharma engineering and regulated facility standards.", "source": "ISPE"},
    {"title": "Pharmaceutical Manufacturing news", "url": "https://www.pharmamanufacturing.com/", "snippet": "Built-in fallback item focused on plant operations, quality, and manufacturing execution.", "source": "Pharma Manufacturing"},
    {"title": "EMA regulatory updates", "url": "https://www.ema.europa.eu/en/news", "snippet": "Built-in fallback item focused on European regulatory updates relevant to life sciences.", "source": "EMA Regulatory Updates"},
    {"title": "Deloitte life sciences outlook", "url": "https://www.deloitte.com/us/en/industries/life-sciences-health-care.html", "snippet": "Built-in fallback item focused on life sciences strategy and market outlooks.", "source": "Deloitte Life Sciences"},
    {"title": "McKinsey life sciences insights", "url": "https://www.mckinsey.com/industries/life-sciences/our-insights", "snippet": "Built-in fallback item focused on life sciences operations and strategy.", "source": "McKinsey Life Sciences"},
    {"title": "PwC health industries insights", "url": "https://www.pwc.com/us/en/industries/health-industries.html", "snippet": "Built-in fallback item focused on health industries strategy and market developments.", "source": "PwC Life Sciences"}
]

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    text = unescape(str(value or ''))
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def clean_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(signal or {})
    for key in [
        'title', 'source', 'source_domain', 'time', 'observation', 'snippet',
        'why_it_matters', 'recommended_action', 'recommendation'
    ]:
        if key in cleaned:
            cleaned[key] = clean_text(cleaned.get(key))
    if cleaned.get('url'):
        cleaned['url'] = str(cleaned.get('url')).strip()
    return cleaned

def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists(): return default
        with path.open("r", encoding="utf-8") as f: return json.load(f)
    except Exception:
        return default

def save_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f: json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def load_env_file(path: Path) -> None:
    if not path.exists(): return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            key, value = line.split("=", 1)
            key = key.strip(); value = value.strip().strip('"').strip("'")
            if key and not os.getenv(key): os.environ[key] = value
    except Exception:
        pass

load_env_file(ROOT / ".env")

class IngestRequest(BaseModel):
    keyword: str = ""
    company: str = ""
    mode: str = "broad_and_targeted"
    sources: Optional[List[str]] = None
    max_results_per_query: int = 6

class DemoFillResponse(BaseModel):
    ok: bool
    message: str
    state: Dict[str, Any]

class BasicResponse(BaseModel):
    ok: bool
    message: str

class IngestResponse(BaseModel):
    ok: bool
    mode_used: str
    added: int
    total_results: int
    message: str
    state: Dict[str, Any]

class RunAllResponse(BaseModel):
    ok: bool
    refreshed: bool
    added: int
    total_results: int
    mode_used: str
    message: str
    state: Dict[str, Any]

class GoogleConfigRequest(BaseModel):
    api_key: str = ""
    cx: str = ""

app = FastAPI(title="Scout Horizon")

# PASS 15A-R - Windows request write-collision guard START
# Windows can briefly lock JSON files when several browser tabs, rapid clicks, or smoke tests
# hit write-heavy API routes at the same time. This middleware serializes those routes
# without changing the existing API behavior.
try:
    PASS15A_WRITE_GUARD_LOCK
except NameError:
    PASS15A_WRITE_GUARD_LOCK = asyncio.Lock()

PASS15A_WRITE_GUARD_PREFIXES = (
    "/api/demo_fill",
    "/api/run_all",
    "/api/refresh",
    "/api/ingest",
    "/api/reset",
    "/api/webassist",
)

@app.middleware("http")
async def pass15a_windows_write_collision_guard(request, call_next):
    path = request.url.path
    write_like = request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
    guarded_path = any(path.startswith(prefix) for prefix in PASS15A_WRITE_GUARD_PREFIXES)

    if write_like or guarded_path:
        async with PASS15A_WRITE_GUARD_LOCK:
            return await call_next(request)

    return await call_next(request)
# PASS 15A-R - Windows request write-collision guard END

app.mount("/viewer", StaticFiles(directory=str(VIEWER_DIR), html=True), name="viewer")

@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url=f"/viewer/index.html?v={APP_VERSION}")

@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    return {"ok": True, "service": "executive-decision-intelligence-engine", "version": APP_VERSION, "time": utc_now()}

@app.get("/viewer/app.js")
def viewer_app_js() -> FileResponse:
    return FileResponse(VIEWER_DIR / "app.js", media_type="application/javascript")

@app.get("/api/targets")
def api_targets() -> Dict[str, Any]:
    data = load_json(TARGETS_PATH, {"targets": []})
    return {"ok": True, "targets": data.get("targets") or []}

def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("&", " and ").replace("/", " ").replace("-", " ").split())

def _tokenize(value: str) -> List[str]:
    text = _norm_text(value)
    return [part for part in text.split() if len(part) >= 3]

def _source_aliases(selected_sources: List[str]) -> set:
    aliases = set()
    for raw in selected_sources or []:
        text = _norm_text(raw)
        if not text:
            continue
        aliases.add(text)
        aliases.add(text.replace(" ", ""))
        aliases.add(text.replace(" and ", " "))
        if "(" in text:
            aliases.add(text.split("(", 1)[0].strip())
        if "fda" in text:
            aliases.update({"fda", "food and drug administration"})
        if "sec" in text:
            aliases.update({"sec", "edgar"})
        if "pharma manufacturing" in text:
            aliases.update({"pharmaceutical manufacturing", "pharma manufacturing"})
    return {a for a in aliases if a}

def signal_matches_state(signal: Dict[str, Any], state: Dict[str, Any]) -> bool:
    selected_sources = state.get("sources") or []
    keyword_tokens = _tokenize(state.get("keyword") or "")
    company_tokens = _tokenize(state.get("company") or "")
    haystack = _norm_text(" ".join([
        signal.get("title") or "",
        signal.get("source") or "",
        signal.get("source_domain") or "",
        signal.get("observation") or signal.get("snippet") or "",
        signal.get("why_it_matters") or "",
    ]))
    if selected_sources:
        aliases = _source_aliases(selected_sources)
        source_text = _norm_text(" ".join([signal.get("source") or "", signal.get("source_domain") or ""]))
        if not any(alias in source_text or alias in haystack for alias in aliases):
            return False
    terms = keyword_tokens + company_tokens
    if not terms:
        return True
    required = min(2, len(terms))
    hits = sum(1 for token in terms if token in haystack)
    return hits >= required or any((signal.get("source") or "").lower().startswith(src.lower()) for src in selected_sources)

def filtered_signal_items(state: Dict[str, Any], payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    payload = payload or load_signal_payload()
    items = payload.get("items") or []
    filtered = [clean_signal(item) for item in items if isinstance(item, dict) and signal_matches_state(item, state)]
    # Public demo guardrail: if the cache has been replaced by a raw/high-volume feed,
    # keep the first impression curated instead of showing thousands of generic items.
    visible = filtered if filtered else items[:DEMO_DEFAULT_MAX_SIGNALS]
    if len(visible) > DEMO_DEFAULT_MAX_SIGNALS and str(state.get("last_mode_used") or "").lower() == "curated_demo":
        visible = visible[:DEMO_DEFAULT_MAX_SIGNALS]
    # Pass 17: enrich and rank visible items with explicit strategy relevance so the
    # right-side brief is backed by a defensible decision-intelligence model.
    try:
        return rank_signals(visible, state)
    except Exception:
        return visible

@app.get("/api/signals")
def api_signals(request: Request) -> Dict[str, Any]:
    payload = load_signal_payload()
    state = load_state()
    qp = request.query_params
    keyword = (qp.get("query") or qp.get("keyword") or qp.get("q") or "").strip()
    company = (qp.get("company") or qp.get("company_focus") or qp.get("account") or "").strip()
    mode = (qp.get("mode") or qp.get("coverage") or "").strip()
    source = (qp.get("source") or qp.get("target") or qp.get("source_filter") or "").strip()
    if keyword:
        state["keyword"] = keyword
    if company:
        state["company"] = company
    elif any(k in qp for k in ["company", "company_focus", "account"]):
        state["company"] = ""
    if mode:
        state["mode"] = mode
    if source and source.lower() not in {"all available sources", "[all available sources]", "all", "any"}:
        state["sources"] = [source]
    elif any(k in qp for k in ["source", "target", "source_filter"]):
        state["sources"] = []
    items = filtered_signal_items(state, payload)
    return {"ok": True, "items": items, "count": len(items), "updated_at": payload.get("active_filters", {}).get("last_ui_update_at") or payload.get("generated_at_utc") or utc_now(), "state_used": state, "strategy_engine": "pass17d_company_filter_truthfulness"}


@app.get("/api/state")
def api_state(request: Request) -> Dict[str, Any]:
    payload = load_signal_payload()
    state = load_state()
    filtered_items = filtered_signal_items(state, payload)
    run_log = load_json(RUN_LOG_PATH, {})
    return {"ok": True, "version": APP_VERSION, "state": state, "signals_count": len(filtered_items), "last_action": run_log.get("last_action") or state.get("last_action") or "Ready", "last_error": run_log.get("last_error") or state.get("last_error") or "", "last_updated": run_log.get("last_updated") or state.get("last_updated") or payload.get("active_filters", {}).get("last_ui_update_at") or payload.get("generated_at_utc") or "", "last_mode_used": run_log.get("last_mode_used") or state.get("last_mode_used") or "", "base_url": str(request.base_url).rstrip("/") }

@app.get("/api/webassist/config")
def get_google_config_status() -> Dict[str, Any]:
    cfg = read_google_cfg(); configured = bool(cfg.get("api_key") and cfg.get("cx"))
    return {"ok": True, "configured": configured, "message": "Configured" if configured else "Google PSE optional. RSS/demo mode still works. For hosted demos, use Render environment variables instead of saving keys in the browser."}

@app.post("/api/webassist/config")
def set_google_config(req: GoogleConfigRequest) -> Dict[str, Any]:
    if os.getenv("ALLOW_PUBLIC_CONFIG_WRITE", "false").lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=403, detail="Public demo mode keeps Google credentials out of the hosted app. Set GOOGLE_PSE_KEY and GOOGLE_PSE_CX as Render environment variables instead.")
    save_json_atomic(GOOGLE_CFG_PATH, {"api_key": req.api_key.strip(), "cx": req.cx.strip()})
    return get_google_config_status()

@app.post("/api/webassist/test")
def test_google_config() -> Dict[str, Any]:
    cfg = read_google_cfg()
    if not cfg.get("api_key") or not cfg.get("cx"): raise HTTPException(status_code=400, detail="Google key and cx are not saved yet.")
    try:
        results = google_pse_search("site:sec.gov 8-K", num=1, explicit_cfg=cfg)
        return {"ok": True, "message": "Google test succeeded.", "sample_title": (results[0].get("name") if results else "No sample title returned")}
    except SearchConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Google test failed: {exc}")

@app.post("/api/demo_fill", response_model=DemoFillResponse)
def api_demo_fill() -> DemoFillResponse:
    state = default_state(); state.update({"keyword": DEMO_KEYWORD, "mode": "broad_and_targeted", "sources": DEMO_TARGETS, "last_action": "Demo defaults loaded", "last_updated": utc_now()})
    save_state(state); write_run_log("Demo defaults loaded", "", "demo_fill")
    return DemoFillResponse(ok=True, message="Demo defaults loaded.", state=state)

@app.post("/api/ingest", response_model=IngestResponse)
def api_ingest(req: Optional[IngestRequest] = None) -> IngestResponse:
    current = load_state()
    if req is None:
        req = IngestRequest(keyword=current.get("keyword") or "", company=current.get("company") or "", mode=current.get("mode") or "broad_and_targeted", sources=current.get("sources") or [], max_results_per_query=int(current.get("max_results_per_query") or 6))
    state = normalize_state_from_request(req); save_state(state)
    try:
        results, mode_used = perform_ingest(state)
        payload, added = merge_signals(results)
        payload.setdefault("active_filters", {})["last_ui_update_at"] = utc_now(); save_json_atomic(CACHE_PATH, payload)
        state.update({"last_action": f"Added {added} signals", "last_error": "", "last_updated": utc_now(), "last_mode_used": mode_used}); save_state(state); write_run_log(state["last_action"], "", mode_used)
        return IngestResponse(ok=True, mode_used=mode_used, added=added, total_results=len(results), message=f"Added {added} signals at {state['last_updated']}", state=state)
    except Exception as exc:
        state.update({"last_error": str(exc), "last_action": "Ingest failed", "last_updated": utc_now()}); save_state(state); write_run_log("Ingest failed", str(exc), "error")
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/refresh", response_model=BasicResponse)
def api_refresh() -> BasicResponse:
    try:
        run_refresh_pipeline(); payload = load_signal_payload(); payload.setdefault("active_filters", {})["last_ui_update_at"] = utc_now(); save_json_atomic(CACHE_PATH, payload); write_run_log("Radar refreshed", "", "refresh")
        return BasicResponse(ok=True, message="Radar refreshed.")
    except Exception as exc:
        write_run_log("Refresh failed", str(exc), "refresh")
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/run_all", response_model=RunAllResponse)
def api_run_all() -> RunAllResponse:
    refreshed = False
    try:
        run_refresh_pipeline(); refreshed = True
    except Exception as exc:
        write_run_log("Refresh failed; continuing to ingest", str(exc), "refresh")
    state = load_state(); req = IngestRequest(keyword=state.get("keyword") or DEMO_KEYWORD, company=state.get("company") or "", mode=state.get("mode") or "broad_and_targeted", sources=state.get("sources") or DEMO_TARGETS, max_results_per_query=int(state.get("max_results_per_query") or 6))
    ingest_result = api_ingest(req)
    return RunAllResponse(ok=True, refreshed=refreshed, added=ingest_result.added, total_results=ingest_result.total_results, mode_used=ingest_result.mode_used, message=f"Added {ingest_result.added} signals at {ingest_result.state.get('last_updated')}", state=ingest_result.state)

def default_state() -> Dict[str, Any]:
    return {"keyword": "", "company": "", "mode": "broad_and_targeted", "sources": [], "max_results_per_query": 6, "last_action": "Ready", "last_error": "", "last_updated": "", "last_mode_used": ""}

def load_state() -> Dict[str, Any]:
    state = default_state(); state.update(load_json(STATE_PATH, {}));
    if not isinstance(state.get("sources"), list): state["sources"] = []
    return state

def save_state(state: Dict[str, Any]) -> None:
    save_json_atomic(STATE_PATH, state)

def normalize_state_from_request(req: IngestRequest) -> Dict[str, Any]:
    return {"keyword": (req.keyword or "").strip(), "company": (req.company or "").strip(), "mode": (req.mode or "broad_and_targeted").strip() or "broad_and_targeted", "sources": [s.strip() for s in (req.sources or []) if isinstance(s, str) and s.strip()], "max_results_per_query": max(1, min(int(req.max_results_per_query or 6), 10)), "last_action": "Ready", "last_error": "", "last_updated": "", "last_mode_used": ""}

def load_signal_payload() -> Dict[str, Any]:
    payload = load_json(CACHE_PATH, {})
    if isinstance(payload, list): payload = {"items": payload, "generated_at_utc": utc_now(), "active_filters": {}}
    items = payload.get("items")
    if items is None:
        items = payload.get("events") or []; payload["items"] = items
    if not isinstance(items, list): payload["items"] = []
    payload["items"] = [clean_signal(item) for item in payload.get("items") or [] if isinstance(item, dict)]
    payload.setdefault("active_filters", {}); payload.setdefault("generated_at_utc", utc_now())
    return payload

def merge_signals(new_signals: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], int]:
    payload = load_signal_payload(); items = payload.get("items") or []; seen_urls = {(item.get("url") or "").strip() for item in items if isinstance(item, dict)}; added = 0
    for signal in new_signals:
        signal = clean_signal(signal)
        url = (signal.get("url") or "").strip()
        if not url or url in seen_urls: continue
        items.insert(0, signal); seen_urls.add(url); added += 1
    payload["items"] = items; payload.setdefault("active_filters", {})["last_web_ingest_added"] = added; payload["active_filters"]["last_web_ingest_at"] = utc_now(); payload["generated_at_utc"] = utc_now()
    return payload, added

def write_run_log(last_action: str, last_error: str, last_mode_used: str) -> None:
    save_json_atomic(RUN_LOG_PATH, {"last_action": last_action, "last_error": last_error, "last_mode_used": last_mode_used, "last_updated": utc_now()})

def read_google_cfg() -> Dict[str, str]:
    cfg = load_json(GOOGLE_CFG_PATH, {}); env_key = (os.getenv("GOOGLE_PSE_KEY") or "").strip(); env_cx = (os.getenv("GOOGLE_PSE_CX") or "").strip(); key = env_key or (cfg.get("api_key") or "").strip(); cx = env_cx or (cfg.get("cx") or "").strip()
    if key: os.environ["GOOGLE_PSE_KEY"] = key
    if cx: os.environ["GOOGLE_PSE_CX"] = cx
    return {"api_key": key, "cx": cx}

def filtered_targets(selected_names: List[str]) -> List[Dict[str, Any]]:
    targets = load_json(TARGETS_PATH, {"targets": []}).get("targets") or []
    if not selected_names: return targets
    wanted = {name.strip().lower() for name in selected_names if name.strip()}
    return [t for t in targets if (t.get("name") or "").strip().lower() in wanted]

def map_demo_result(item: Dict[str, Any], source_label: str) -> Dict[str, Any]:
    mapped = map_result_to_signal(item, forced_source=source_label); mapped["lane"] = "rss_demo"; mapped["priority_score"] = 0.55; mapped["observation"] = clean_text(item.get("snippet") or mapped.get("observation") or ""); mapped["why_it_matters"] = "RSS or built-in demo source item."; mapped["recommendation"] = "Open the link and review whether it matters for the leader."; mapped["recommended_action"] = mapped["recommendation"]; mapped.setdefault("facets", {}); mapped["facets"].setdefault("accounts", []); mapped["time"] = utc_now(); return clean_signal(mapped)

def built_in_demo_results(limit: int = 12, keyword: str = "") -> List[Dict[str, Any]]:
    focus = clean_text(keyword).lower()
    base = STATIC_DEMO_SIGNALS
    if any(term in focus for term in ["glp", "fill", "cdmo", "manufacturing", "gmp", "validation", "injectable", "capacity"]):
        base = [
            {"title": "GLP-1 sterile fill-finish capacity expansion creates validation and CDMO readiness watch", "url": "https://www.pharmamanufacturing.com/", "snippet": "Public/sample manufacturing signal: injectable capacity, fill-finish pressure, validation planning, commissioning support, and CDMO readiness.", "source": "Pharma Manufacturing"},
            {"title": "CDMO outsourcing activity signals tech-transfer and supplier governance pressure", "url": "https://www.biopharmadive.com/", "snippet": "Public/sample partner signal: sponsors may need CDMO support, supplier governance, tech-transfer readiness, and validation coordination.", "source": "BioPharma Dive"},
            {"title": "FDA/GMP inspection pressure raises quality remediation and launch-readiness questions", "url": "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters", "snippet": "Public/sample regulatory signal: GMP compliance, inspection readiness, validation burden, quality remediation, and source verification.", "source": "FDA Warning Letters / Inspections"},
            {"title": "Cold-chain and injectable distribution constraints can affect GLP-1 patient access", "url": "https://www.fiercepharma.com/", "snippet": "Public/sample supply signal: cold-chain readiness, injectable distribution, launch timing, supply resilience, and partner capacity.", "source": "Fierce Pharma"},
            {"title": "Automation and BMS commissioning needs rise with regulated facility expansion", "url": "https://ispe.org/publications/guidance-documents", "snippet": "Public/sample facility signal: automation, BMS, commissioning, qualification, CSV, and regulated manufacturing controls.", "source": "ISPE"},
            {"title": "Life-sciences capital project signals supplier readiness and manufacturing expansion risk", "url": "https://www.pharmamanufacturing.com/", "snippet": "Public/sample operations signal: facility expansion, supplier readiness, project execution, manufacturing capacity, and operational follow-up.", "source": "Pharma Manufacturing"},
        ] + STATIC_DEMO_SIGNALS
    results = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for idx, raw in enumerate(base[:limit], start=1):
        joiner = "&" if "?" in raw["url"] else "?"
        demo_url = f"{raw['url']}{joiner}demo_ingest={stamp}_{idx}"
        results.append({"url": demo_url, "name": f"{raw['title']} ({stamp}-{idx})", "snippet": raw["snippet"], "displayLink": raw["source"], "_forced_source": raw["source"]})
    return results


def perform_ingest(state: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    keyword = (state.get("keyword") or "").strip(); company = (state.get("company") or "").strip(); max_results = int(state.get("max_results_per_query") or 6); targets = filtered_targets(state.get("sources") or []); queries = build_queries(keyword, company, targets, include_general=(state.get("mode") != "targeted_only")); results: List[Dict[str, Any]] = []; cfg = read_google_cfg()
    if cfg.get("api_key") and cfg.get("cx") and queries:
        try:
            for query, forced_source in queries[:8]:
                raw = google_pse_search(query=query, num=max_results, explicit_cfg=cfg)
                for item in raw: results.append(map_result_to_signal(item, forced_source=forced_source))
            if results:
                return results, "google"
        except Exception as exc:
            write_run_log("Google failed, falling back to demo-safe mode", str(exc), "demo_safe_fallback")
    demo_safe_mode = os.getenv("DEMO_SAFE_MODE", "true").lower() not in {"0", "false", "no"}
    live_rss_enabled = os.getenv("ENABLE_LIVE_RSS", "false").lower() in {"1", "true", "yes"}
    if demo_safe_mode and not live_rss_enabled:
        return [map_demo_result(raw, raw.get("_forced_source") or raw.get("displayLink") or "Demo Source") for raw in built_in_demo_results(limit=12, keyword=keyword)], "demo_safe"
    rss_results: List[Dict[str, Any]] = []
    if queries:
        for query, forced_source in queries[:8]:
            try:
                raw = rss_search(query=query, forced_source=forced_source, num=max_results)
            except Exception:
                raw = []
            for item in raw:
                rss_results.append(map_demo_result(item, forced_source or item.get("_forced_source") or item.get("displayLink") or "RSS"))
    deduped: List[Dict[str, Any]] = []
    seen_urls = set()
    for item in rss_results:
        url = (item.get("url") or "").strip()
        if url and url not in seen_urls:
            deduped.append(item)
            seen_urls.add(url)
    if len(deduped) < 10:
        for item in [map_demo_result(raw, raw.get("_forced_source") or raw.get("displayLink") or "RSS") for raw in built_in_demo_results(limit=12, keyword=keyword)]:
            url = (item.get("url") or "").strip()
            if url and url not in seen_urls:
                deduped.append(item)
                seen_urls.add(url)
            if len(deduped) >= 12:
                break
    return deduped[:12], "rss"

def run_refresh_pipeline() -> None:
    python_exe = sys.executable; cmd1 = [python_exe, "-m", "src.main", "--lookback-hours", "24"]; cmd2 = [python_exe, str(ROOT / "tools" / "build_cache.py")]
    run1 = subprocess.run(cmd1, cwd=str(ROOT), capture_output=True, text=True)
    if run1.returncode != 0: raise RuntimeError("Refresh step 1 failed:\n" + (run1.stdout[-1200:] + "\n" + run1.stderr[-1200:]))
    run2 = subprocess.run(cmd2, cwd=str(ROOT), capture_output=True, text=True)
    if run2.returncode != 0: raise RuntimeError("Refresh step 2 failed:\n" + (run2.stdout[-1200:] + "\n" + run2.stderr[-1200:]))


# PASS 17D - Company-Aware API START
@app.get("/api/strategy_audit17d")
def api_strategy_audit17d(request: Request) -> Dict[str, Any]:
    payload = load_signal_payload()
    state = load_state()
    qp = request.query_params
    keyword = (qp.get("query") or qp.get("keyword") or qp.get("q") or "").strip()
    company = (qp.get("company") or qp.get("company_focus") or qp.get("account") or "").strip()
    mode = (qp.get("mode") or qp.get("coverage") or "").strip()
    source = (qp.get("source") or qp.get("target") or qp.get("source_filter") or "").strip()
    if keyword:
        state["keyword"] = keyword
    if company:
        state["company"] = company
    elif any(k in qp for k in ["company", "company_focus", "account"]):
        state["company"] = ""
    if mode:
        state["mode"] = mode
    if source and source.lower() not in {"all available sources", "[all available sources]", "all", "any"}:
        state["sources"] = [source]
    elif any(k in qp for k in ["source", "target", "source_filter"]):
        state["sources"] = []
    items = filtered_signal_items(state, payload)
    targets = load_json(TARGETS_PATH, {"targets": []}).get("targets") or []
    cfg = read_google_cfg()
    return strategy_audit(items, state, source_targets=targets, google_configured=bool(cfg.get("api_key") and cfg.get("cx")))
# PASS 17D - Company-Aware API END

@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    traceback.print_exc(); return JSONResponse(status_code=500, content={"ok": False, "detail": str(exc)})

# PASS 14 - Source Truth API START
SOURCE_TRUTH_PATH = ROOT / "outputs" / "source_truth_audit.json"

SOURCE_TRUTH_FALLBACK = {
    "ok": True,
    "mode": "fallback_source_truth",
    "project": "Scout Horizon",
    "positioning": "demo-safe public/current-source-oriented decision-support prototype",
    "summary": "Scout Horizon organizes public, configurable, and demo-safe life-sciences signals into executive briefs, confidence cues, source posture notes, and next-action review.",
    "what_is_real_current_source_oriented": [
        "The dashboard and API are live on Render.",
        "The app can read bundled/cache signal data and configured public-source registries.",
        "The workflow supports public/current-source-oriented review using RSS/API/manual-source style inputs when configured.",
        "The Scout Brief, scoring, filtering, evidence posture, and next-action language are generated from the app workflow."
    ],
    "what_is_demo_safe_or_sample_based": [
        "Some bundled signals and showcase examples are demo-safe/sample or curated fallback data.",
        "The GLP-1 Manufacturing Pressure Radar should be presented as a demonstration workflow, not a private market-intelligence feed.",
        "Manual CSV/cache inputs should be described as curated inputs unless freshly regenerated and verified."
    ],
    "claims_to_avoid": [
        "Do not claim enterprise-ready.",
        "Do not claim compliance-certified.",
        "Do not claim GxP-validated.",
        "Do not claim fully real-time.",
        "Do not claim connection to private customer systems.",
        "Do not imply endorsement by any named person or company unless separately approved."
    ],
    "safe_language": [
        "public-signal workflow",
        "current-source-oriented",
        "demo-safe",
        "refresh-ready",
        "decision-support prototype",
        "validated facility readiness lens"
    ],
    "recommended_review": "Use this endpoint as a public honesty layer. For production use, generate and review a fresh source truth audit before sharing claims externally."
}

@app.get("/api/source_truth")
def api_source_truth():
    if SOURCE_TRUTH_PATH.exists():
        try:
            return JSONResponse(json.loads(SOURCE_TRUTH_PATH.read_text(encoding="utf-8")))
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    return JSONResponse(SOURCE_TRUTH_FALLBACK)
# PASS 14 - Source Truth API END

# PASS 17 - Strategic Brain Audit API START
@app.get("/api/strategy_audit")
def api_strategy_audit() -> Dict[str, Any]:
    payload = load_signal_payload()
    state = load_state()
    items = filtered_signal_items(state, payload)
    targets = load_json(TARGETS_PATH, {"targets": []}).get("targets") or []
    cfg = read_google_cfg()
    return strategy_audit(items, state, source_targets=targets, google_configured=bool(cfg.get("api_key") and cfg.get("cx")))
# PASS 17 - Strategic Brain Audit API END

# PASS 17E - Source Conflict Truthfulness START
try:
    import json as _pass17e_json
    from starlette.middleware.base import BaseHTTPMiddleware as _Pass17EBaseHTTPMiddleware
    from starlette.responses import Response as _Pass17EResponse

    _PASS17E_CYBER_TERMS = ("cyber", " ot ", "ics", "cisa", "cve", "kev", "ransomware", "vulnerability", "exploit")
    _PASS17E_CYBER_SOURCES = ("cisa", "nvd", "cyber", "kev", "cve", "ics", " ot ", "security")

    def _pass17e_text(value):
        if value is None:
            return ""
        if isinstance(value, (list, dict)):
            try:
                return _pass17e_json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        return str(value)

    def _pass17e_has_any(text, terms):
        text = " " + (text or "").lower() + " "
        return any(term in text for term in terms)

    def _pass17e_get_signals(payload):
        if isinstance(payload, list):
            return payload, None
        if isinstance(payload, dict):
            for key in ("signals", "items", "data", "results"):
                if isinstance(payload.get(key), list):
                    return payload[key], key
        return None, None

    def _pass17e_params(request):
        q = request.query_params.get("query") or request.query_params.get("keyword") or request.query_params.get("q") or ""
        company = request.query_params.get("company") or request.query_params.get("company_focus") or request.query_params.get("account") or ""
        source = request.query_params.get("source") or request.query_params.get("target") or request.query_params.get("source_filter") or ""
        mode = request.query_params.get("mode") or request.query_params.get("coverage") or ""
        return q.strip(), company.strip(), source.strip(), mode.strip()

    def _pass17e_is_cyber_query(query):
        return _pass17e_has_any(query, _PASS17E_CYBER_TERMS)

    def _pass17e_is_cyber_source(source):
        return _pass17e_has_any(source, _PASS17E_CYBER_SOURCES)

    def _pass17e_annotate(payload, request):
        query, company, source, mode = _pass17e_params(request)
        signals, key = _pass17e_get_signals(payload)
        if not isinstance(signals, list):
            return payload

        source_selected = bool(source and source.lower() not in {"all available sources", "[all available sources]"})
        conflict = bool(_pass17e_is_cyber_query(query) and source_selected and not _pass17e_is_cyber_source(source))

        out = []
        for signal in signals:
            if not isinstance(signal, dict):
                out.append(signal)
                continue
            item = dict(signal)
            warnings = item.get("strategic_warnings", [])
            if isinstance(warnings, str):
                warnings = [warnings] if warnings.strip() else []
            if not isinstance(warnings, list):
                warnings = []

            item["requested_query"] = query
            item["requested_company"] = company
            item["requested_source"] = source or "all available sources"
            item["requested_mode"] = mode

            if conflict:
                item["source_query_conflict"] = True
                item["source_filter_adjacent_only"] = True
                item["truth_label"] = (
                    "No direct cyber/OT signal is expected inside selected source '"
                    + source
                    + "'. Showing source-limited adjacent intelligence."
                )
                for warn in (
                    "source-query conflict: cyber/OT query with non-cyber source filter",
                    "adjacent source-limited result, not direct cyber/OT evidence",
                ):
                    if warn not in warnings:
                        warnings.append(warn)
                item["direct_query_match"] = False
            else:
                item["source_query_conflict"] = False
                item["source_filter_adjacent_only"] = False

            item["strategic_warnings"] = warnings
            out.append(item)

        if isinstance(payload, list):
            return out
        payload = dict(payload)
        payload[key] = out
        payload["strategy_engine"] = "pass17e_source_conflict_truthfulness"
        payload["source_conflict_count"] = sum(1 for s in out if isinstance(s, dict) and s.get("source_query_conflict"))
        payload["truthfulness_note"] = "Source-limited adjacent results are allowed when clearly labeled."
        return payload

    class _Pass17ESourceConflictMiddleware(_Pass17EBaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            if request.url.path.rstrip("/") != "/api/signals" or response.status_code != 200:
                return response
            if "application/json" not in response.headers.get("content-type", ""):
                return response
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            try:
                payload = _pass17e_json.loads(body.decode("utf-8"))
                payload = _pass17e_annotate(payload, request)
                return _Pass17EResponse(
                    content=_pass17e_json.dumps(payload, ensure_ascii=False),
                    status_code=response.status_code,
                    media_type="application/json",
                    headers={k: v for k, v in response.headers.items() if k.lower() not in {"content-length", "content-type"}},
                )
            except Exception:
                return _Pass17EResponse(
                    content=body,
                    status_code=response.status_code,
                    media_type="application/json",
                    headers={k: v for k, v in response.headers.items() if k.lower() not in {"content-length", "content-type"}},
                )

    if not getattr(app.state, "pass17e_source_conflict_middleware_installed", False):
        app.add_middleware(_Pass17ESourceConflictMiddleware)
        app.state.pass17e_source_conflict_middleware_installed = True

    @app.get("/api/strategy_audit17e")
    def pass17e_strategy_audit(query: str = "cyber OT life sciences risk", company: str = "", source: str = "Fierce Pharma", mode: str = "broad_targeted"):
        conflict = bool(_pass17e_is_cyber_query(query) and source and not _pass17e_is_cyber_source(source))
        return {
            "ok": True,
            "strategy_engine": "pass17e_source_conflict_truthfulness",
            "query": query,
            "company": company,
            "source": source,
            "mode": mode,
            "source_query_conflict": conflict,
            "truth_label": (
                "No direct cyber/OT signal is expected inside selected source '" + source + "'. Showing source-limited adjacent intelligence."
                if conflict else
                "No source/query conflict detected."
            ),
        }

except Exception as _pass17e_exc:
    try:
        print("Pass 17E source-conflict truthfulness skipped:", _pass17e_exc)
    except Exception:
        pass
# PASS 17E - Source Conflict Truthfulness END

# === PASS17I_SOURCE_LIMITED_MODE_SEMANTICS_START ===
# Adds honest, mode-specific semantics to source-limited API results.
# This is intentionally narrow: it does not invent evidence or change source facts.
# It labels how broad, targeted, and broad_targeted scans should be interpreted,
# especially when a hard source filter prevents a direct topic match.
try:
    from starlette.responses import Response as _Pass17IResponse
except Exception:  # pragma: no cover
    _Pass17IResponse = None

_PASS17I_MODE_LABELS = {
    "broad": "scan mode: broad market-context weighting",
    "targeted": "scan mode: targeted exact-evidence weighting",
    "broad_targeted": "scan mode: balanced broad-plus-targeted weighting",
    "balanced": "scan mode: balanced broad-plus-targeted weighting",
}
_PASS17I_CYBER_TERMS = ("cyber", "ot", "ics", "cisa", "cve", "kev", "vulnerability", "ransomware", "security")
_PASS17I_CYBER_SOURCES = ("cisa", "nvd", "cyber", "security", "cve", "kev", "ics", "ot")

def _pass17i_text(value):
    try:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            import json as _json
            return _json.dumps(value, ensure_ascii=False)
        return str(value)
    except Exception:
        return ""

def _pass17i_blob(item):
    if isinstance(item, dict):
        return " ".join(_pass17i_text(v) for v in item.values()).lower()
    return _pass17i_text(item).lower()

def _pass17i_apply(payload, mode, query, source):
    mode_key = (mode or "broad_targeted").strip().lower()
    mode_label = _PASS17I_MODE_LABELS.get(mode_key, f"scan mode: {mode_key or 'balanced'} weighting")
    q = (query or "").lower()
    s = (source or "").lower()
    source_limited_cyber = (
        any(term in q for term in _PASS17I_CYBER_TERMS)
        and bool(s)
        and not any(term in s for term in _PASS17I_CYBER_SOURCES)
    )

    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = None
        for key in ("signals", "items", "data", "results"):
            if isinstance(payload.get(key), list):
                items = payload[key]
                break
        if items is None:
            items = []
    else:
        items = []

    for item in items:
        if not isinstance(item, dict):
            continue
        current = _pass17i_text(item.get("truth_label")).strip()
        if mode_label not in current:
            item["truth_label"] = (current + " | " + mode_label).strip(" |")
        item["scan_mode"] = mode_key or "broad_targeted"
        item["scan_mode_evidence"] = mode_label

        if source_limited_cyber:
            item["source_query_conflict"] = True
            item["source_filter_adjacent_only"] = True
            warning = _pass17i_text(item.get("strategic_warnings")).strip()
            add = f"Source-limited adjacent result: '{source}' is not a cyber/OT source, so this scan preserves source truth while labeling the result as adjacent under {mode_key or 'balanced'} mode."
            if add not in warning:
                item["strategic_warnings"] = (warning + " | " + add).strip(" |")
    return payload

try:
    @app.middleware("http")
    async def _pass17i_source_limited_mode_semantics(request, call_next):
        response = await call_next(request)
        try:
            path = str(request.url.path)
            if path != "/api/signals" or getattr(response, "status_code", None) != 200:
                return response
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return response

            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            import json as _json
            payload = _json.loads(body.decode("utf-8", errors="replace"))
            params = request.query_params
            mode = params.get("mode") or params.get("coverage") or "broad_targeted"
            query = params.get("query") or params.get("keyword") or params.get("q") or ""
            source = params.get("source") or params.get("target") or params.get("source_filter") or ""
            payload = _pass17i_apply(payload, mode, query, source)
            new_body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers = dict(response.headers)
            headers.pop("content-length", None)
            return _Pass17IResponse(content=new_body, status_code=response.status_code, headers=headers, media_type="application/json")
        except Exception:
            return response
except Exception:
    pass
# === PASS17I_SOURCE_LIMITED_MODE_SEMANTICS_END ===
