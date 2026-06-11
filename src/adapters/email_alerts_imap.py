# Optional adapter: IMAP ingestion for user-managed alerts.
# This is intentionally conservative: store minimal fields, extract first URL, and dedupe by Message-ID.
import os, re, imaplib, email
from email.header import decode_header

URL_RE = re.compile(r"https?://\S+", re.I)

def _decode(s):
    if not s:
        return ""
    parts = decode_header(s)
    out = ""
    for val, enc in parts:
        if isinstance(val, bytes):
            out += val.decode(enc or "utf-8", errors="ignore")
        else:
            out += str(val)
    return out

def fetch(_feed: dict, since_uid: int | None = None):
    host = os.getenv("IMAP_HOST", "").strip()
    user = os.getenv("IMAP_USER", "").strip()
    pw = os.getenv("IMAP_PASS", "").strip()
    mailbox = os.getenv("IMAP_MAILBOX", "INBOX").strip()
    port = int(os.getenv("IMAP_PORT", "993"))
    if not (host and user and pw):
        return [], None, "Missing IMAP credentials"

    m = imaplib.IMAP4_SSL(host, port)
    m.login(user, pw)
    m.select(mailbox)
    crit = "ALL"
    if since_uid:
        crit = f"(UID {since_uid}:*)"
    typ, data = m.uid('search', None, crit)
    if typ != 'OK':
        return [], since_uid, "IMAP search failed"
    uids = [int(x) for x in (data[0].split() if data and data[0] else [])]
    out = []
    max_uid = since_uid or 0
    for uid in uids[-200:]:  # safety cap per run
        typ, msgdata = m.uid('fetch', str(uid), '(RFC822)')
        if typ != 'OK' or not msgdata or not msgdata[0]:
            continue
        raw = msgdata[0][1]
        msg = email.message_from_bytes(raw)
        mid = msg.get('Message-ID','') or f"uid:{uid}"
        subj = _decode(msg.get('Subject',''))
        date = msg.get('Date','') or ''
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain" and part.get_payload(decode=True):
                    body = part.get_payload(decode=True).decode(errors="ignore")
                    break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(errors="ignore")
        url = ""
        m0 = URL_RE.search(body or "")
        if m0:
            url = m0.group(0).rstrip(').,]')
        snippet = (body or "").strip().replace("\n"," ")[:280]
        out.append({
            "title": subj or "Email alert",
            "link": url,
            "published": date,
            "summary": snippet,
            "source": "Email Alert",
            "evidence": [mid],
            "raw": {"email": {"uid": uid}}
        })
        if uid > max_uid:
            max_uid = uid
    m.logout()
    return out, max_uid, None
