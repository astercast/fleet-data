"""One GitHub issue per broken site in fleet-data: opens when a site goes down or stale, closes itself when it recovers.
Uses the gh CLI and the workflow's own token. Notifications go to the repo owner by email."""
import json, os, subprocess
s = json.load(open(os.path.join(os.path.dirname(__file__), "..", "status.json")))
def gh(*a): return subprocess.run(["gh", *a], capture_output=True, text=True).stdout
open_ = {i["title"]: i["number"] for i in json.loads(gh("issue", "list", "--state", "open", "--limit", "100", "--json", "title,number") or "[]")}
for r in s["sites"]:
    title = f'{r["site"]} needs a look'
    if r["state"] == "fail" and title not in open_:
        body = "\n".join(f"- {c[0]}: {c[2]}" for c in r["checks"] if c[1] != "ok") + f'\n\nLive: {r["live"]}'
        gh("issue", "create", "--title", title, "--body", body)
    elif r["state"] == "ok" and title in open_:
        gh("issue", "close", str(open_[title]), "--comment", "Recovered.")
