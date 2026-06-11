"""Headless Web Assist runner.

Used by DAILY_REFRESH.bat (Windows Scheduled Task) to run Google PSE searches
using the last saved Web Assist state, then merge results into cache/radar_signals.json.

Stability goals:
- Never crash the whole refresh if Web Assist is not configured.
- Respect max results and dedupe by URL (handled in merge_into_cache).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from src.search_engine import (
    google_pse_search,
    build_queries,
    map_result_to_signal,
    merge_into_cache,
    SearchConfigError,
)

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "cache" / "radar_signals.json"
TARGETS_PATH = ROOT / "config" / "source_targets.json"
STATE_PATH = ROOT / "config" / "webassist_state.json"
CFG_PATH = ROOT / "config" / "webassist_google_pse.json"

def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def _mirror_cfg_to_env() -> None:
    cfg = _load_json(CFG_PATH, {})
    api_key = (cfg or {}).get("api_key") or ""
    cx = (cfg or {}).get("cx") or ""
    if api_key and cx:
        os.environ["GOOGLE_PSE_KEY"] = api_key
        os.environ["GOOGLE_PSE_CX"] = cx

def main() -> int:
    _mirror_cfg_to_env()

    state: Dict[str, Any] = _load_json(STATE_PATH, {})
    keyword = (state.get("keyword") or "").strip()
    company = (state.get("company") or "").strip()
    mode = (state.get("mode") or "broad_and_targeted").strip()
    max_results_per_query = int(state.get("max_results_per_query") or 6)
    sources = state.get("sources") or None

    if not keyword and not company:
        print("[WEBASSIST] No saved keyword/company. Skipping Web Assist.")
        return 0

    targets_doc = _load_json(TARGETS_PATH, {"targets": []})
    targets: List[Dict[str, Any]] = (targets_doc or {}).get("targets") or []
    if sources:
        want = set([str(s).strip() for s in sources if str(s).strip()])
        targets = [t for t in targets if t.get("name") in want]

    queries = build_queries(keyword, company, targets, include_general=(mode != "targeted_only"))
    if not queries:
        print("[WEBASSIST] No queries built. Skipping.")
        return 0

    all_mapped: List[Dict[str, Any]] = []
    total = 0
    try:
        for q, forced_source in queries:
            raw = google_pse_search(q, num=max_results_per_query)
            total += len(raw)
            for r in raw:
                all_mapped.append(map_result_to_signal(r, forced_source=forced_source))
    except SearchConfigError as e:
        print(f"[WEBASSIST] Not configured: {e}")
        return 0
    except Exception as e:
        print(f"[WEBASSIST] Search failed: {e}")
        return 0

    payload = merge_into_cache(str(CACHE_PATH), all_mapped)
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    added = int(payload.get("active_filters", {}).get("last_web_ingest_added", 0) or 0)
    print(f"[WEBASSIST] Completed. Added {added} items (raw results {total}).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
