import hashlib
from urllib.parse import urlparse

def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        u = url.strip()
        # strip fragments
        u = u.split("#", 1)[0]
        return u
    except Exception:
        return url

def fingerprint(event: dict) -> str:
    url = canonicalize_url(event.get("link",""))
    if url:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()
    # fallback: title + date + source
    key = f"{event.get('title','').strip().lower()}|{event.get('published','')}|{event.get('source','')}"
    return hashlib.sha256(key.encode('utf-8')).hexdigest()
