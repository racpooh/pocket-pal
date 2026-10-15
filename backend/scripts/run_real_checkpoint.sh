#!/usr/bin/env bash
# Real-model checkpoint, run from YOUR terminal (the key stays on your machine).
#   cd <repo>/backend && bash scripts/run_real_checkpoint.sh
# Gates: config check → smoke (5 images) → full synthetic (40) → agent demo. Stops at the first failure.
# Budget guard: FINASSIST_BUDGET_USD (default 1.0) across all runs, tracked in ../evidence/usage_ledger.jsonl.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync -q
echo "== 1/4 config (no key printed)"
uv run python - <<'PY'
import json
from finassist.settings import get_settings
from finassist.providers import verify_model_access
s = get_settings(); s.require_real_provider()
assert s.model_provider == "anthropic", "FINASSIST_MODEL_PROVIDER must be anthropic for this checkpoint"
d = s.describe(); d["env_files_considered"] = [p.rsplit("/", 2)[-2] + "/" + p.rsplit("/", 1)[-1] for p in d["env_files_considered"]]
print(json.dumps(d, indent=1))
for m in (s.extraction_model, s.chat_model):
    print(verify_model_access(s.model_api_key.get_secret_value(), m))
PY
echo "== 2/4 smoke: 5 synthetic slips"
uv run python scripts/eval_extraction.py --slug haiku-smoke5 --limit 5 | tee var/smoke.json
echo "== smoke done. Review var/smoke.json; continuing only because the run exited 0."
echo "== 3/4 full synthetic set (40)"
uv run python scripts/eval_extraction.py --slug haiku-synth40 | tail -40
echo "== 4/4 agent demo (separate *_test database, synthetic users)"
export TEST_DATABASE_URL="$(uv run --with pixeltable-pgserver python scripts/local_pg.py)"
uv run --with pixeltable-pgserver python scripts/real_agent_demo.py --slug agent-sonnet | tail -60
echo "== done. Evidence in ../evidence/runs/ ; spend ledger in ../evidence/usage_ledger.jsonl"
