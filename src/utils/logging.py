import json, time, os
from pathlib import Path

def log_event(log_path: Path, payload: dict):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["_ts"] = time.time()
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
