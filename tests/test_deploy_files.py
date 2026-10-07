"""deploy/user-data.sh embeds copies of deploy/backup/ files; they must not drift."""
import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def _heredoc(target, marker):
    text = (DEPLOY / "user-data.sh").read_text()
    m = re.search(rf"cat > {re.escape(target)} <<'{marker}'\n(.*?)\n{marker}\n", text, re.S)
    assert m, f"no heredoc for {target}"
    return m.group(1)


def test_embedded_backup_script_matches_canonical_copy():
    embedded = _heredoc("/usr/local/bin/zameenrentals-backup.py", "PYEOF")
    assert embedded == (DEPLOY / "backup" / "zameenrentals-backup.py").read_text().rstrip("\n")


def test_embedded_backup_units_match_canonical_copies():
    for unit in ("zameenrentals-backup.service", "zameenrentals-backup.timer"):
        embedded = _heredoc(f"/etc/systemd/system/{unit}", "UNIT")
        assert embedded == (DEPLOY / "backup" / unit).read_text().rstrip("\n"), unit
