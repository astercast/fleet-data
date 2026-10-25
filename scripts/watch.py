"""Watchdog. For every site: how old is its live data, is each source healthy, and does the live site answer. Writes status.json,
which the status page reads, and prints the list of problems. Needs no keys."""
import glob, json, os, re, sys, time, urllib.request
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(__file__)); from lib import get, now
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
m = json.load(open(os.path.join(ROOT, "fleet.json"))); out, problems = [], []
age_h = lambda iso: round((datetime.now(timezone.utc) - datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() / 3600, 1) if iso else None
for site, c in m["sites"].items():
    p = os.path.join(ROOT, site, "pulse.json"); pulse = json.load(open(p)) if os.path.exists(p) else None
    row = {"site": site, "group": c["group"], "live": c["live"], "checks": []}
    if c["collectors"]:
        if not pulse: row["checks"].append(["data", "warn", "waiting for the first run"])
        else:
            a = age_h(pulse["generated_at"]); row["data_age_h"] = a; row["changed_age_h"] = age_h(pulse.get("last_data_change_at"))
            row["sources"] = [{"id": s["id"], "ok": s["ok"], "fails": s["fails_in_a_row"], "items": s["items"]} for s in pulse["sources"]]
            row["checks"].append(["freshness", "ok" if a <= c["stale_h"] else "fail", f"{a} h old, limit {c['stale_h']} h"])
            bad = [s["id"] for s in pulse["sources"] if not s["ok"]]
            row["checks"].append(["sources", "ok" if not bad else ("warn" if len(bad) < len(pulse["sources"]) else "fail"), "all ok" if not bad else "down: " + ", ".join(bad)])
    if c.get("forbid_keys"):                                  # the site laws, enforced: no play counts on Aster, no price on Sonny
        rx, hits = re.compile(c["forbid_keys"], re.I), []
        def walk(o, f):
            if isinstance(o, dict):
                for k, v in o.items():
                    if rx.search(k): hits.append(f + ":" + k)
                    walk(v, f)
            elif isinstance(o, list):
                for v in o: walk(v, f)
        for f in glob.glob(os.path.join(ROOT, site, "*.json")):
            try: walk(json.load(open(f)), os.path.basename(f))
            except Exception: pass
        row["checks"].append(["law", "fail" if hits else "ok", ("forbidden field in " + ", ".join(sorted(set(hits))[:3])) if hits else "no forbidden fields"])
    t = time.time(); b, err = get(c["live"] + "/", timeout=15, tries=2); row["checks"].append(["site", "ok" if b else "fail", f"{round((time.time()-t)*1000)} ms" if b else err])
    if c.get("health"):
        b, err = get(c["live"] + c["health"], timeout=15, tries=2); row["checks"].append(["health", "ok" if b and b'"ok":true' in b.replace(b" ", b"") else "fail", "ok" if b else err])
    row["state"] = "fail" if any(k[1] == "fail" for k in row["checks"]) else "warn" if any(k[1] == "warn" for k in row["checks"]) else "ok"
    if row["state"] != "ok": problems.append((site, row["state"], [k for k in row["checks"] if k[1] != "ok"]))
    out.append(row)
json.dump({"format": "fleet-status/1", "generated_at": now(), "sites": out}, open(os.path.join(ROOT, "status.json"), "w"), indent=1)
for p in problems: print("PROBLEM", p)
print(f"{len(out)} sites, {len(problems)} problems")
