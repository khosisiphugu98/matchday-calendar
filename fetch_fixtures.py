#!/usr/bin/env python3
"""Pull every fixture for the 2026-27 season from ESPN's public soccer API
into fixtures.js, which index.html loads as its offline snapshot.

Re-run any time: python3 fetch_fixtures.py
The page also refreshes the month on screen live from the same API.
"""
import json, datetime as dt, concurrent.futures as cf, urllib.request, gzip, sys, os, ssl, subprocess

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
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "fixtures-calendar"})
    for attempt in range(3):
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
    return {}

def pull(slug, ym):
    return slug, get(API.format(slug=slug, ym=ym)).get("events", [])

def main():
    teams, fixtures, seen = {}, [], set()
    jobs = [(s, ym) for s in LEAGUES for ym in months()]
    with cf.ThreadPoolExecutor(12) as ex:
        for slug, events in ex.map(lambda j: pull(*j), jobs):
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
    fixtures.sort(key=lambda f: f["d"])
    if len(fixtures) < 1000:  # feed down or blocked: keep the existing snapshot rather than publish a near-empty calendar
        sys.exit(f"Only {len(fixtures)} fixtures fetched; leaving fixtures.js unchanged.")
    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "leagues": {k: {"name": v[0], "short": v[1], "group": v[2]} for k, v in LEAGUES.items()},
        "teams": teams, "fixtures": fixtures,
    }
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures.js")
    with open(path, "w") as f:
        f.write("window.FIXTURES = ")
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
        f.write(";\n")
    # one-file copy with the data inlined, for sending as an attachment (no hosting needed)
    here = os.path.dirname(path)
    page = open(os.path.join(here, "index.html")).read()
    data = open(path).read().replace("</script", "<\\/script")
    with open(os.path.join(here, "matchday-calendar.html"), "w") as f:
        f.write(page.replace('<script src="fixtures.js"></script>', "<script>" + data + "</script>"))
    counts = {}
    for x in fixtures:
        counts[x["l"]] = counts.get(x["l"], 0) + 1
    for k in LEAGUES:
        print(f"{LEAGUES[k][0]:28} {counts.get(k, 0):5}")
    print(f"{'TOTAL':28} {len(fixtures):5}  ({len(teams)} teams) -> {path}")

if __name__ == "__main__":
    main()
