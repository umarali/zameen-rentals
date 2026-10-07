#!/usr/bin/env python3
"""Local dev dashboard: crawler, data, the app on :8000, worktrees, PRs, ports.

    python3 tools/dev_dashboard.py        # then open http://127.0.0.1:8900

Binds to 127.0.0.1 only and reads the database read-only. The only action it
takes is starting the app on :8000 when nothing is listening there; it never
stops a process. Standard library only.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DASH_PORT = int(os.environ.get("ZR_DASH_PORT", "8900"))
APP_PORT = 8000
REPO = "umarali/zameen-rentals"

# Ports the parallel sessions agreed on, so the ports panel can name owners.
PORT_OWNERS = [
    (8000, 8000, "your app"),
    (8100, 8100, "zameenrental-c4 tests (NL accuracy)"),
    (8200, 8200, "zameenrental-fe tests (design)"),
    (8300, 8399, "zameenrental-2a verify skill"),
    (8400, 8400, "zameenrental-d2 tests (voice search)"),
    (DASH_PORT, DASH_PORT, "this dashboard"),
]

QUICK_TESTS = [
    ("Karachi: 2-bed flats in DHA Phase 6", "city=karachi&area=DHA+Phase+6&type=apartment&beds=2"),
    ("Lahore: houses in Johar Town", "city=lahore&area=Johar+Town&type=house"),
    ("Islamabad: flats in F-8", "city=islamabad&area=F+8&type=apartment"),
    ("Karachi: rooms under Rs 30k", "city=karachi&type=room&price_max=30000"),
]

PROBLEM_RE = re.compile(
    r"Traceback| ERROR | CRITICAL |HTTP/[0-9.]+ (?:403|429|5\d\d)|disallows|[Pp]ausing|consecutive errors|Crawler stopped"
)
LOG_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _run(cmd, cwd=None, timeout=10):
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def main_checkout():
    """The repo's primary worktree, which holds data/ and runs the app."""
    first = _run(["git", "worktree", "list", "--porcelain"], cwd=HERE).splitlines()
    if first and first[0].startswith("worktree "):
        return Path(first[0][len("worktree "):])
    return HERE


MAIN = main_checkout()
DATA_DIR = Path(os.environ.get("ZAMEENRENTALS_DB_DIR") or (
    MAIN / "data" / "rebuild" if (MAIN / "data" / "rebuild" / "zameenrentals.db").exists() else MAIN / "data"
))


# ── Collectors ──

def parse_lsof(text):
    """Map listening port -> pid from `lsof -nP -iTCP -sTCP:LISTEN` output."""
    ports = {}
    for line in text.splitlines()[1:]:
        cols = line.split()
        if len(cols) < 9:
            continue
        m = re.search(r":(\d+)$", cols[8])
        if m:
            ports.setdefault(int(m.group(1)), int(cols[1]))
    return ports


def port_owner(port):
    return next((label for lo, hi, label in PORT_OWNERS if lo <= port <= hi), "")


