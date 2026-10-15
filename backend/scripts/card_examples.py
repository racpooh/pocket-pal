"""Approval-card examples from synthetic data → execution evidence (CP2). No model calls; no real slips.

  TEST_DATABASE_URL=... uv run python scripts/card_examples.py --slug card-examples
Requires a disposable database whose name ends with _test (it is reset).
Writes ../evidence/runs/<UTC>-<slug>/{manifest.json, cards.json, summary.md}.
Scenario: income ฿20,000 on 1 Nov, rent ฿5,000, balance ฿15,000 at 13:00 ICT on 15 Oct (fixed clock); default plan
Food ฿4,000 / Shopping ฿1,500 / Transport ฿1,500 / Entertainment ฿1,000 / Other ฿2,000.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "src"))
sys.path.insert(0, str(BACKEND))
FIXED_NOW = "2026-10-15T06:00:00+00:00"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    a = ap.parse_args()
    os.environ["FINASSIST_FIXED_NOW"] = FIXED_NOW
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        print("TEST_DATABASE_URL is required", file=sys.stderr)
        return 2
    from fastapi.testclient import TestClient

    from finassist.api.app import create_app
    from finassist.infra import Database, canonical_json, sha256
    from finassist.services.imports import LocalStorage
    from finassist.settings import Settings
    from tests.integration.conftest import User, _reset, app_url

    _reset(url)
    storage = LocalStorage(str(BACKEND / "var" / "card_uploads" / uuid.uuid4().hex))
    app = create_app(Settings(_env_file=None, model_provider="fake", database_url=url, storage_dir=str(storage.root)),
                     db=Database(app_url(url)), storage=storage)
    c = TestClient(app)
    u = User(c).onboard()
    u.approve_plan()
    checks: list[dict] = []

    def check(name: str, ok: bool) -> None:
        checks.append({"check": name, "ok": bool(ok)})

    def spend(amount: int, cat: str, hour: int = 12):
        r = u.req("POST", "/transactions", idem=True, json={"kind": "expense", "amount_satang": amount, "occurred_date": "2026-10-15",
                                                            "occurred_at": f"2026-10-15T{hour:02d}:00:00+07:00", "category": cat,
                                                            "payee": f"shop-{uuid.uuid4().hex[:4]}"})
        assert r.status_code == 201, r.text

    def realloc(amount: int):
        plan = u.req("GET", "/plan").json()["plan"]
        r = u.req("POST", "/proposals", json={"kind": "reallocate", "payload": {"plan_id": plan["id"], "from_pocket": u.pockets["Food"],
                                                                                "to_pocket": u.pockets["Shopping"], "amount_satang": amount}})
        assert r.status_code == 201, r.text
        return r.json()

    examples: dict[str, dict] = {}
    spend(25_000, "food")
    food_left = next(p for p in u.req("GET", "/plan").json()["pockets"] if p["name"] == "Food")["remaining_satang"]
    ex = examples["1_move_all_food_to_shopping"] = realloc(food_left)
    codes = [w["code"] for w in ex["card"]["warnings"]]
    check("food remaining is ฿3,750 after ฿250 spent", food_left == 375_000)
    check("card warns MOVES_ALL_REMAINING (high)", codes == ["MOVES_ALL_REMAINING"])
    check("source remaining after = 0", ex["card"]["transfer"]["from"]["remaining_after_satang"] == 0)
    reload = u.req("GET", f"/proposals/{ex['proposal_id']}").json()
    check("reload returns the identical card and hash", reload["card"] == ex["card"] and reload["card_hash"] == ex["card_hash"])
    check("card_hash = sha256(canonical card)", ex["card_hash"] == "sha256:" + sha256(canonical_json(ex["card"])).hex())
    examples["2_small_move_100"] = small = realloc(10_000)
    check("฿100 top-up has no warnings", small["card"]["warnings"] == [])
    edited = u.req("POST", f"/proposals/{ex['proposal_id']}/edit",
                   json={"payload_hash": ex["payload_hash"], "payload": {**ex["payload"], "amount_satang": 100_000}}).json()
    examples["3_edit_of_example_1_to_1000"] = edited
    old = u.req("GET", f"/proposals/{ex['proposal_id']}").json()
    check("edit → new id, old superseded", edited["edited_from"] == ex["proposal_id"] and old["status"] == "superseded")
    r_old = u.req("POST", f"/proposals/{ex['proposal_id']}/approve", idem=True,
                  json={"payload_hash": ex["payload_hash"], "card_hash": ex["card_hash"]})
    check("old approval cannot apply (409 PROPOSAL_NOT_PENDING)", r_old.status_code == 409)
    goal = u.req("POST", "/proposals", json={"kind": "goal_create", "payload": {"name": "Laptop", "target_satang": 3_000_000, "saved_satang": 0,
                                                                                "deadline": "2027-01-31", "contribution_satang_per_period": 200_000}}).json()
    examples["4_goal_create_overcommits_plan"] = goal
    check("goal card warns PLAN_EXCEEDS_MONEY_LEFT_AFTER", "PLAN_EXCEEDS_MONEY_LEFT_AFTER" in [w["code"] for w in goal["card"]["warnings"]])
    stale_src = realloc(100_000)
    spend(300_000, "food", hour=15)
    r = u.req("POST", f"/proposals/{stale_src['proposal_id']}/approve", idem=True,
              json={"payload_hash": stale_src["payload_hash"], "card_hash": stale_src["card_hash"]})
    rep = r.json()["error"]["details"]["replacement"]
    examples["5_stale_replacement_recomputed"] = {"original": stale_src, "replacement": rep}
    check("stale approval → 409 with recomputed replacement card", r.status_code == 409 and rep["card_hash"] != stale_src["card_hash"])
    ok = u.req("POST", f"/proposals/{edited['proposal_id']}/approve", idem=True,
               json={"payload_hash": edited["payload_hash"], "card_hash": edited["card_hash"]})
    check("edited proposal is stale too after new spending (strict watermark)", ok.status_code == 409)

    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ") + "-" + a.slug
    out = REPO / "evidence" / "runs" / run_id
    out.mkdir(parents=True)
    (out / "cards.json").write_text(json.dumps(examples, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    manifest = {"run_id": run_id, "kind": "approval-card examples", "fixed_now": FIXED_NOW, "uses_mocks": [],
                "model_identifiers": [], "model_calls": 0, "data": "synthetic profile and manual transactions only",
                "checks": checks, "all_ok": all(x["ok"] for x in checks),
                "environment": {"python": platform.python_version(), "platform": platform.platform()}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    c1 = examples["1_move_all_food_to_shopping"]["card"]
    lines = [f"# {run_id}", "", "Synthetic data, fixed clock, no model calls. Full cards: `cards.json`.", "",
             "Note: the ฿250 food expense is timed 12:00, before the 13:00 balance entry, so it is already in the balance (FI-8):",
             "it counts as Food spending but does not lower money left.", "", "## Example 1: move all unspent Food to Shopping", "",
             f"- {c1['summary']['text']}"]
    for ch in c1["changes"]:
        lines.append(f"- {ch['name']}: allocation {ch['allocation_before_satang']/100:,.2f} → {ch['allocation_after_satang']/100:,.2f}; "
                     f"left {ch['remaining_before_satang']/100:,.2f} → {ch['remaining_after_satang']/100:,.2f}")
    lines += [f"- warning: {w['code']} ({w['severity']}): {w['text']}" for w in c1["warnings"]]
    lines += [f"- money left {c1['effects']['money_left']['before_satang']/100:,.2f} → {c1['effects']['money_left']['after_satang']/100:,.2f}; "
              f"buffer and commitments unchanged; goals: {c1['effects']['goals']['reason_code']}", "", "## Checks", ""]
    lines += [f"- [{'x' if x['ok'] else ' '}] {x['check']}" for x in checks]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": run_id, "all_ok": manifest["all_ok"], "failed": [x for x in checks if not x["ok"]]}, ensure_ascii=False))
    return 0 if manifest["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
