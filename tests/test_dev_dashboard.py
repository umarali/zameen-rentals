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
