"""CP3a evidence run: real backend (dev_server.py, FAKE extraction, synthetic fixtures) + client core self-tests + the
client-core E2E scenario. Writes ../evidence/runs/<UTC>-<slug>/. Python 3 stdlib only.

  # owner's Mac (Android Studio's JDK on PATH, network for Gradle):
  python3 android/tools/cp3a_e2e.py --slug cp3a-client-e2e-mac --runner gradle
  # build sandbox without Gradle plugin access (uses Gradle's bundled Kotlin compiler):
  python3 android/tools/cp3a_e2e.py --slug cp3a-client-e2e --runner kotlinc --database-url postgresql://…/finassist_dev

No real slips, no model calls, no tokens or images are written to the evidence folder.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ANDROID = Path(__file__).resolve().parents[1]
REPO = ANDROID.parent
BACKEND = REPO / "backend"


def wait_health(url: str, timeout: float = 90) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url + "/v1/health", timeout=3) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(1)
    raise SystemExit("backend did not become healthy")


def kotlinc_cmds(out: Path) -> tuple[list[list[str]], list[str]]:
    lib = Path(os.environ.get("GRADLE_LIB", "/opt/gradle/lib"))
    pick = lambda pat: str(sorted(lib.glob(pat))[0])  # noqa: E731
    stdlib = pick("kotlin-stdlib-2*.jar")
    cp = ":".join(pick(p) for p in ("kotlin-compiler-embeddable-*.jar", "kotlin-stdlib-2*.jar", "kotlin-reflect-*.jar",
                                    "kotlin-daemon-embeddable-*.jar", "trove4j-*.jar", "annotations-*.jar", "kotlinx-coroutines-core-jvm-*.jar"))
    import tempfile

    classes = Path(tempfile.mkdtemp(prefix="cp3a-classes-"))  # build output stays out of the evidence folder
    compile_ = ["java", "-cp", cp, "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler", "-no-stdlib", "-no-reflect", "-jvm-target", "17", "-nowarn",
                "-cp", stdlib, "core/src/main/kotlin", "core/src/test/kotlin", "core/src/e2e/kotlin", "-d", str(classes)]
    run_cp = f"{classes}:{stdlib}"
    return [compile_], ["java", "-Dfile.encoding=UTF-8", "-cp", run_cp]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--runner", choices=["gradle", "kotlinc", "jar"], required=True)
    ap.add_argument("--jar-dir", default=None, help="runner=jar: dir with finassist-core-e2e.jar + kotlin-stdlib jar (compiled elsewhere from this tree)")
    ap.add_argument("--database-url", default=None, help="admin URL of finassist_dev; default: dev_server's local pgserver")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ") + "-" + a.slug
    out = REPO / "evidence" / "runs" / run_id
    out.mkdir(parents=True)
    base = f"http://127.0.0.1:{a.port}"

    srv_cmd = ["uv", "run"] + ([] if a.database_url else ["--with", "pixeltable-pgserver"]) + \
              ["python", "scripts/dev_server.py", "--provider", "fake", "--reset", "--port", str(a.port)] + \
              (["--database-url", a.database_url] if a.database_url else [])
    srv_log = open(out / "backend_server.log", "w", encoding="utf-8")
    srv = subprocess.Popen(srv_cmd, cwd=BACKEND, stdout=srv_log, stderr=subprocess.STDOUT)
    results: dict = {}
    try:
        health = wait_health(base)
        if a.runner == "gradle":
            gw = str(ANDROID / ("gradlew.bat" if os.name == "nt" else "gradlew"))
            steps = [("core_selftest", [gw, ":core:selfTest", "--console=plain"]),
                     ("client_e2e", [gw, ":core:e2e", f"-PbaseUrl={base}", "--console=plain"])]
            e2e_out = ANDROID / "core" / "build" / "e2e"
        elif a.runner == "jar":
            jd = Path(a.jar_dir)
            java = ["java", "-Dfile.encoding=UTF-8", "-cp", f"{jd / 'finassist-core-e2e.jar'}:{sorted(jd.glob('kotlin-stdlib-*.jar'))[0]}"]
            steps = [("core_selftest", java + ["dev.finassist.core.CoreSelfTest"]),
                     ("client_e2e", java + ["dev.finassist.e2e.Cp3aE2EKt", base, str(BACKEND / "fixtures/synthetic/slips"), str(out)])]
            e2e_out = out
        else:
            compiles, java = kotlinc_cmds(out)
            steps = [("compile_core", c) for c in compiles] + [
                ("core_selftest", java + ["dev.finassist.core.CoreSelfTest"]),
                ("client_e2e", java + ["dev.finassist.e2e.Cp3aE2EKt", base, str(BACKEND / "fixtures/synthetic/slips"), str(out)])]
            e2e_out = out
        for name, cmd in steps:
            t0 = time.time()
            p = subprocess.run(cmd, cwd=ANDROID, capture_output=True, text=True, encoding="utf-8", errors="replace")
            log = "\n".join(l for l in (p.stdout + p.stderr).splitlines() if "JAVA_TOOL_OPTIONS" not in l)
            (out / f"{name}.log").write_text(log, encoding="utf-8")
            results[name] = {"exit_code": p.returncode, "seconds": round(time.time() - t0, 1)}
            if p.returncode != 0:
                break
        steps_file = e2e_out / "client_e2e_steps.json"
        if steps_file.exists() and steps_file.parent != out:
            (out / "client_e2e_steps.json").write_text(steps_file.read_text(encoding="utf-8"), encoding="utf-8")
        e2e = json.loads((out / "client_e2e_steps.json").read_text(encoding="utf-8")) if (out / "client_e2e_steps.json").exists() else {}
    finally:
        srv.terminate()
        try:
            srv.wait(15)
        except subprocess.TimeoutExpired:
            srv.kill()
        srv_log.close()
    selftest_line = next((l for l in (out / "core_selftest.log").read_text(encoding="utf-8").splitlines()[::-1] if "passed" in l), None) \
        if (out / "core_selftest.log").exists() else None
    manifest = {
        "run_id": run_id, "kind": "CP3a client core + real backend end-to-end", "started_at_utc": started.isoformat(),
        "runner": a.runner, "commands": {k: v for k, v in results.items()},
        "environment": {"os": platform.platform(), "python": platform.python_version(),
                        "java": subprocess.run(["java", "-version"], capture_output=True, text=True).stderr.splitlines()[-3:]},
        "backend": {"health": health, "server": "backend/scripts/dev_server.py --provider fake --reset (real FastAPI + Postgres + RLS roles + embedded worker)"},
        "uses_mocks": ["extraction: FakeExtractionProvider preloaded with SYNTHETIC fixtures (test_mode=true reported by /v1/health)",
                       "no chat model (chat not part of CP3a)"],
        "not_covered": ["Android UI, Photo Picker and Keystore code (app module) — not built or run in this environment unless runner=gradle and the app was installed separately",
                        "album scanning, OS photo permissions, background work (CP3b)"],
        "core_selftest": selftest_line,
        "client_e2e": {"all_ok": e2e.get("all_ok"), "steps_ok": sum(1 for s in e2e.get("steps", []) if s.get("ok")), "steps": len(e2e.get("steps", []))},
        "data": "synthetic fixtures only; no images or tokens stored here",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"run_id": run_id, "core_selftest": selftest_line, "client_e2e": manifest["client_e2e"], "commands": results}, ensure_ascii=False))
    ok = all(r["exit_code"] == 0 for r in results.values()) and e2e.get("all_ok") is True
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
