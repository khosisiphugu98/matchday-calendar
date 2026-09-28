#!/usr/bin/env python3
"""Serve the calendar locally with live data.

    python3 serve.py            # http://localhost:8790
    python3 serve.py 9000       # another port

ESPN's feed doesn't send CORS headers to browsers, so the page can't call it
directly. This server hands out the static files and relays
/api/espn/<league>/<YYYYMM> to ESPN (cached 60s). On a static host with no
proxy (e.g. GitLab Pages) the page quietly falls back to fixtures.js.
"""
import http.server, json, os, re, subprocess, sys, time, urllib.request, ssl

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
ROOT = os.path.dirname(os.path.abspath(__file__))
API = "https://site.api.espn.com/apis/site/v2/sports/soccer/{}/scoreboard?dates={}&limit=1000"
ROUTE = re.compile(r"^/api/espn/([a-z0-9._]+)/(\d{6})$")
CACHE = {}

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = None

def fetch(url):
    if CTX is None:  # python.org builds lack a CA bundle; curl uses the system keychain
        return subprocess.run(["curl", "-s", "--compressed", "-m", "30", "-f", url],
                              capture_output=True, check=True).stdout
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "fixtures-calendar"}),
                                timeout=30, context=CTX) as r:
        return r.read()

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def do_GET(self):
        m = ROUTE.match(self.path.split("?")[0])
        if not m:
            return super().do_GET()
        key = m.groups()
        hit = CACHE.get(key)
        try:
            if not hit or time.time() - hit[0] > 60:
                hit = CACHE[key] = (time.time(), fetch(API.format(*key)))
            body, code = hit[1], 200
        except Exception as e:
            body, code = json.dumps({"error": str(e)}).encode(), 502
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if "/api/" not in (args[0] if args else ""):
            super().log_message(fmt, *args)

if __name__ == "__main__":
    print(f"Matchday Calendar on http://localhost:{PORT}")
    http.server.ThreadingHTTPServer(("", PORT), Handler).serve_forever()
