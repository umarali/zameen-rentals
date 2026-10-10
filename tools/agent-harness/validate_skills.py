#!/usr/bin/env python3
"""Verify the complete vendored skill inventory against its committed lock file."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
lock = json.loads((root / 'docs/agents/skills-lock.json').read_text())
base = root / 'tools/agent-harness/skills'
expected_names = {entry['name'] for entry in lock['skills']}
actual_names = {p.name for p in base.iterdir() if p.is_dir()}
if expected_names != actual_names:
    raise SystemExit('Skill directory inventory differs from lock file')
for entry in lock['skills']:
    directory = base / entry['name']
    expected = entry['files_sha256']
    actual = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    if not (directory / 'SKILL.md').is_file() or actual != expected:
        raise SystemExit(f'Skill hash mismatch: {entry["name"]}')
print(f'PASS: {len(expected_names)} skills match their complete pinned inventories')
