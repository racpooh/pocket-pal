# 20261015T120156Z-card-examples

Synthetic data, fixed clock, no model calls. Full cards: `cards.json`.

Note: the ฿250 food expense is timed 12:00, before the 13:00 balance entry, so it is already in the balance (FI-8):
it counts as Food spending but does not lower money left.

## Example 1: move all unspent Food to Shopping

- Move ฿3,750.00 of budget from Food to Shopping.
- Food: allocation 4,000.00 → 250.00; left 3,750.00 → 0.00
- Shopping: allocation 1,500.00 → 5,250.00; left 1,500.00 → 5,250.00
- warning: MOVES_ALL_REMAINING (high): Food would have nothing left to spend until your next income (฿3,750.00 unspent now).
- money left 10,000.00 → 10,000.00; buffer and commitments unchanged; goals: POCKET_MOVE_DOES_NOT_CHANGE_MONEY_LEFT

## Checks

- [x] food remaining is ฿3,750 after ฿250 spent
- [x] card warns MOVES_ALL_REMAINING (high)
- [x] source remaining after = 0
- [x] reload returns the identical card and hash
- [x] card_hash = sha256(canonical card)
- [x] ฿100 top-up has no warnings
- [x] edit → new id, old superseded
- [x] old approval cannot apply (409 PROPOSAL_NOT_PENDING)
- [x] goal card warns PLAN_EXCEEDS_MONEY_LEFT_AFTER
- [x] stale approval → 409 with recomputed replacement card
- [x] edited proposal is stale too after new spending (strict watermark)
