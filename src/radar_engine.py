from __future__ import annotations
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from .adapters import cisa_kev, clinicaltrials, email_alerts_imap, gdelt, nvd, sam_gov, sec_edgar, rss_feed, manual_signals
from .cache import cache_get, cache_set
from .dedupe import fingerprint
from .filters import parse_term_list, passes_include_exclude
from .normalization import lane_from_tags, map_region, normalize_published, tag_service_line
from .partnerships import detect_partnership, extract_partnership_fields
from .scoring import apply_question_mode, compute_confidence, freshness_boost
from .utils.logging import log_event


DEFAULT_SETTINGS = {
    "clinical_trials": {
        "enabled": True,
        "max_items_per_run": 250,
        "max_pages_per_query": 1,
        "max_queries_per_run": 8,
        "sponsor_only_queries": True,
        "exclude_healthy_participants": True,
        "exclude_by_keywords": False,
        "exclude_keywords": ["healthy participants", "phase 1", "bioequivalence", "pharmacokinetics"],
    },
    "filters": {"include_text": "", "exclude_text": ""},
    "sources": {"free": {}, "premium": {}},
    "discovery": {
        "enabled": True,
        "max_queries_per_run": 28,
        "account_query_limit": 8,
        "region_query_limit": 6,
        "topic_query_limit": 16,
        "capex_queries": [],
        "hiring_queries": [],
        "partnership_queries": [],
        "competitor_queries": [],
    },
    "partnership_detection": {
        "enabled": True,
        "keywords": ["partnership", "collaboration", "deal", "agreement", "alliance"],
        "modalities": [],
        "stages": [],
    },
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def deep_merge(base: dict, incoming: dict) -> dict:
    merged = dict(base)
    for k, v in (incoming or {}).items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def load_settings(cfg_dir: Path) -> dict:
    settings_path = cfg_dir / 'radar_settings.json'
    settings = DEFAULT_SETTINGS
    if settings_path.exists():
        settings = deep_merge(DEFAULT_SETTINGS, load_json(settings_path))
    return settings


def utc_window(hours: int):
    end = datetime.utcnow()
    start = end - timedelta(hours=hours)
    return start, end


def fmt_gdelt(dt: datetime) -> str:
    return dt.strftime('%Y%m%d%H%M%S')


def source_enabled(settings: dict, fid: str) -> bool:
    return bool((settings.get('sources', {}).get('free', {}) or {}).get(fid, True))


def build_account_map(accounts_cfg: dict) -> tuple[dict, dict, list[str]]:
    acct_types: dict[str, str] = {}
    for a in accounts_cfg.get('clients', []):
        acct_types[a] = 'client'
    for a in accounts_cfg.get('competitors', []):
        acct_types[a] = 'competitor'
    for a in accounts_cfg.get('watchlist', []):
        acct_types[a] = 'watch'
    aliases = accounts_cfg.get('aliases', {}) or {}
    known_accounts = list(acct_types.keys())
    return acct_types, aliases, known_accounts


def event_text(ev: dict) -> str:
    return ' '.join([
        ev.get('title', ''),
        ev.get('summary', ''),
        ev.get('link', ''),
        json.dumps(ev.get('raw', {}), ensure_ascii=False),
    ])


def filter_clinical_item(ev: dict, settings: dict, include_terms: list[str], exclude_terms: list[str]) -> bool:
    cfg = settings.get('clinical_trials', {}) or {}
    txt = event_text(ev)
    raw = (ev.get('raw', {}) or {}).get('clinicaltrials', {}) or {}
    if cfg.get('exclude_healthy_participants') and raw.get('healthyVolunteers'):
        return False
    if cfg.get('exclude_by_keywords') and cfg.get('exclude_keywords'):
        if any(k.lower() in txt.lower() for k in cfg.get('exclude_keywords', [])):
            return False
    return passes_include_exclude(txt, include_terms, exclude_terms)


def build_gdelt_queries(acct_types: dict, topics: dict, settings: dict) -> list[str]:
    discovery = settings.get('discovery', {}) or {}
    if not discovery.get('enabled', True):
        return []

    director_topics = topics.get('director_topics', []) or []
    accts = list(acct_types.keys())[: int(discovery.get('account_query_limit', 8))]
    queries: list[str] = []

    capex = discovery.get('capex_queries', []) or []
    hiring = discovery.get('hiring_queries', []) or []
    partnerships = discovery.get('partnership_queries', []) or []
    competitor = discovery.get('competitor_queries', []) or []

    for acct in accts:
        acct_q = f'"{acct}"'
        for q in capex[:1] + hiring[:1] + partnerships[:1] + competitor[:1]:
            queries.append(f'{acct_q} ({q})')

    for topic in (director_topics[: int(discovery.get('topic_query_limit', 16))] or []):
        q = topic.get('query', '')
        if q:
            queries.append(q)

    queries.extend(capex)
    queries.extend(hiring)
    queries.extend(partnerships)
    queries.extend(competitor)

    max_queries = int(discovery.get('max_queries_per_run', 28))
    deduped = []
    seen = set()
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped[:max_queries]


def infer_account(txt: str, acct_types: dict, aliases: dict) -> str:
    low = txt.lower()
    for a in acct_types.keys():
        cand = [a] + (aliases.get(a, []) or [])
        if any(c and c.lower() in low for c in cand):
            return a
    return ''


def run_engine(project_dir: Path, mode: str | None = None, lookback_hours: int = 24, include_text: str = '', exclude_text: str = ''):
    cfg_dir = project_dir / 'config'
    out_dir = project_dir / 'outputs'
    cache_dir = project_dir / '.cache'
    log_path = out_dir / 'run_log.json'
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    accounts = load_yaml(cfg_dir / 'accounts.yaml')
    regions = load_yaml(cfg_dir / 'regions.yaml')
    topics = load_yaml(cfg_dir / 'topics.yaml')
    mode_weights = load_yaml(cfg_dir / 'question_modes.yaml')
    feeds_free = load_json(cfg_dir / 'feeds_registry_free_max.json')
    # Optional add-ons: public RSS feeds + manual (copy/paste) signals
    feeds_rss = []
    if (cfg_dir / 'feeds_registry_rss_public.json').exists():
        feeds_rss = load_json(cfg_dir / 'feeds_registry_rss_public.json')
    feeds_manual = []
    if (cfg_dir / 'feeds_registry_manual.json').exists():
        feeds_manual = load_json(cfg_dir / 'feeds_registry_manual.json')
    feeds_all = (feeds_free or []) + (feeds_rss or []) + (feeds_manual or [])

    settings = load_settings(cfg_dir)

    include_terms = parse_term_list(include_text or settings.get('filters', {}).get('include_text', ''))
    exclude_terms = parse_term_list(exclude_text or settings.get('filters', {}).get('exclude_text', ''))

    acct_types, aliases, known_accounts = build_account_map(accounts)
    director_topics = topics.get('director_topics', []) or []
    start_dt, end_dt = utc_window(lookback_hours)
    start_utc, end_utc = fmt_gdelt(start_dt), fmt_gdelt(end_dt)

    all_events = []
    feed_health = []
    clinical_kept = 0

    for feed in feeds_all:
        fid = feed['id']
        if not source_enabled(settings, fid):
            feed_health.append({"feed_id": fid, "label": feed.get("label", ""), "yield": 0, "seconds": 0, "error": "disabled_by_settings"})
            continue

        t0 = time.time()
        yield_count = 0
        err = None
        try:
            # Generic RSS feeds (public, ToS-safe)
            if (feed.get("type") or "") == "rss":
                items = rss_feed.fetch(feed, start_dt, end_dt)
                for ev in items:
                    ev["feed_id"] = fid
                    ev["_source_reliability"] = feed.get("reliability", 0.6)
                all_events.extend(items)
                yield_count += len(items)
            # Dynamic RSS list (e.g., Google Alerts RSS URLs you paste into config/google_alerts_rss_urls.txt)
            elif (feed.get("type") or "") == "rss_dynamic":
                cfg_list = (feed.get("config_list_path") or "").strip()
                urls = []
                if cfg_list:
                    p = project_dir / cfg_list
                    if p.exists():
                        for line in p.read_text(encoding="utf-8").splitlines():
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            urls.append(line)
                for u in urls:
                    f2 = dict(feed)
                    f2["url_or_endpoint"] = u
                    items = rss_feed.fetch(f2, start_dt, end_dt)
                    for ev in items:
                        ev["feed_id"] = fid
                        ev["_source_reliability"] = feed.get("reliability", 0.6)
                    all_events.extend(items)
                    yield_count += len(items)
            # Manual copy/paste signals (CSV) to mirror "manual research"
            elif (feed.get("type") or "") == "manual_csv":
                items = manual_signals.fetch(feed, project_dir)
                for ev in items:
                    ev["feed_id"] = fid
                    ev["_source_reliability"] = feed.get("reliability", 0.6)
                all_events.extend(items)
                yield_count += len(items)
            elif fid == 'gdelt_doc_v2_discovery':
                queries = build_gdelt_queries(acct_types, topics, settings)
                for q in queries:
                    cache_key = f'gdelt:{q}:{start_utc}:{end_utc}'
                    items = cache_get(cache_dir, cache_key, ttl_seconds=6 * 3600)
                    if items is None:
                        items = gdelt.fetch(feed, q, start_utc, end_utc)
                        cache_set(cache_dir, cache_key, items)
                    for it in items:
                        it['_feed_id'] = fid
                        it['_source_reliability'] = feed.get('reliability', 0.7)
                        it['_query'] = q
                        if not passes_include_exclude(event_text(it), include_terms, exclude_terms):
                            continue
                        all_events.append(it)
                        yield_count += 1

            elif fid == 'cisa_kev_catalog':
                cache_key = f"kev:{feed['url_or_endpoint']}"
                items = cache_get(cache_dir, cache_key, ttl_seconds=6 * 3600)
                if items is None:
                    items = cisa_kev.fetch(feed)
                    cache_set(cache_dir, cache_key, items)
                for it in items:
                    it['_feed_id'] = fid
                    it['_source_reliability'] = feed.get('reliability', 0.97)
                    if not passes_include_exclude(event_text(it), include_terms, exclude_terms):
                        continue
                    all_events.append(it)
                    yield_count += 1

            elif fid == 'nist_nvd_cve_api':
                cyber_queries = [
                    t.get('query', '') for t in director_topics
                    if 'CVE' in (t.get('query', '') or '') or 'ransomware' in (t.get('query', '') or '').lower() or 'OT' in (t.get('query', '') or '')
                ]
                cyber_queries = cyber_queries[:4] if cyber_queries else ['ICS OR OT OR SCADA']
                start_iso = start_dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
                end_iso = end_dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
                for q in cyber_queries:
                    offset = 0
                    for _ in range(2):
                        cache_key = f'nvd:{q}:{start_iso}:{end_iso}:{offset}'
                        cached = cache_get(cache_dir, cache_key, ttl_seconds=6 * 3600)
                        if cached is None:
                            items, total = nvd.fetch(feed, q, start_iso, end_iso, offset=offset)
                            cache_set(cache_dir, cache_key, {'items': items, 'total': total})
                        else:
                            items, total = cached['items'], cached['total']
                        for it in items:
                            it['_feed_id'] = fid
                            it['_source_reliability'] = feed.get('reliability', 0.9)
                            it['_query'] = q
                            if not passes_include_exclude(event_text(it), include_terms, exclude_terms):
                                continue
                            all_events.append(it)
                            yield_count += 1
                        offset += 200
                        if offset >= total:
                            break

            elif fid == 'clinicaltrials_v2_studies' and settings.get('clinical_trials', {}).get('enabled', True):
                ctcfg = settings.get('clinical_trials', {}) or {}
                queries = []
                sponsor_only = ctcfg.get('sponsor_only_queries', True)
                acct_candidates = list(acct_types.keys())[: int(ctcfg.get('max_queries_per_run', 8))]
                if sponsor_only:
                    queries.extend(acct_candidates)
                else:
                    queries.extend(acct_candidates)
                    queries.extend([t.get('query', '') for t in director_topics[:4]])
                for q in queries[: int(ctcfg.get('max_queries_per_run', 8))]:
                    page = None
                    for _ in range(int(ctcfg.get('max_pages_per_query', 1))):
                        items, page = clinicaltrials.fetch(feed, q, page_token=page, page_size=100)
                        for it in items:
                            if clinical_kept >= int(ctcfg.get('max_items_per_run', 250)):
                                break
                            if not filter_clinical_item(it, settings, include_terms, exclude_terms):
                                continue
                            it['_feed_id'] = fid
                            it['_source_reliability'] = feed.get('reliability', 0.93)
                            it['_query'] = q
                            all_events.append(it)
                            yield_count += 1
                            clinical_kept += 1
                        if clinical_kept >= int(ctcfg.get('max_items_per_run', 250)) or not page:
                            break
                    if clinical_kept >= int(ctcfg.get('max_items_per_run', 250)):
                        break

            elif fid == 'sec_company_tickers_exchange':
                ua = os.getenv('SEC_USER_AGENT', 'StrategicRadar/1.0 (contact: you@example.com)')
                cache_key = 'sec:company_tickers_exchange'
                cached = cache_get(cache_dir, cache_key, ttl_seconds=7 * 24 * 3600)
                if cached is None:
                    data = sec_edgar.fetch_company_tickers(feed['url_or_endpoint'], user_agent=ua)
                    cache_set(cache_dir, cache_key, data)
                    yield_count = 1
                else:
                    yield_count = 0

            elif fid == 'sec_submissions_by_cik':
                ua = os.getenv('SEC_USER_AGENT', 'StrategicRadar/1.0 (contact: you@example.com)')
                tickers = cache_get(cache_dir, 'sec:company_tickers_exchange', ttl_seconds=7 * 24 * 3600)
                if tickers is None:
                    data = sec_edgar.fetch_company_tickers('https://www.sec.gov/files/company_tickers_exchange.json', user_agent=ua)
                    cache_set(cache_dir, 'sec:company_tickers_exchange', data)
                    tickers = data
                target_accounts = [a for a in acct_types.keys() if a in ['Pfizer', 'Moderna', 'AstraZeneca', 'Sanofi', 'Siemens']]
                ciks = []
                for _, rec in (tickers or {}).items():
                    title = (rec.get('title') or '').lower()
                    for a in target_accounts:
                        if a.lower() in title:
                            cik = str(rec.get('cik', '')).zfill(10)
                            if cik and cik not in ciks:
                                ciks.append(cik)
                for cik10 in ciks[:6]:
                    cache_key = f"sec:submissions:{cik10}"
                    sub = cache_get(cache_dir, cache_key, ttl_seconds=24 * 3600)
                    if sub is None:
                        sub = sec_edgar.fetch_submissions(feed['url_or_endpoint'], cik10=cik10, user_agent=ua)
                        cache_set(cache_dir, cache_key, sub)
                    items = sec_edgar.filings_to_events(sub, cik10=cik10, forms_allow=['8-K', '10-K', '10-Q', 'S-4', '424B*'])
                    for it in items:
                        it['_feed_id'] = fid
                        it['_source_reliability'] = feed.get('reliability', 0.96)
                        it['_query'] = cik10
                        if not passes_include_exclude(event_text(it), include_terms, exclude_terms):
                            continue
                        all_events.append(it)
                        yield_count += 1

            elif fid == 'sam_gov_opportunities':
                qlist = ["GMP cleanroom", "OT cybersecurity", "commissioning qualification", "facility expansion"]
                start_date = (datetime.utcnow() - timedelta(days=7)).strftime('%m/%d/%Y')
                end_date = datetime.utcnow().strftime('%m/%d/%Y')
                for q in qlist:
                    items, total, err2 = sam_gov.fetch(feed, q, start_date, end_date, offset=0)
                    if err2:
                        err = err2
                        break
                    for it in items:
                        it['_feed_id'] = fid
                        it['_source_reliability'] = feed.get('reliability', 0.9)
                        it['_query'] = q
                        if not passes_include_exclude(event_text(it), include_terms, exclude_terms):
                            continue
                        all_events.append(it)
                        yield_count += 1

            elif fid == 'email_alerts_imap':
                items, _, err2 = email_alerts_imap.fetch(feed, since_uid=None)
                if err2:
                    err = err2
                for it in items:
                    it['_feed_id'] = fid
                    it['_source_reliability'] = feed.get('reliability', 0.55)
                    if not passes_include_exclude(event_text(it), include_terms, exclude_terms):
                        continue
                    all_events.append(it)
                    yield_count += 1

        except Exception as e:
            err = str(e)

        dt = time.time() - t0
        feed_health.append({"feed_id": fid, "label": feed.get("label", ""), "yield": yield_count, "seconds": round(dt, 2), "error": err})
        log_event(log_path, {"feed_id": fid, "yield": yield_count, "seconds": dt, "error": err})

    partnership_cfg = settings.get('partnership_detection', {}) or {}
    partnership_keywords = partnership_cfg.get('keywords', []) or []
    partnership_modalities = partnership_cfg.get('modalities', []) or []
    partnership_stages = partnership_cfg.get('stages', []) or []

    seen = set()
    normalized = []
    for ev in all_events:
        pub = normalize_published(ev.get("published", ""))
        txt = ' '.join([ev.get("title", ""), ev.get("summary", ""), ev.get("link", "")])
        region, region_conf = map_region(txt, regions)
        svc, topic_name, topic_conf = tag_service_line(txt, topics)
        lane = lane_from_tags(txt)
        acct_match = infer_account(txt, acct_types, aliases)

        partnership = {}
        if partnership_cfg.get('enabled', True) and detect_partnership(txt, partnership_keywords):
            partnership = extract_partnership_fields(
                ev.get('title', ''),
                ev.get('summary', ''),
                account=acct_match,
                known_accounts=known_accounts,
                modalities=partnership_modalities,
                stages=partnership_stages,
            )
            # If a partnership keyword was detected but the extractor couldn't confidently
            # pull structured fields, we still treat this as a partnership/deal signal so
            # the viewer filter works and the leader can review the candidate items.
            partnership['is_partnership'] = True
            lane = 'competitive_intel'

        ev2 = {
            "id": "",
            "title": ev.get("title", ""),
            "link": ev.get("link", ""),
            "published": pub,
            "summary": ev.get("summary", ""),
            "source": ev.get("source", ""),
            "lane": lane,
            "tags": list(set(feed_id_to_tags(ev.get('_feed_id')) + (["partnership"] if partnership.get('is_partnership') else []))),
            "account": acct_match,
            "account_type": acct_types.get(acct_match, ""),
            "region": region,
            "region_confidence": round(region_conf, 2),
            "service_line": svc,
            "topic": topic_name,
            "topic_confidence": round(topic_conf, 2),
            "evidence": ev.get("evidence", []) or [],
            "feed_id": ev.get("_feed_id", ""),
            "confidence": 0.0,
            "confidence_reasons": [],
            "score": 0.0,
            "partner_a": partnership.get('partner_a', ''),
            "partner_b": partnership.get('partner_b', ''),
            "deal_value": partnership.get('deal_value', ''),
            "modality": partnership.get('modality', ''),
            "deal_geography": partnership.get('geography', ''),
            "deal_stage": partnership.get('stage', ''),
            "is_partnership": bool(partnership.get('is_partnership')),
        }
        fp = fingerprint(ev2)
        if fp in seen:
            continue
        seen.add(fp)
        ev2["id"] = fp[:16]
        src_rel = float(ev.get("_source_reliability", 0.6) or 0.6)
        conf, reasons = compute_confidence(ev2, src_rel)
        ev2["confidence"] = round(conf, 3)
        ev2["confidence_reasons"] = reasons
        score = conf * freshness_boost(ev2["published"])
        if ev2["is_partnership"]:
            score *= 1.12
        if ev2.get('feed_id') == 'clinicaltrials_v2_studies':
            score *= 0.78
        score = apply_question_mode(score, lane, mode_weights, mode)
        ev2["score"] = round(float(score), 3)
        normalized.append(ev2)

    normalized.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    summary = {
        "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds"),
        "mode": mode or "",
        "lookback_hours": lookback_hours,
        "total_events": len(normalized),
        "counts_by_lane": {},
        "counts_by_region": {},
        "counts_by_account_type": {},
        "top_events": normalized[:50],
        "feed_health": feed_health,
        "active_filters": {
            "include_text": include_terms,
            "exclude_text": exclude_terms,
        },
        "settings_snapshot": {
            "clinical_trials": settings.get('clinical_trials', {}),
            "sources": settings.get('sources', {}),
        },
    }
    for e in normalized:
        summary["counts_by_lane"][e["lane"]] = summary["counts_by_lane"].get(e["lane"], 0) + 1
        if e["region"]:
            summary["counts_by_region"][e["region"]] = summary["counts_by_region"].get(e["region"], 0) + 1
        if e["account_type"]:
            summary["counts_by_account_type"][e["account_type"]] = summary["counts_by_account_type"].get(e["account_type"], 0) + 1

    (out_dir / 'radar_signals.json').write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding='utf-8')
    (out_dir / 'radar_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary



def feed_id_to_tags(feed_id: str):
    if not feed_id:
        return []
    mapping = {
        "gdelt_doc_v2_discovery": ["discovery"],
        "sec_submissions_by_cik": ["sec", "edgar"],
        "clinicaltrials_v2_studies": ["clinicaltrials"],
        "cisa_kev_catalog": ["cisa", "kev"],
        "nist_nvd_cve_api": ["nvd", "cve"],
        "sam_gov_opportunities": ["sam_gov"],
        "email_alerts_imap": ["email_alerts"],
    }
    return mapping.get(feed_id, [feed_id])
