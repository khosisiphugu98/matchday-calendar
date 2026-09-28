#!/usr/bin/env python3
"""Pull every fixture for the 2026-27 season from ESPN's public soccer API
into fixtures.js, which index.html loads as its offline snapshot.

Re-run any time: python3 fetch_fixtures.py
The page also refreshes the month on screen live from the same API.
"""
import json, datetime as dt, concurrent.futures as cf, urllib.request, gzip, sys, os, ssl, subprocess, time

try:  # python.org builds on macOS ship without a CA bundle
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = None

START, END = (2026, 9), (2027, 7)   # Sept 2026 -> end of July 2027 (covers Gold Cup / Nations League finals)
API = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={ym}&limit=1000"

# slug -> (label, short, group). Groups drive the market presets in the page.
LEAGUES = {
    "ger.1":                   ("Bundesliga", "BL", "dach"),
    "ger.2":                   ("2. Bundesliga", "BL2", "dach"),
    "ger.dfb_pokal":           ("DFB-Pokal", "DFB", "dach"),
    "aut.1":                   ("Austrian Bundesliga", "AUT", "dach"),
    "sui.1":                   ("Swiss Super League", "SUI", "dach"),
    "eng.1":                   ("Premier League", "EPL", "europe"),
    "eng.fa":                  ("FA Cup", "FAC", "europe"),
    "eng.league_cup":          ("Carabao Cup", "EFL", "europe"),
    "esp.1":                   ("La Liga", "LL", "europe"),
    "esp.copa_del_rey":        ("Copa del Rey", "CDR", "europe"),
    "ita.1":                   ("Serie A", "SA", "europe"),
    "fra.1":                   ("Ligue 1", "L1", "europe"),
    "uefa.champions":          ("Champions League", "UCL", "uefa"),
    "uefa.europa":             ("Europa League", "UEL", "uefa"),
    "uefa.europa.conf":        ("Conference League", "UECL", "uefa"),
    "uefa.nations":            ("UEFA Nations League", "UNL", "intl"),
    "uefa.euroq":              ("Euro 2028 Qualifiers", "EQ", "intl"),
    "fifa.friendly":           ("International Friendlies", "FR", "intl"),
    "usa.1":                   ("MLS", "MLS", "us"),
    "mex.1":                   ("Liga MX", "LMX", "us"),
    "concacaf.champions":      ("Concacaf Champions Cup", "CCC", "us"),
    "concacaf.nations.league": ("Concacaf Nations League", "CNL", "us"),
    "concacaf.gold":           ("Concacaf Gold Cup", "GC", "us"),
}

def months():
    y, m = START
    while (y, m) <= END:
        yield f"{y}{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

def get(url):
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    for attempt in range(4):
        if attempt:
            time.sleep(2 ** attempt)  # 2s, 4s, 8s backoff
        try:
            if CTX is None:  # no certifi: let curl use the system keychain
                return json.loads(subprocess.run(["curl", "-s", "--compressed", "-m", "40", url],
                                                 capture_output=True, check=True).stdout)
            with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except Exception as e:
            err = e
    print("  failed:", url, err, file=sys.stderr)
    return None

def pull(slug, ym):
    data = get(API.format(slug=slug, ym=ym))
    return slug, ym, None if data is None else data.get("events", [])

def load_previous(path):
    """The last good snapshot: used to fill in any league/month whose request failed this run."""
    try:
        raw = open(path, encoding="utf-8").read()
        return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (OSError, ValueError):
        return None

def main():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures.js")
    teams, fixtures, seen, failed = {}, [], set(), []
    jobs = [(s, ym) for s in LEAGUES for ym in months()]
    with cf.ThreadPoolExecutor(8) as ex:
        for slug, ym, events in ex.map(lambda j: pull(*j), jobs):
            if events is None:
                failed.append((slug, ym))
                continue
            for e in events:
                if e["id"] in seen:
                    continue
                seen.add(e["id"])
                c = e["competitions"][0]
                side = {t["homeAway"]: t for t in c["competitors"]}
                if "home" not in side or "away" not in side:
                    continue
                for t in (side["home"], side["away"]):
                    tm = t["team"]
                    teams.setdefault(tm["id"], {"n": tm.get("displayName") or tm.get("name"),
                                                "a": tm.get("abbreviation", ""),
                                                "lg": tm.get("logo", "")})
                st = e["status"]["type"]
                bc = sorted({n for b in c.get("broadcasts", []) for n in b.get("names", [])})
                fixtures.append({
                    "id": e["id"], "l": slug, "d": e["date"],
                    "tv": c.get("timeValid", True),
                    "h": side["home"]["team"]["id"], "a": side["away"]["team"]["id"],
                    "hs": side["home"].get("score") if st["state"] != "pre" else None,
                    "as": side["away"].get("score") if st["state"] != "pre" else None,
                    "s": st["state"], "sd": st.get("shortDetail", ""),
                    "r": (c.get("altGameNote") or "").split(", ", 1)[1] if ", " in (c.get("altGameNote") or "") else "",  # round / group, e.g. "League Phase"
                    "v": ", ".join(x for x in [c.get("venue", {}).get("fullName"), c.get("venue", {}).get("address", {}).get("city")] if x),
                    "b": bc,
                })
    if len(failed) > len(jobs) // 4:  # feed down or blocked: keep the existing snapshot rather than publish a gutted calendar
        sys.exit(f"{len(failed)} of {len(jobs)} requests failed; leaving fixtures.js unchanged.")
    if failed:
        # carry those league/months over from the previous snapshot so a single bad request can't blank a month
        prev = load_previous(path)
        if prev is None:
            sys.exit(f"{len(failed)} requests failed and there is no previous snapshot to fill from.")
        gaps = set(failed)
        for f in prev["fixtures"]:
            if (f["l"], f["d"][:7].replace("-", "")) in gaps and f["id"] not in seen:
                seen.add(f["id"])
                fixtures.append(f)
                for t in (f["h"], f["a"]):
                    if t in prev["teams"]:
                        teams.setdefault(t, prev["teams"][t])
        print(f"::warning::{len(failed)} requests failed, kept previous data for: "
              + ", ".join(f"{s}/{ym}" for s, ym in failed))
    fixtures.sort(key=lambda f: f["d"])
    if len(fixtures) < 1000:
        sys.exit(f"Only {len(fixtures)} fixtures; leaving fixtures.js unchanged.")
    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "leagues": {k: {"name": v[0], "short": v[1], "group": v[2]} for k, v in LEAGUES.items()},
        "teams": teams, "fixtures": fixtures,
    }
    # "<" escaped so feed text can never close the <script> it's inlined into
    js = "window.FIXTURES = " + json.dumps(out, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c") + ";\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(js)
    os.replace(tmp, path)
    # one-file copy with the data inlined, for sending as an attachment (no hosting needed)
    here = os.path.dirname(path)
    page = open(os.path.join(here, "index.html"), encoding="utf-8").read()
    with open(os.path.join(here, "matchday-calendar.html"), "w", encoding="utf-8") as f:
        f.write(page.replace('<script src="fixtures.js"></script>', "<script>" + js + "</script>"))
    counts = {}
    for x in fixtures:
        counts[x["l"]] = counts.get(x["l"], 0) + 1
    for k in LEAGUES:
        print(f"{LEAGUES[k][0]:28} {counts.get(k, 0):5}")
    print(f"{'TOTAL':28} {len(fixtures):5}  ({len(teams)} teams) -> {path}")

if __name__ == "__main__":
    main()
