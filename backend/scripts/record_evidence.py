"""Run the test suite and write an evidence bundle (docs/design/06 §5).

Usage (from backend/):  uv run python scripts/record_evidence.py --slug cp0-unit-db
Writes ../evidence/runs/<UTC>-<slug>/{manifest.json,pytest.log,junit.xml}.
It records what actually ran; it never fabricates results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout
        return out.stdout.strip() + ("+dirty" if dirty.strip() else "")
    except Exception:
        return "uncommitted"


def _content_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((BACKEND / "src").rglob("*.py")) + sorted((BACKEND / "db").rglob("*.sql")) + sorted((BACKEND / "tests").rglob("*.py")):
        h.update(str(p.relative_to(BACKEND)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _pg_version(url: str | None) -> str | None:
    if not url:
        return None
    try:
        import psycopg

        with psycopg.connect(url) as c:
            return c.execute("show server_version").fetchone()[0]
    except Exception as e:  # recorded, not hidden
        return f"unavailable: {type(e).__name__}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("pytest_args", nargs="*")
    a = ap.parse_args()

    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ") + "-" + a.slug
    out = REPO / "evidence" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)

    cmd = [sys.executable, "-m", "pytest", "-rs", "-v", f"--junitxml={out / 'junit.xml'}", *a.pytest_args]
    proc = subprocess.run(cmd, cwd=BACKEND, capture_output=True, text=True)
    (out / "pytest.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")

    cases = []
    suite = ET.parse(out / "junit.xml").getroot()
    for tc in suite.iter("testcase"):
        outcome = "passed"
        for tag in ("failure", "error", "skipped"):
            if tc.find(tag) is not None:
                outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
        cases.append({"id": f"{tc.get('classname')}::{tc.get('name')}", "outcome": outcome})
    counts = {k: sum(1 for c in cases if c["outcome"] == k) for k in ("passed", "failed", "error", "skipped")}

    db_url = os.environ.get("TEST_DATABASE_URL")
    manifest = {
        "run_id": run_id,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_version": {"git": _git_commit(), "content_sha256": _content_hash()},
        "command": " ".join(["pytest", *cmd[3:]]),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "postgres_server_version": _pg_version(db_url),
            "db_tests_enabled": bool(db_url),
        },
        "configuration": {"FINASSIST_MODEL_PROVIDER": os.environ.get("FINASSIST_MODEL_PROVIDER", "fake")},
        "model_identifiers": [],
        "uses_mocks": [
            "tests/integration: FakeExtractionProvider (returns ground-truth fields; no real OCR/vision call)",
            "tests/integration: ScriptedChatModel (fixed tool-call sequence; no real LLM)",
            "real components: FastAPI app, Postgres with RLS (API as finassist_app, worker as finassist_worker), worker logic, storage on local disk",
        ],
        "expected": "all collected tests pass; DB tests skipped only if TEST_DATABASE_URL unset",
        "actual": counts,
        "exit_code": proc.returncode,
        "cases": cases,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "actual": counts, "exit_code": proc.returncode}))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
