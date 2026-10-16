"""Synthetic REVIEW VARIANTS for UI slice 1 (Codex review finding 1). Derived from synthetic slips only.

Each variant is a copy of a synthetic slip with a visible "TEST VARIANT" strip (so the bytes and SHA-256 differ) and
fake-extractor fields that leave out exactly one thing the user must supply in review. dev_server.py --provider fake
registers them next to the regular fixtures. Deterministic: re-running produces the same files.

  python3 make_variants.py   (needs Pillow)
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SLIPS = HERE.parent / "slips"

VARIANTS = [
    # bill whose due date was not read: the user enters it → a bill is created (never an expense)
    {"file": "var_bill_no_due_date.png", "base": "slip_030_bill.png",
     "fields": {"doc_type": "bill", "amount_text": "3,600.00", "date_text": "2026-10-01", "time_text": None, "status": None,
                "payee": "Synthetic Power Co (variant)", "bank_ref": None, "due_date_text": None, "readability": "clear"}},
    # transfer whose status was not readable: the user picks it → the ledger follows the choice
    {"file": "var_slip_status_unknown_a.png", "base": "slip_005_transfer_out.png",
     "fields": {"doc_type": "transfer_out", "amount_text": "899.00", "date_text": "2026-08-22", "time_text": "20:55", "status": "unknown",
                "payee": "Variant Shop A", "bank_ref": "VAR-A-0001", "due_date_text": None, "readability": "clear"}},
    {"file": "var_slip_status_unknown_b.png", "base": "slip_006_transfer_out.png",
     "fields": {"doc_type": "transfer_out", "amount_text": "350.00", "date_text": "2026-09-30", "time_text": "19:53", "status": "unknown",
                "payee": "Variant Shop B", "bank_ref": "VAR-B-0002", "due_date_text": None, "readability": "clear"}},
]


def main() -> None:
    for v in VARIANTS:
        with Image.open(SLIPS / v["base"]) as im:
            im = im.convert("RGB")
            d = ImageDraw.Draw(im)
            d.rectangle((0, 0, im.width, 28), fill=(255, 220, 0))
            d.text((8, 8), f"TEST VARIANT - {v['file']}", fill=(0, 0, 0))
            im.save(HERE / v["file"], format="PNG", optimize=False)
    (HERE / "variants.jsonl").write_text("\n".join(json.dumps({"file": v["file"], "base": v["base"], "fields": v["fields"]}) for v in VARIANTS) + "\n")


if __name__ == "__main__":
    main()
