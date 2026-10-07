"""Parsing helpers behind tools/dev_dashboard.py."""
import importlib.util
from datetime import datetime
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "dev_dashboard", Path(__file__).resolve().parent.parent / "tools" / "dev_dashboard.py"
)
dash = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dash)


def test_parse_lsof_maps_ports_to_first_pid():
    text = (
        "COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
        "Python  46465 me    7u  IPv4 0x1      0t0  TCP 127.0.0.1:8000 (LISTEN)\n"
        "node    11111 me    20u IPv6 0x2      0t0  TCP *:8200 (LISTEN)\n"
        "node    22222 me    21u IPv4 0x3      0t0  TCP *:8200 (LISTEN)\n"
    )
    assert dash.parse_lsof(text) == {8000: 46465, 8200: 11111}


def test_port_owner_names_agreed_ranges():
    assert dash.port_owner(8000) == "your app"
    assert "verify" in dash.port_owner(8342)
    assert dash.port_owner(8765) == ""


def test_analyze_log_counts_recent_requests_and_problems():
    now = datetime(2026, 10, 7, 13, 0, 0)
    lines = [
        '2026-10-07 12:40:00,1 INFO HTTP Request: GET https://www.zameen.com/a "HTTP/1.1 200 OK"',
        '2026-10-07 12:58:00,1 INFO HTTP Request: GET https://www.zameen.com/b "HTTP/1.1 200 OK"',
        '2026-10-07 12:58:30,429 INFO HTTP Request: GET https://www.zameen.com/e "HTTP/1.1 200 OK"',
        '2026-10-07 12:59:00,1 INFO HTTP Request: GET https://www.zameen.com/c "HTTP/1.1 404 Not Found"',
        '2026-10-07 12:59:30,429 INFO HTTP Request: GET https://www.zameen.com/d "HTTP/1.1 429 Too Many"',
        "2026-10-07 12:59:40,1 INFO [Phase A complete] 1130 areas, 5 new, 9 updated",
    ]
    out = dash.analyze_log(lines, now)
    assert out["requests_last_5min"] == 4
    assert out["not_found_last_5min"] == 1
    # The ",429" millisecond field alone must not count as a rate-limit problem.
    assert out["problems"] == [lines[4]]
    assert out["last_pass"].endswith("1130 areas, 5 new, 9 updated")
    assert out["last_activity"] == "2026-10-07 12:59:40"


import io
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_start_app_serializes_clicks_before_child_listens(monkeypatch, tmp_path):
    monkeypatch.setattr(dash, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dash, "_start_proc", None)
    monkeypatch.setattr(dash, "_run", lambda *a, **k: "")
    child = SimpleNamespace(pid=123, poll=lambda: None)
    spawn = Mock(return_value=child)
    monkeypatch.setattr(dash.subprocess, "Popen", spawn)
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: dash.start_app()[0], range(2)))
    assert sorted(codes) == [202, 409]
    spawn.assert_called_once()
    assert spawn.call_args.kwargs["stdout"].closed


@pytest.mark.parametrize("method,host,origin,header,expected", [
    ("POST", "127.0.0.1:8900", "https://evil.example", False, 403),  # form/no-cors
    ("POST", "127.0.0.1:8900", "https://evil.example", True, 403),
    ("POST", "evil.example:8900", "http://evil.example:8900", True, 403),  # rebinding
    ("GET", "evil.example:8900", None, False, 403),
    ("POST", "127.0.0.1:8900", "http://127.0.0.1:8900", True, 202),
    ("POST", "localhost:8900", None, True, 202),
])
def test_http_origin_and_host_guards(monkeypatch, method, host, origin, header, expected):
    # Exercise the actual HTTP parser without binding a port or starting an app.
    lines = [f"{method} /api/start-app HTTP/1.0", f"Host: {host}"]
    if origin:
        lines.append(f"Origin: {origin}")
    if header:
        lines.append("X-ZR-Dash: 1")
    request = ("\r\n".join(lines) + "\r\n\r\n").encode()
    output = bytearray()
    sock = SimpleNamespace(makefile=lambda *a: io.BytesIO(request), sendall=output.extend)
    start = Mock(return_value=(202, {"pid": 123}))
    monkeypatch.setattr(dash, "start_app", start)
    dash.Handler(sock, ("127.0.0.1", 4567), SimpleNamespace(server_address=("127.0.0.1", 8900)))
    assert bytes(output).splitlines()[0].split()[1] == str(expected).encode()
    assert start.call_count == (1 if expected == 202 else 0)


def test_concurrent_refresh_returns_cached_status_without_more_processes(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    snapshot = {"data": {"missing": True}, "app": {"up": False}}
    monkeypatch.setattr(dash, "_status_cache", snapshot)
    def slow_collect():
        entered.set()
        assert release.wait(2)
        return snapshot
    collector = Mock(side_effect=slow_collect)
    monkeypatch.setattr(dash, "_collect", collector)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(dash.collect)
        try:
            assert entered.wait(1)
            assert dash.collect() is snapshot
            collector.assert_called_once()
        finally:
            release.set()
        assert first.result() is snapshot


def test_subprocesses_share_the_refresh_time_budget(monkeypatch):
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok"))
    monkeypatch.setattr(dash.subprocess, "run", run)
    monkeypatch.setattr(dash.time, "monotonic", lambda: 10)
    token = dash._deadline.set(10.25)
    try:
        assert dash._run(["git", "status"]) == "ok"
        assert run.call_args.kwargs["timeout"] == 0.25
        dash._deadline.set(9)
        with pytest.raises(TimeoutError):
            dash._run(["git", "status"])
        run.assert_called_once()
    finally:
        dash._deadline.reset(token)


@pytest.mark.parametrize("output,unavailable", [("", True), ("[]", False)])
def test_failed_pr_lookup_is_not_reported_as_no_open_prs(monkeypatch, output, unavailable):
    monkeypatch.setattr(dash, "_pr_cache", {"at": 0, "rows": []})
    monkeypatch.setattr(dash, "_run", lambda *args, **kwargs: output)
    result = dash.pr_status()
    if unavailable:
        assert result == {"error": "Could not load pull requests."}
    else:
        assert result == []
