"""Fleet heartbeat lib v2. One file, standard library only.
HB_SRC = the site's own repo data folder (read-only, for matching). HB_OUT = where this site's live data is written."""
import json, gzip, hashlib, os, re, time, urllib.request, urllib.error
from datetime import datetime, timezone
UA = "AsterFleetHeartbeat/2.0 (+https://github.com/astercast/fleet-data)"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("HB_OUT", os.path.join(HERE, "..", "out"))
SRC = os.environ.get("HB_SRC", OUT)
now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def get(url, timeout=20, tries=3, headers=None):
    """(bytes, None) or (None, error). Never raises. gzip, real user agent, no hammering a closed door."""
    h = {"User-Agent": UA, "Accept-Encoding": "gzip", **(headers or {})}; err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                b = r.read(); return (gzip.decompress(b) if r.headers.get("Content-Encoding") == "gzip" else b), None
        except urllib.error.HTTPError as e:
            err = f"http {e.code}"
            if e.code in (400, 401, 403, 404, 410): break
        except Exception as e: err = type(e).__name__
        time.sleep(2 ** i)
    return None, err
def get_json(url, **kw):
    b, err = get(url, **kw)
    if b is None: return None, err
    try: return json.loads(b), None
    except Exception: return None, "bad json"
def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return default
def read(name, default=None):
    """Own live data first (what we wrote last run), then the site's baked data."""
    v = _load(os.path.join(OUT, name), None)
    return v if v is not None else _load(os.path.join(SRC, name), default)
def write_if_changed(name, obj, volatile=("generated_at", "checked_at")):
    path = os.path.join(OUT, name); strip = lambda o: {k: v for k, v in o.items() if k not in volatile} if isinstance(o, dict) else o
    old = _load(path, None)
    if old is not None and json.dumps(strip(old), sort_keys=True) == json.dumps(strip(obj), sort_keys=True): return False
    os.makedirs(OUT, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=1); f.write("\n")
    return True
def sig(text):
    t = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", text); t = re.sub(r"<[^>]+>", " ", t)
    return hashlib.sha256(re.sub(r"\s+", " ", t).strip().lower().encode()).hexdigest()[:16]

class Pulse:
    """Per-source ok/fail counts, newest-first changes, healthy flag. Keeps last good data when a source dies."""
    def __init__(self, stale_after_h=26):
        self.prev = _load(os.path.join(OUT, "pulse.json"), {"sources": [], "changes": []})
        self.sources, self.changes, self.stale_after_h = {}, [], stale_after_h
    def source(self, sid, label, ok, items=0, error=None, url=None):
        p = next((s for s in self.prev["sources"] if s["id"] == sid), {})
        self.sources[sid] = {"id": sid, "label": label, "url": url, "ok": ok, "items": items if ok else p.get("items", 0),
            "checked_at": now(), "last_ok_at": now() if ok else p.get("last_ok_at"), "error": None if ok else error,
            "fails_in_a_row": 0 if ok else p.get("fails_in_a_row", 0) + 1}
    def change(self, kind, title, ref=None): self.changes.append({"at": now(), "kind": kind, "title": title, "ref": ref})
    def write(self):
        keep = (self.changes + self.prev.get("changes", []))[:60]; seen, uniq = set(), []
        for c in keep:
            k = (c["kind"], c["title"])
            if k not in seen: seen.add(k); uniq.append(c)
        # merge in sources from other collectors of the same site that ran earlier
        merged = {s["id"]: s for s in self.prev.get("sources", [])}; merged.update(self.sources)
        ok = [s for s in merged.values() if s["ok"]]
        return write_if_changed("pulse.json", {"format": "pulse/2", "generated_at": now(), "stale_after_h": self.stale_after_h,
            "healthy": len(ok) == len(merged), "sources_ok": len(ok), "sources_total": len(merged),
            "last_data_change_at": (uniq[0]["at"] if uniq else self.prev.get("last_data_change_at")),
            "sources": sorted(merged.values(), key=lambda s: s["id"]), "changes": uniq})
