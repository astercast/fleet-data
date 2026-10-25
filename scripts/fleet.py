"""Runner. For one group ("fast" or "daily"): for each site, run its collectors with that site's repo as read-only input and
fleet-data/<site>/ as output. One site crashing or timing out never stops the others. Writes <site>/runs.json."""
import json, os, subprocess, sys, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
m = json.load(open(os.path.join(ROOT, "fleet.json"))); group = sys.argv[1]; only = sys.argv[2:] 
for site, c in m["sites"].items():
    if c["group"] != group or (only and site not in only): continue
    src, out = os.path.join(ROOT, "src", site), os.path.join(ROOT, site); os.makedirs(out, exist_ok=True); runs = []
    for col in c["collectors"]:
        path = os.path.join(src, col); t = time.time()
        if not os.path.exists(path): runs.append({"collector": col, "ok": False, "error": "missing in site repo"}); continue
        env = dict(os.environ, HB_SRC=os.path.join(src, "data", "v1"), HB_OUT=out, PYTHONPATH=os.path.join(ROOT, "scripts"), PYTHONDONTWRITEBYTECODE="1")
        limit = int(os.environ.get("FLEET_COLLECTOR_TIMEOUT", "3600"))
        try:
            r = subprocess.run([sys.executable, path], env=env, timeout=limit, capture_output=True, text=True)
            runs.append({"collector": col, "ok": r.returncode == 0, "seconds": round(time.time() - t, 1), "error": None if r.returncode == 0 else (r.stderr or r.stdout)[-300:]})
        except subprocess.TimeoutExpired: runs.append({"collector": col, "ok": False, "error": f"timeout {limit}s"})
    json.dump({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": runs}, open(os.path.join(out, "runs.json"), "w"), indent=1)
    print(site, [("ok" if r["ok"] else "FAIL " + str(r["error"])[:80]) for r in runs])
