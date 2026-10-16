"""UsageMeter ledger accounting (Codex finding, 16 Oct 2026): unknown cost never becomes $0; corrections never double count."""
import json

import pytest

from finassist.providers import BudgetExceeded, UsageMeter, ledger_cost

M = "claude-haiku-5-5"  # priced in PRICES_PER_MTOK


def _write(tmp_path, entries):
    p = tmp_path / "ledger.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return str(p)


def test_null_cost_is_computed_from_tokens_when_the_model_is_priced():
    total, unknown = ledger_cost([{"run_id": "a", "model": M, "input_tokens": 1_000_000, "output_tokens": 0, "cost_usd": None}])
    assert unknown == [] and total == pytest.approx(0.10)


@pytest.mark.parametrize("entry", [
    {"run_id": "a", "model": "some-unpriced-model", "input_tokens": 10, "output_tokens": 10, "cost_usd": None},
    {"run_id": "a", "model": M, "cost_usd": None},                      # no token counts
    {"run_id": "a", "model": M, "input_tokens": "?", "output_tokens": 1},  # malformed tokens
    {"run_id": "a", "cost_usd": None},                                   # no model
])
def test_uncomputable_null_cost_is_unknown_not_zero(entry):
    total, unknown = ledger_cost([entry])
    assert total == 0.0 and unknown == [entry]


def test_meter_refuses_paid_calls_while_a_cost_is_unknown(tmp_path):
    m = UsageMeter(budget_usd=10.0, max_requests=5, ledger_path=_write(tmp_path, [{"run_id": "x", "model": "unpriced", "cost_usd": None}]))
    with pytest.raises(BudgetExceeded, match="unknown cost"):
        m.check(M, 1000, 100)
    assert m.summary()["prior_unknown_cost_entries"] == 1


def test_correction_replaces_the_run_and_is_not_counted_twice():
    entries = [
        {"run_id": "r1", "model": M, "input_tokens": 11343, "output_tokens": 1499, "cost_usd": None},  # would compute ≈0.00188
        {"run_id": "r1", "corrects_run_id": "r1", "cost_usd": 0.001884, "input_tokens": 0, "output_tokens": 0},
        {"run_id": "other", "model": M, "cost_usd": 0.0003},
    ]
    total, unknown = ledger_cost(entries)
    assert unknown == [] and total == pytest.approx(0.001884 + 0.0003)


def test_latest_correction_wins_and_legacy_text_correction_is_recognised():
    entries = [
        {"run_id": "r1", "model": M, "input_tokens": 5, "output_tokens": 5, "cost_usd": 0.5},
        {"run_id": "r1", "purpose": "CORRECTION of the line above: …", "cost_usd": 0.2},  # legacy form (16 Oct)
        {"run_id": "r1", "corrects_run_id": "r1", "cost_usd": 0.3},
    ]
    assert ledger_cost(entries) == (pytest.approx(0.3), [])


def test_correction_with_unknown_cost_is_unknown():
    entries = [{"run_id": "r1", "model": M, "cost_usd": 0.1}, {"corrects_run_id": "r1", "cost_usd": None}]
    total, unknown = ledger_cost(entries)
    assert total == 0.0 and len(unknown) == 1


def test_real_repo_ledger_has_no_unknown_cost_and_no_double_count():
    from pathlib import Path

    p = Path(__file__).resolve().parents[3] / "evidence" / "usage_ledger.jsonl"
    entries = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    total, unknown = ledger_cost(entries)
    assert unknown == []
    naive_with_r1_twice = sum(e.get("cost_usd") or 0 for e in entries) + 0.001884
    assert total < naive_with_r1_twice
