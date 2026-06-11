import json, time, hashlib, os
from pathlib import Path

def _key_to_path(cache_dir: Path, key: str) -> Path:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return cache_dir / f"{h}.json"

def cache_get(cache_dir: Path, key: str, ttl_seconds: int | None):
    p = _key_to_path(cache_dir, key)
    if not p.exists():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        ts = obj.get("_cached_at", 0)
        if ttl_seconds is not None and (time.time() - ts) > ttl_seconds:
            return None
        return obj.get("data")
    except Exception:
        return None

def cache_set(cache_dir: Path, key: str, data):
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = _key_to_path(cache_dir, key)
    obj = {"_cached_at": time.time(), "data": data}
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
