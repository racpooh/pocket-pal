"""Tests for the synthetic slip generator (no network)."""
from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import pytest

pytest.importorskip("PIL")
pytest.importorskip("qrcode")

MOD_PATH = Path(__file__).resolve().parents[2] / "tools" / "synth_slips.py"
spec = importlib.util.spec_from_file_location("synth_slips", MOD_PATH)
synth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(synth)


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory):
    a = tmp_path_factory.mktemp("a")
    b = tmp_path_factory.mktemp("b")
    synth.generate(a, 7, 40)
    synth.generate(b, 7, 40)
    return a, b


def _gt(d: Path) -> list[dict]:
    return [json.loads(x) for x in (d / "ground_truth.jsonl").read_text(encoding="utf-8").splitlines()]


def test_deterministic(two_runs):
    a, b = two_runs
    assert (a / "ground_truth.jsonl").read_bytes() == (b / "ground_truth.jsonl").read_bytes()
    for g in _gt(a):
        assert (a / g["file"]).read_bytes() == (b / g["file"]).read_bytes()


def test_different_seed_differs(tmp_path):
    synth.generate(tmp_path, 8, 40)
    other = (tmp_path / "ground_truth.jsonl").read_bytes()
    base = tmp_path / "base"
    synth.generate(base, 7, 40)
    assert other != (base / "ground_truth.jsonl").read_bytes()


def test_files_exist_and_shape(two_runs):
    a, _ = two_runs
    gts = _gt(a)
    assert len(gts) == 40
    for g in gts:
        assert (a / g["file"]).is_file()
        assert g["doc_type"] in {"transfer_out", "transfer_in", "receipt", "bill"}
        assert g["amount_satang"] is None or (isinstance(g["amount_satang"], int)
                                              and not isinstance(g["amount_satang"], bool))
        if g["doc_type"] == "bill":
            assert g["bill_due_date"]
        else:
            assert g.get("occurred_at", "").endswith("+07:00")


def test_exact_duplicate_is_byte_identical(two_runs):
    a, _ = two_runs
    dups = [(g["file"], t.split(":", 1)[1]) for g in _gt(a) for t in g["group_tags"]
            if t.startswith("exact_duplicate_of:")]
    assert dups
    for copy, orig in dups:
        assert copy != orig
        assert (a / copy).read_bytes() == (a / orig).read_bytes()


def test_near_duplicate_differs_but_same_truth(two_runs):
    a, _ = two_runs
    by = {g["file"]: g for g in _gt(a)}
    near = [(f, t.split(":", 1)[1]) for f, g in by.items() for t in g["group_tags"]
            if t.startswith("near_duplicate_of:")]
    assert near
    for f, orig in near:
        assert (a / f).read_bytes() != (a / orig).read_bytes()
        assert by[f]["amount_satang"] == by[orig]["amount_satang"]


def test_required_scenarios_present(two_runs):
    a, _ = two_runs
    gts = _gt(a)
    tags = {t.split(":")[0] for g in gts for t in g["group_tags"]}
    assert {"exact_duplicate_of", "near_duplicate_of", "same_purchase_as", "distinct_same_amount_as",
            "prompt_injection", "low_quality"} <= tags
    assert any(g["amount_satang"] is None for g in gts)
    assert {"pending", "failed"} <= {g["payment_status"] for g in gts}
    assert any(g["payee_display"] == "ร้านป้าสมาน" and g["amount_satang"] == 1000 for g in gts)
    assert any(g["payee_display"] == "AWN SPECIAL SHOP" and g["amount_satang"] == 12000 for g in gts)


def test_watermark_in_rendering_function():
    assert synth.WATERMARK_TEXT == "SYNTHETIC TEST DATA"
    assert "WATERMARK_TEXT" in inspect.getsource(synth.draw_watermark)
    assert "draw_watermark" in inspect.getsource(synth.render)


def test_watermark_changes_pixels():
    from PIL import Image

    blank = Image.new("RGB", (600, 200), "white")
    marked = synth.draw_watermark(blank.copy())
    assert marked.tobytes() != blank.tobytes()
