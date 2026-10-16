"""Evidence: local environment profiles are isolated (Codex review after the 16 Oct device-DB reset).

  FINASSIST_PGDATA_ROOT=<fresh dir> uv run --with pixeltable-pgserver python scripts/check_env_isolation.py \
      --slug env-isolation --jar-dir <dir with finassist-core-e2e.jar>

What it does (synthetic fixtures, fake extraction, no model calls):
  1. refusals: legacy FINASSIST_PGDATA; a second server on a taken port; e2e profile on the dev port; cp3a_e2e on 8000;
     a cluster whose marker names another profile; a --database-url that names another profile's database
  2. starts the PHONE profile (dev, port 8000), signs up account A, imports one synthetic slip
  3. while it runs: the pytest DB suite file test_cp3a_client_api.py (test profile; rotates finassist_app/worker) and a
     full cp3a_e2e.py run (e2e profile, port 8001, with --reset)
  4. checks the dev server afterwards: A's token still valid, A's records unchanged, a new upload still imports (new API
     and worker connections authenticate), and the three profiles live in three different clusters
Writes evidence/runs/<UTC>-<slug>/{manifest.json, *.log}. No tokens are written.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
SLIPS = BACKEND / "fixtures" / "synthetic" / "slips"
sys.path.insert(0, str(BACKEND / "scripts"))
import local_envs  # noqa: E402

BASE = "http://127.0.0.1:8000"
UV = ["uv", "run", "--with", "pixeltable-pgserver", "python"]


def call(method: str, path: str, token: str | None = None, body: dict | None = None, files: tuple | None = None):
    headers, data = {}, None
    if token:
        headers["Authorization"] = "Bearer " + token
    if files:
        b = uuid.uuid4().hex
        name, content, fields = files
        parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n'.encode() + content + b"\r\n")
        data = b"".join(parts) + f"--{b}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={b}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + "/v1" + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def wait_health(timeout: float = 90) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(BASE + "/v1/health", timeout=3) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(1)
    raise SystemExit("dev server did not become healthy")


def upload_and_wait(token: str, file: str) -> str:
    st, r = call("POST", "/uploads", token, files=(file, (SLIPS / file).read_bytes(), {"captured_at": "2026-10-15T13:00:00+07:00"}))
    assert st == 202, (st, r)
    for _ in range(60):
        st2, u = call("GET", f"/uploads/{r['upload_id']}", token)
        if u["status"] not in ("received", "processing", "queued"):
            return u["status"]
        time.sleep(0.5)
    return "timeout"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--jar-dir", required=True)
    a = ap.parse_args()
    root = os.environ.get("FINASSIST_PGDATA_ROOT")
    if not root:
        raise SystemExit("set FINASSIST_PGDATA_ROOT to a fresh directory for this check")
    started = datetime.now(timezone.utc)
    out = REPO / "evidence" / "runs" / (started.strftime("%Y%m%dT%H%M%SZ") + "-" + a.slug)
    out.mkdir(parents=True)
    checks: list[dict] = []

    def check(name: str, ok: bool, detail=None) -> None:
        checks.append({"check": name, "ok": bool(ok), **({"detail": detail} if detail is not None else {})})
        print(("PASS " if ok else "FAIL ") + name, detail if detail is not None else "", flush=True)

    def refused(name: str, cmd: list[str], expect: str, env: dict | None = None, cwd: Path = BACKEND) -> None:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120, env=env or os.environ.copy())
        msg = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
        check(name, p.returncode != 0 and expect in (p.stdout + p.stderr), msg[0][:200])

    env_legacy = os.environ.copy()
    env_legacy["FINASSIST_PGDATA"] = str(Path(root) / "legacy")
    refused("legacy FINASSIST_PGDATA refused", UV + ["scripts/dev_server.py", "--profile", "dev", "--provider", "fake"],
            "no longer supported", env=env_legacy)

    log = open(out / "dev_server.log", "w", encoding="utf-8")
    dev = subprocess.Popen(UV + ["scripts/dev_server.py", "--profile", "dev", "--provider", "fake", "--reset"], cwd=BACKEND,
                           stdout=log, stderr=subprocess.STDOUT)
    try:
        wait_health()
        check("dev server is the dev profile", dev.poll() is None and "PROFILE dev" in (out / "dev_server.log").read_text())
        refused("second server on the taken dev port refused", UV + ["scripts/dev_server.py", "--profile", "dev", "--provider", "fake"], "already in use")
        refused("e2e profile on the dev port refused", UV + ["scripts/dev_server.py", "--profile", "e2e", "--provider", "fake", "--port", "8000"], "belongs to profile 'dev'")
        refused("cp3a_e2e on port 8000 refused", ["python3", "android/tools/cp3a_e2e.py", "--slug", "x", "--runner", "jar", "--port", "8000"],
                "phone's dev server", cwd=REPO)
        dev_url = local_envs.local_admin_url(local_envs.PROFILES["dev"])
        refused("e2e profile with the dev database URL refused",
                UV + ["scripts/dev_server.py", "--profile", "e2e", "--provider", "fake", "--database-url", dev_url, "--port", "8011"], "refusing")
        bad_root = Path(root) / "marker-check"
        bad_root.mkdir(exist_ok=True)
        (bad_root / "pgdata-dev.profile").write_text("e2e")
        try:
            os.environ["FINASSIST_PGDATA_ROOT"] = str(bad_root)
            local_envs.cluster_dir(local_envs.PROFILES["dev"])
            check("cluster marked for another profile refused", False)
        except SystemExit as e:
            check("cluster marked for another profile refused", "belongs to profile 'e2e'" in str(e), str(e)[:120])
        finally:
            os.environ["FINASSIST_PGDATA_ROOT"] = root

        email = f"iso-{uuid.uuid4().hex[:8]}@example.test"
        call("POST", "/auth/signup", body={"email": email, "password": "isolation password 1"})
        token = call("POST", "/auth/login", body={"email": email, "password": "isolation password 1"})[1]["token"]
        me_a = call("GET", "/me", token)[1]["user_id"]
        call("POST", "/consents", token, {"scope": "photo_processing", "version": "v1", "params": {"scan_from": "2026-07-01"}})
        call("POST", "/consents", token, {"scope": "auto_import", "version": "v1"})
        check("dev: first synthetic slip imported", upload_and_wait(token, "slip_003_transfer_out.png") == "imported")
        before = call("GET", "/transactions", token)[1]

        tenv = os.environ.copy()
        tenv["TEST_DATABASE_URL"] = subprocess.run(UV + ["scripts/local_pg.py"], cwd=BACKEND, capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
        t = subprocess.run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", "tests/integration/test_cp3a_client_api.py"],
                           cwd=BACKEND, capture_output=True, text=True, env=tenv, timeout=600)
        (out / "pytest_test_profile.log").write_text(t.stdout[-4000:] + t.stderr[-2000:], encoding="utf-8")
        check("pytest (test profile) ran while dev server was up", t.returncode == 0 and "passed" in t.stdout,
              (t.stdout.strip().splitlines() or [""])[-1])

        e = subprocess.run(["python3", "android/tools/cp3a_e2e.py", "--slug", a.slug + "-e2e", "--runner", "jar", "--jar-dir", a.jar_dir],
                           cwd=REPO, capture_output=True, text=True, timeout=900)
        (out / "cp3a_e2e.log").write_text(e.stdout[-4000:] + e.stderr[-2000:], encoding="utf-8")
        check("cp3a_e2e (e2e profile, --reset, port 8001) ran while dev server was up", e.returncode == 0,
              (e.stdout.strip().splitlines() or [""])[-1][:300])

        st, me = call("GET", "/me", token)
        check("dev: A's token still valid after both runs", st == 200 and me["user_id"] == me_a)
        after = call("GET", "/transactions", token)[1]
        check("dev: A's records unchanged", after == before, {"before": len(before), "after": len(after)})
        check("dev: a new upload still imports (fresh API + worker connections)", upload_and_wait(token, "slip_004_transfer_out.png") == "imported")
        check("dev server still running", dev.poll() is None)
        dirs = {n: (Path(root) / local_envs.PROFILES[n].cluster) for n in ("dev", "e2e", "test")}
        check("three separate clusters", all((d / "PG_VERSION").exists() for d in dirs.values()) and len({d.resolve() for d in dirs.values()}) == 3,
              {k: v.name for k, v in dirs.items()})
    finally:
        dev.terminate()
        try:
            dev.wait(15)
        except subprocess.TimeoutExpired:
            dev.kill()
        log.close()

    ok = all(c["ok"] for c in checks)
    manifest = {"run_id": out.name, "kind": "local environment isolation check (synthetic fixtures, fake extraction, no model calls)",
                "started_at_utc": started.isoformat(), "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "environment": {"os": platform.platform(), "python": platform.python_version()},
                "profiles": {k: {"cluster": v.cluster, "database": v.database, "port": v.port} for k, v in local_envs.PROFILES.items()},
                "uses_mocks": ["extraction: FakeExtractionProvider with SYNTHETIC fixtures"],
                "checks": checks, "verdict": "PASS" if ok else "FAIL"}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"run_id": out.name, "verdict": manifest["verdict"], "passed": sum(c["ok"] for c in checks), "checks": len(checks)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
