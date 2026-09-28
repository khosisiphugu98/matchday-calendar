# Matchday Calendar 26/27

Every club and international fixture from Sep 2026 to the end of the 2026-27 season
(Jul 2027), filterable by competition, team and top clashes.

| File | What it is |
|---|---|
| `index.html` | The calendar: month, agenda and season-heatmap views, filters, .ics export |
| `fixtures.js` | Snapshot of all fixtures (ESPN public feed), loaded by the page |
| `fetch_fixtures.py` | Rebuilds `fixtures.js`. Run it any time: `python3 fetch_fixtures.py` |
| `matchday-calendar.html` | One-file copy with the data built in, for emailing / Slack (rebuilt by the fetcher) |
| `serve.py` | Local server + ESPN relay so the month on screen refreshes live |
| `.github/workflows/pages.yml` | GitHub Pages: rebuilds the snapshot hourly and republishes |
| `.gitlab-ci.yml` | GitLab Pages job; rebuilds the snapshot on each run (add a daily schedule) |

Run locally: `python3 serve.py` → http://localhost:8790

Opening `index.html` directly, or hosting it statically, works too; it just shows the snapshot.
ESPN doesn't send CORS headers to browsers, which is why live refresh needs `serve.py`.

Rounds that aren't drawn yet (UCL/UEL knockouts, cup finals, Euro 2028 qualifiers, Gold Cup,
MLS 2027) appear as **key dates**, hand-maintained in the `KEY` / `TBD` arrays in `index.html`.
Once ESPN publishes those fixtures, re-running the fetcher picks them up automatically.