def ports_status():
    listening = parse_lsof(_run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"]))
    rows = []
    for port, pid in sorted(listening.items()):
        if 8000 <= port <= 8999:
            cmd = _run(["ps", "-o", "command=", "-p", str(pid)]).strip()
            rows.append({"port": port, "pid": pid, "owner": port_owner(port), "command": cmd[:140]})
    return rows


def app_status():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/api/health", timeout=1.5) as resp:
            health = json.loads(resp.read())
        return {"up": True, "version": health.get("version"), "url": f"http://localhost:{APP_PORT}"}
    except (OSError, ValueError):
        return {"up": False, "url": f"http://localhost:{APP_PORT}"}


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def _read_int(path):
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def analyze_log(lines, now):
    """Summarise crawler log lines: recent request rate, 404s, problems, last activity."""
    cutoff = now - timedelta(minutes=5)
    recent_requests = recent_404 = 0
    problems, last_ts, last_pass = [], None, None
    for line in lines:
        m = LOG_TS_RE.match(line)
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") if m else None
        if ts:
            last_ts = ts
        if "HTTP Request" in line and ts and ts >= cutoff:
            recent_requests += 1
            if "HTTP/1.1 404" in line:
                recent_404 += 1
        if "Phase A complete" in line:
            last_pass = line.strip()
        if PROBLEM_RE.search(line):
            problems.append(line.strip()[:220])
    return {
        "requests_last_5min": recent_requests,
        "not_found_last_5min": recent_404,
        "problems": problems[-8:],
        "last_activity": last_ts.isoformat(sep=" ") if last_ts else None,
        "last_pass": last_pass,
    }


def lock_holder(lock_path):
    """PID holding the crawler lock file open; the OS knows even if its contents were lost."""
    pids = _run(["lsof", "-t", str(lock_path)]).split()
    return int(pids[0]) if pids else _read_int(lock_path)


def crawler_status():
    pid = _read_int(DATA_DIR / "crawler.pid")
    lock_pid = lock_holder(DATA_DIR / "crawler.lock")
    log = DATA_DIR / "crawler.log"
    lines = []
    if log.exists():
        with log.open("rb") as fh:
            fh.seek(max(0, log.stat().st_size - 400_000))
            lines = fh.read().decode("utf-8", "replace").replace("\x00", "").splitlines()
    status = analyze_log(lines, datetime.now())
    status.update(pid=pid, running=_pid_alive(pid), lock_pid=lock_pid, log=str(log))
    return status


def data_status():
    db = DATA_DIR / "zameenrentals.db"
    if not db.exists():
        return {"db": str(db), "missing": True}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        cities = [dict(r) for r in conn.execute("""
            SELECT city, COUNT(*) AS listings,
                   SUM(location_source = 'listing_exact') AS exact_geo,
                   SUM(phone IS NOT NULL OR whatsapp_phone IS NOT NULL) AS with_contact,
                   SUM(property_type IS NULL) AS untyped
            FROM listings GROUP BY city ORDER BY listings DESC
        """)]
        crawl = dict(conn.execute("""
            SELECT COUNT(*) AS areas, SUM(last_crawl_at IS NOT NULL) AS crawled,
                   MAX(last_crawl_at) AS last_crawl_at
            FROM crawl_state
        """).fetchone())
        newest = conn.execute("SELECT MAX(last_seen_at) FROM listings").fetchone()[0]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        paths = conn.execute("SELECT COUNT(DISTINCT zameen_id) FROM listing_locations").fetchone()[0] \
            if "listing_locations" in tables else None
    finally:
        conn.close()
    return {"db": str(db), "cities": cities, "crawl": crawl, "newest_seen_utc": newest,
            "listings_with_location_path": paths}


def git_status():
    rows = []
    blocks = _run(["git", "worktree", "list", "--porcelain"], cwd=HERE).strip().split("\n\n")
    for block in filter(None, blocks):
        info = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        path = info.get("worktree", "")
        branch = info.get("branch", "").replace("refs/heads/", "") or "(detached)"
        head = _run(["git", "log", "-1", "--format=%h|%s|%cr"], cwd=path).strip().split("|", 2)
        dirty = len([l for l in _run(["git", "status", "--porcelain"], cwd=path).splitlines() if l])
        counts = _run(["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"], cwd=path).split()
        rows.append({
            "path": path, "branch": branch, "dirty": dirty,
            "head": head[0] if head else "", "subject": head[1] if len(head) > 1 else "",
            "when": head[2] if len(head) > 2 else "",
            "behind": int(counts[0]) if len(counts) == 2 else None,
            "ahead": int(counts[1]) if len(counts) == 2 else None,
        })
    return rows


_pr_cache = {"at": 0.0, "rows": []}


def pr_status():
    if time.time() - _pr_cache["at"] > 60:
        out = _run(["gh", "pr", "list", "--repo", REPO, "--state", "open",
                    "--json", "number,title,headRefName,url,mergeStateStatus"], timeout=15)
        try:
            _pr_cache["rows"] = json.loads(out) if out else []
        except ValueError:
            _pr_cache["rows"] = []
        _pr_cache["at"] = time.time()
    return _pr_cache["rows"]


def collect():
    status = {"generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
              "main_checkout": str(MAIN), "data_dir": str(DATA_DIR),
              "quick_tests": [{"label": l, "url": f"http://localhost:{APP_PORT}/?{q}"} for l, q in QUICK_TESTS]}
    for key, fn in (("app", app_status), ("crawler", crawler_status), ("data", data_status),
                    ("worktrees", git_status), ("prs", pr_status), ("ports", ports_status)):
        try:
            status[key] = fn()
        except Exception as exc:  # one broken panel must not blank the page
            status[key] = {"error": f"{type(exc).__name__}: {exc}"}
    return status


def start_app():
    if APP_PORT in parse_lsof(_run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"])):
        return 409, {"error": f"Something is already listening on :{APP_PORT}."}
    log = (DATA_DIR / "web.log").open("ab")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(APP_PORT)],
        cwd=MAIN, env={**os.environ, "ZAMEENRENTALS_DB_DIR": str(DATA_DIR)},
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    return 202, {"pid": proc.pid, "log": str(DATA_DIR / "web.log")}


# ── HTTP ──

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self._send(200, json.dumps(collect()), "application/json")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        # The custom header forces a CORS preflight this server never answers,
        # so other websites can't trigger actions on localhost.
        if self.path != "/api/start-app" or self.headers.get("X-ZR-Dash") != "1":
            self._send(403, "forbidden", "text/plain")
            return
        code, body = start_app()
        self._send(code, json.dumps(body), "application/json")

    def log_message(self, *args):
        pass


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZameenRentals Dev</title>
<style>
:root{--bg:#f6f7f6;--card:#fff;--ink:#14201b;--muted:#5d6b64;--line:#e2e7e4;--brand:#127b5a;--ok:#127b5a;--warn:#b26b00;--bad:#c0362c;--chip:#eef4f1}
@media (prefers-color-scheme:dark){:root{--bg:#0f1513;--card:#17201c;--ink:#e6efe9;--muted:#93a39b;--line:#26322d;--brand:#42b883;--ok:#42b883;--warn:#e0a03a;--bad:#ef6b5f;--chip:#1e2a25}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;padding:18px 20px;border-bottom:1px solid var(--line)}
h1{font-size:18px;margin:0}h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 10px}
main{display:grid;gap:16px;padding:16px 20px 40px;grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;min-width:0}
.wide{grid-column:1/-1}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}.ok{background:var(--ok)}.bad{background:var(--bad)}.warn{background:var(--warn)}
.big{font-size:22px;font-weight:600}.muted{color:var(--muted)}.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px}
button,a.btn{font:inherit;border:1px solid var(--brand);background:var(--brand);color:#fff;border-radius:7px;padding:7px 12px;cursor:pointer;text-decoration:none;display:inline-block}
a.btn.ghost,button.ghost{background:transparent;color:var(--brand)}button:disabled{opacity:.5;cursor:default}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:500;font-size:12px}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}.tablewrap{overflow-x:auto}
.chip{background:var(--chip);border-radius:999px;padding:2px 8px;font-size:12px}
ul.log{list-style:none;margin:0;padding:0;max-height:220px;overflow:auto}ul.log li{padding:4px 0;border-bottom:1px solid var(--line)}
.quick a{display:block;padding:6px 0;color:var(--brand)}
</style></head><body>
<header><div><h1>ZameenRentals dev dashboard</h1><div class="muted" id="meta">Loading…</div></div>
<div class="row"><a class="btn" id="openApp" href="http://localhost:8000" target="_blank" rel="noopener">Open app</a>
<button class="ghost" id="startApp" hidden>Start app on :8000</button><button class="ghost" id="refresh">Refresh</button></div></header>
<main>
<section><h2>App</h2><div id="app"></div><div class="quick" id="quick"></div></section>
<section><h2>Crawler</h2><div id="crawler"></div></section>
<section class="wide"><h2>Data</h2><div id="data"></div></section>
<section class="wide"><h2>Worktrees and branches</h2><div id="worktrees"></div></section>
<section><h2>Open pull requests</h2><div id="prs"></div></section>
<section><h2>Ports 8000–8999</h2><div id="ports"></div></section>
<section class="wide"><h2>Crawler problems (latest)</h2><div id="problems"></div></section>
</main>
<script>
const $ = id => document.getElementById(id);
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else n.setAttribute(k, v); }
  for (const k of kids) n.append(k instanceof Node ? k : document.createTextNode(k ?? ''));
  return n;
}
const fmt = n => n == null ? '–' : Number(n).toLocaleString();
const pct = (a, b) => b ? Math.round(100 * a / b) + '%' : '–';
function table(cols, rows) {
  const head = el('tr', {}, ...cols.map(c => el('th', { class: c.n ? 'n' : '', text: c.h })));
  const body = rows.map(r => el('tr', {}, ...cols.map(c => { const v = c.v(r); return el('td', { class: c.n ? 'n' : '' }, v instanceof Node ? v : String(v ?? '–')); })));
  return el('div', { class: 'tablewrap' }, el('table', {}, el('thead', {}, head), el('tbody', {}, ...body)));
}
function errBox(x) { return el('div', { class: 'muted', text: x.error }); }
function render(s) {
  $('meta').textContent = `Updated ${s.generated_at} · data: ${s.data_dir}`;
  const app = s.app || {};
  $('app').replaceChildren(app.error ? errBox(app) : el('div', { class: 'row' }, el('span', { class: 'dot ' + (app.up ? 'ok' : 'bad') }),
    el('span', { class: 'big', text: app.up ? 'Running' : 'Not running' }), el('span', { class: 'muted', text: app.up ? `v${app.version} on ${app.url}` : 'Use "Start app" above' })));
  $('startApp').hidden = !!app.up; $('openApp').style.opacity = app.up ? 1 : .5;
  $('quick').replaceChildren(el('div', { class: 'muted', text: 'Quick tests' }), ...(s.quick_tests || []).map(q => el('a', { href: q.url, target: '_blank', rel: 'noopener', text: q.label })));
  const c = s.crawler || {};
  $('crawler').replaceChildren(c.error ? errBox(c) : el('div', {},
    el('div', { class: 'row' }, el('span', { class: 'dot ' + (c.running ? 'ok' : 'bad') }), el('span', { class: 'big', text: c.running ? 'Crawling' : 'Stopped' }),
      el('span', { class: 'chip', text: `PID ${c.pid ?? '–'}` }), el('span', { class: 'chip', text: c.lock_pid && c.lock_pid === c.pid ? 'holds lock' : 'lock: ' + (c.lock_pid ?? 'none') })),
    el('p', { class: 'muted' }, `${fmt(c.requests_last_5min)} requests in the last 5 min (${fmt(c.not_found_last_5min)} not found) · last activity ${c.last_activity ?? '–'}`),
    el('div', { class: 'mono muted', text: c.last_pass || 'No completed pass in the current log yet' })));
  const d = s.data || {};
  if (d.error || d.missing) $('data').replaceChildren(errBox({ error: d.error || 'No database at ' + d.db }));
  else {
    const total = d.cities.reduce((t, r) => t + r.listings, 0), cr = d.crawl || {};
    $('data').replaceChildren(
      el('div', { class: 'row' }, el('span', { class: 'big', text: fmt(total) + ' listings' }),
        el('span', { class: 'chip', text: `${fmt(cr.crawled)} / ${fmt(cr.areas)} areas crawled` }),
        el('span', { class: 'chip', text: `newest seen ${d.newest_seen_utc ? d.newest_seen_utc.slice(0, 16).replace('T', ' ') + ' UTC' : '–'}` }),
        d.listings_with_location_path != null ? el('span', { class: 'chip', text: `${fmt(d.listings_with_location_path)} with location path` }) : ''),
      table([{ h: 'City', v: r => r.city }, { h: 'Listings', n: 1, v: r => fmt(r.listings) }, { h: 'Exact pin', n: 1, v: r => pct(r.exact_geo, r.listings) },
             { h: 'Contact', n: 1, v: r => pct(r.with_contact, r.listings) }, { h: 'No type', n: 1, v: r => fmt(r.untyped) }], d.cities));
  }
  const w = s.worktrees;
  $('worktrees').replaceChildren(w && w.error ? errBox(w) : table([
    { h: 'Branch', v: r => el('strong', { text: r.branch }) }, { h: 'Folder', v: r => el('span', { class: 'mono', text: r.path.split('/').pop() }) },
    { h: 'Last commit', v: r => `${r.head} ${r.subject} (${r.when})` }, { h: 'vs main', v: r => r.ahead == null ? '–' : `+${r.ahead} / −${r.behind}` },
    { h: 'Uncommitted', n: 1, v: r => r.dirty ? el('span', { class: 'chip', text: r.dirty + ' files' }) : 'clean' }], w || []));
  const p = s.prs;
  $('prs').replaceChildren(p && p.error ? errBox(p) : (p && p.length ? table([
    { h: '#', v: r => el('a', { href: r.url, target: '_blank', rel: 'noopener', text: '#' + r.number }) }, { h: 'Title', v: r => r.title },
    { h: 'Branch', v: r => r.headRefName }, { h: 'State', v: r => r.mergeStateStatus }], p) : el('div', { class: 'muted', text: 'No open PRs.' })));
  const pt = s.ports;
  $('ports').replaceChildren(pt && pt.error ? errBox(pt) : (pt && pt.length ? table([
    { h: 'Port', v: r => r.port }, { h: 'Owner', v: r => r.owner || '?' }, { h: 'PID', v: r => r.pid }], pt) : el('div', { class: 'muted', text: 'Nothing listening.' })));
  const probs = (c.problems || []);
  $('problems').replaceChildren(probs.length ? el('ul', { class: 'log mono' }, ...probs.map(l => el('li', { text: l }))) : el('div', { class: 'muted', text: 'No errors, blocks or stops in the recent log.' }));
}
async function load() {
  try { render(await (await fetch('/api/status')).json()); } catch (e) { $('meta').textContent = 'Dashboard server unreachable: ' + e.message; }
}
$('refresh').onclick = load;
$('startApp').onclick = async () => {
  $('startApp').disabled = true;
  const r = await fetch('/api/start-app', { method: 'POST', headers: { 'X-ZR-Dash': '1' } });
  const body = await r.json().catch(() => ({}));
  $('meta').textContent = r.ok ? `Starting app (PID ${body.pid}); log: ${body.log}` : (body.error || 'Could not start the app');
  setTimeout(() => { $('startApp').disabled = false; load(); }, 4000);
};
load(); setInterval(() => { if (!document.hidden) load(); }, 10000);
</script></body></html>"""


def main():
    server = ThreadingHTTPServer(("127.0.0.1", DASH_PORT), Handler)
    print(f"ZameenRentals dev dashboard on http://127.0.0.1:{DASH_PORT}  (data: {DATA_DIR})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
