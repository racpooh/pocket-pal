"""Approval cards (02 FI-31..FI-33, 05 §Proposals).

A card says what a proposal would change, computed by deterministic code from the same data snapshot the
proposal is bound to (its data watermark). No model output is used for any number, warning or flag; the chat
model only ever sees the finished card as a tool result.

The card is stored with the proposal and bound to the approval by `card_hash`, so a reload shows exactly what
was computed and an approval can only apply what the user saw. Thresholds in POLICY are a provisional product
policy for the prototype, not a competition requirement.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

from finassist.api.errors import ApiError
from finassist.domain import cashflow as cf
from finassist.domain import goals as goals_d
from finassist.domain.allocation import reallocate
from finassist.domain.ledger import spending
from finassist.domain.money import format_thb
from finassist.domain.periods import NextIncomeDatePassed
from finassist.infra import canonical_json, sha256

CARD_SCHEMA = "approval-card@1"

POLICY = {
    "version": "card-policy@0.1",
    "status": "provisional product policy for the prototype; not a competition requirement; team to confirm",
    # LARGE_MOVE: a pocket loses at least half of what it still had unspent, or the move is at least a quarter of
    # all unspent pocket budget. Chosen so that routine top-ups (e.g. ฿100 from a ฿4,000 pocket) stay quiet.
    "large_move_min_share_of_pocket_remaining_bps": 5000,
    "large_move_min_share_of_all_unspent_bps": 2500,
    # POCKET_LOW_AFTER: what is left is under 10 % of the pocket's allocation before the change.
    "low_remaining_max_share_of_allocation_bps": 1000,
    # BALANCE_OBSERVATION_OLD: the balance anchor is older than this (projection may have drifted).
    "stale_balance_days": 3,
}


def card_hash(card: dict) -> bytes:
    return sha256(canonical_json(card))


def _thb(s: int) -> str:
    return "฿" + format_thb(s)


def _iso(d) -> str | None:
    return d.isoformat() if d is not None else None


def _warn(code: str, severity: str, text: str, **params) -> dict:
    return {"code": code, "severity": severity, "text": text, "params": params}


# ---------------- pockets ----------------

def _pocket_changes(conn, owner_id, period_start: date, period_end: date, before: dict[str, int], after: dict[str, int],
                    txns) -> tuple[list[dict], dict]:
    names = {str(r["id"]): r["name"] for r in conn.execute("select id,name from pocket where owner_id=%s", (owner_id,)).fetchall()}
    cmap = {r["category_code"]: str(r["pocket_id"]) for r in conn.execute(
        "select category_code,pocket_id from pocket_category_map where owner_id=%s", (owner_id,)).fetchall()}
    s = spending(txns, period_start, period_end)
    conf: dict[str, int] = {}
    pred: dict[str, int] = {}
    for code, v in s.by_category.items():
        pid = cmap.get(code)
        if pid:
            conf[pid] = conf.get(pid, 0) + v["confirmed"]
            pred[pid] = pred.get(pid, 0) + v["predicted"]
    unmapped = sum(v["confirmed"] + v["predicted"] for c, v in s.by_category.items() if c not in cmap)
    rows = []
    for pid in sorted(set(before) | set(after), key=lambda k: (names.get(k, ""), k)):
        b, a = before.get(pid, 0), after.get(pid, 0)
        if a == b:
            continue
        spent = conf.get(pid, 0) + pred.get(pid, 0)
        rows.append({"pocket_id": pid, "name": names.get(pid, "?"), "allocation_before_satang": b, "allocation_after_satang": a,
                     "delta_satang": a - b, "spent_confirmed_satang": conf.get(pid, 0), "spent_predicted_satang": pred.get(pid, 0),
                     "remaining_before_satang": b - spent, "remaining_after_satang": a - spent})
    unspent = lambda alloc: sum(max(0, amt - conf.get(p, 0) - pred.get(p, 0)) for p, amt in alloc.items())  # noqa: E731
    facts = {"unspent_before": unspent(before), "unspent_after": unspent(after), "unassigned": s.unassigned_satang + unmapped,
             "excluded": s.excluded_count}
    return rows, facts


def _pocket_warnings(rows: list[dict], unspent_before: int, *, moved: int | None = None) -> list[dict]:
    out = []
    for r in rows:
        rb, ra = r["remaining_before_satang"], r["remaining_after_satang"]
        if ra >= rb:
            continue
        if rb > 0 and ra <= 0:
            out.append(_warn("MOVES_ALL_REMAINING", "high", f"{r['name']} would have nothing left to spend until your next income "
                             f"({_thb(rb)} unspent now).", pocket=r["name"], pocket_id=r["pocket_id"], remaining_before_satang=rb))
            continue
        reduction = rb - ra if moved is None else moved
        if ra > 0 and ra * 10_000 < POLICY["low_remaining_max_share_of_allocation_bps"] * r["allocation_before_satang"]:
            out.append(_warn("POCKET_LOW_AFTER", "medium", f"{r['name']} would have only {_thb(ra)} left.",
                             pocket=r["name"], pocket_id=r["pocket_id"], remaining_after_satang=ra))
        big_local = rb > 0 and reduction * 10_000 >= POLICY["large_move_min_share_of_pocket_remaining_bps"] * rb
        big_total = unspent_before > 0 and reduction * 10_000 >= POLICY["large_move_min_share_of_all_unspent_bps"] * unspent_before
        if big_local or big_total:
            out.append(_warn("LARGE_MOVE", "medium", f"This takes {_thb(reduction)} of the {_thb(rb)} still unspent in {r['name']}.",
                             pocket=r["name"], pocket_id=r["pocket_id"], amount_satang=reduction, remaining_before_satang=rb))
    return out


# ---------------- money left / commitments ----------------

def _money(res: cf.CashflowResult | None) -> dict | None:
    if res is None:
        return None
    by = lambda k: sum(ln.amount_satang for ln in res.lines if ln.kind == k)  # noqa: E731
    return {"discretionary_satang": res.discretionary_satang, "shortage_satang": res.shortage_satang,
            "daily_allowance_satang": res.daily_allowance_satang, "bills_satang": by("bill"), "essentials_satang": by("essential"),
            "savings_satang": by("savings"), "buffer_satang": by("buffer"), "available_balance_satang": res.available_balance_satang}


def _effects(before: dict | None, after: dict | None) -> dict:
    if before is None or after is None:
        return {}
    keys = ("bills_satang", "essentials_satang", "savings_satang")
    return {
        "money_left": {"before_satang": before["discretionary_satang"], "after_satang": after["discretionary_satang"],
                       "daily_allowance_before_satang": before["daily_allowance_satang"],
                       "daily_allowance_after_satang": after["daily_allowance_satang"]},
        "buffer": {"before_satang": before["buffer_satang"], "after_satang": after["buffer_satang"]},
        "commitments": {"before": {k: before[k] for k in keys}, "after": {k: after[k] for k in keys},
                        "changed": any(before[k] != after[k] for k in keys)},
    }


# ---------------- builder ----------------

def build_card(conn, owner_id, kind: str, p: dict, *, payload_hash_hex: str, created_by: str, assumptions: list[dict],
               computed_at: datetime, edited_from: str | None = None, extra: dict | None = None) -> dict:
    from finassist.services import budget as b

    txns = b.load_txns(conn, owner_id)
    not_computed: list[dict] = []
    inp = ctx = None
    try:
        inp, ctx = b.cashflow_inputs(conn, owner_id, txns=txns)
        cf.compute(inp)
    except ApiError as e:
        inp = ctx = None
        not_computed.append({"item": "money_left", "reason_code": e.code})
    except NextIncomeDatePassed:
        inp = ctx = None
        not_computed.append({"item": "money_left", "reason_code": "NEXT_INCOME_DATE_PASSED"})

    def compute(**changes):
        return cf.compute(replace(inp, **changes)) if inp is not None else None

    warnings: list[dict] = []
    uncertainty: list[dict] = []
    card: dict = {"schema": CARD_SCHEMA, "policy": POLICY, "kind": kind, "payload_hash": "sha256:" + payload_hash_hex,
                  "computed_at": computed_at.isoformat(), "created_by": created_by, "edited_from": edited_from}
    facts: dict = {}

    if kind in ("reallocate", "budget_plan"):
        if kind == "reallocate":
            plan = conn.execute("select id,period_start,period_end,buffer_satang from budget_plan where owner_id=%s and id=%s",
                                (owner_id, p["plan_id"])).fetchone()
            before = {str(r["pocket_id"]): r["allocation_satang"] for r in conn.execute(
                "select pocket_id,allocation_satang from pocket_allocation where owner_id=%s and plan_id=%s", (owner_id, plan["id"])).fetchall()}
            after = reallocate(before, p["from_pocket"], p["to_pocket"], p["amount_satang"])
            ps, pe = plan["period_start"], plan["period_end"]
            buf_before = buf_after = plan["buffer_satang"]
        else:
            ps, pe = date.fromisoformat(str(p["period_start"])), date.fromisoformat(str(p["period_end"]))
            existing = conn.execute("select id,buffer_satang from budget_plan where owner_id=%s and period_start=%s", (owner_id, ps)).fetchone()
            before = {}
            if existing:
                before = {str(r["pocket_id"]): r["allocation_satang"] for r in conn.execute(
                    "select pocket_id,allocation_satang from pocket_allocation where owner_id=%s and plan_id=%s", (owner_id, existing["id"])).fetchall()}
            buf_before = existing["buffer_satang"] if existing else (ctx["plan"]["buffer_satang"] if ctx and ctx["plan"] else 0)
            buf_after = p["buffer_satang"]
            after = dict(p["allocations"])
            card["replaces_plan"] = existing is not None
        rows, facts = _pocket_changes(conn, owner_id, ps, pe, before, after, txns)
        card["period"] = {"start": _iso(ps), "end_exclusive": _iso(pe)}
        card["changes"] = rows
        m_before, m_after = _money(compute(buffer=cf.Buffer(amount_satang=buf_before))), _money(compute(buffer=cf.Buffer(amount_satang=buf_after)))
        card["effects"] = _effects(m_before, m_after)
        available = max(0, m_after["discretionary_satang"]) if m_after else None
        card["effects"]["unspent_budget"] = {"before_satang": facts["unspent_before"], "after_satang": facts["unspent_after"],
                                             "money_left_after_satang": available,
                                             "fits": None if available is None else facts["unspent_after"] <= available}
        if kind == "reallocate":
            names = {r["pocket_id"]: r for r in rows}
            src, dst = names[p["from_pocket"]], names[p["to_pocket"]]
            card["transfer"] = {"amount_satang": p["amount_satang"],
                                "from": {"pocket_id": src["pocket_id"], "name": src["name"], "remaining_before_satang": src["remaining_before_satang"],
                                         "remaining_after_satang": src["remaining_after_satang"]},
                                "to": {"pocket_id": dst["pocket_id"], "name": dst["name"], "remaining_before_satang": dst["remaining_before_satang"],
                                       "remaining_after_satang": dst["remaining_after_satang"]}}
            card["summary"] = {"code": "REALLOCATE", "text": f"Move {_thb(p['amount_satang'])} of budget from {src['name']} to {dst['name']}."}
            warnings += _pocket_warnings([src], facts["unspent_before"], moved=p["amount_satang"])
            card["effects"]["goals"] = {"changed": False, "reason_code": "POCKET_MOVE_DOES_NOT_CHANGE_MONEY_LEFT"}
        else:
            last_day = pe - timedelta(days=1)
            card["summary"] = {"code": "BUDGET_PLAN", "text": f"Set pocket budgets totalling {_thb(sum(after.values()))} "
                                                              f"for {ps.isoformat()} to {last_day.isoformat()}."}
            warnings += _pocket_warnings(rows, facts["unspent_before"])
            if buf_after < buf_before:
                warnings.append(_warn("BUFFER_REDUCED", "medium", f"Safety buffer goes from {_thb(buf_before)} to {_thb(buf_after)}.",
                                      before_satang=buf_before, after_satang=buf_after))
            card["effects"]["goals"] = _goal_effects(conn, owner_id, ctx, m_before, m_after, warnings)
        predicted = sum(r["spent_predicted_satang"] for r in rows)
        if predicted:
            uncertainty.append({"code": "PREDICTED_CATEGORY_SPENDING", "text": f"{_thb(predicted)} of spending in these pockets has a "
                                "guessed category; remaining amounts change if you correct it.", "params": {"satang": predicted}})
    elif kind in ("goal_create", "goal_update"):
        warnings, uncertainty, facts = _goal_card(conn, owner_id, p, card, ctx, inp, compute, txns)
    else:
        raise ApiError(400, "VALIDATION_FAILED", "Unknown kind.")

    ml = card.get("effects", {}).get("money_left")
    if ml and ml["after_satang"] < 0 <= ml["before_satang"]:
        warnings.append(_warn("CAUSES_SHORTAGE", "high", f"You would be {_thb(-ml['after_satang'])} short before your next income.",
                              shortage_satang=-ml["after_satang"]))
    if facts.get("unassigned"):
        uncertainty.append({"code": "UNASSIGNED_SPENDING", "text": f"{_thb(facts['unassigned'])} of spending this period has no pocket yet; "
                            "some of it may belong to a pocket shown here.", "params": {"satang": facts["unassigned"]}})
    if facts.get("excluded"):
        uncertainty.append({"code": "EXCLUDED_UNRESOLVED", "text": f"{facts['excluded']} record(s) are pending or have an unclear amount "
                            "and are not counted.", "params": {"count": facts["excluded"]}})
    open_reviews = conn.execute("select count(*) n from review_item where owner_id=%s and status='open'", (owner_id,)).fetchone()["n"]
    if open_reviews:
        uncertainty.append({"code": "OPEN_REVIEW_ITEMS", "text": f"{open_reviews} imported item(s) wait for your review and are not counted yet.",
                            "params": {"count": open_reviews}})
    if ctx:
        oldest = min(a["as_of"] for a in ctx["accounts"])
        card["balance_as_of"] = oldest.isoformat()
        if computed_at - oldest > timedelta(days=POLICY["stale_balance_days"]):
            uncertainty.append({"code": "BALANCE_OBSERVATION_OLD", "text": f"Your balance was last entered on {oldest.date().isoformat()}; "
                                "money left is a projection from that.", "params": {"as_of": oldest.isoformat()}})
        card["days_until_income"] = (inp.next_income_date - inp.today).days
    if created_by == "agent":
        warnings.append(_warn("SUGGESTED_BY_ASSISTANT", "info", "Suggested by the assistant. Nothing changes until you approve."))
    order = {"high": 0, "medium": 1, "info": 2}
    card["warnings"] = sorted(warnings, key=lambda w: order[w["severity"]])
    card["uncertainty"] = uncertainty
    card["assumptions"] = assumptions
    card["not_computed"] = not_computed
    if extra:
        card["extra"] = extra
    return card


def _goal_effects(conn, owner_id, ctx, m_before, m_after, warnings: list[dict]) -> dict:
    if not ctx or not m_before or not m_after:
        return {"changed": None, "reason_code": "MONEY_LEFT_NOT_COMPUTED"}
    if m_before["discretionary_satang"] == m_after["discretionary_satang"]:
        return {"changed": False, "reason_code": "MONEY_LEFT_UNCHANGED"}
    inc = ctx["income"]
    out = []
    for g in conn.execute("select id,name,target_satang,saved_satang,deadline from goal where owner_id=%s and status='active' order by deadline",
                          (owner_id,)).fetchall():
        f = [goals_d.feasibility(g["target_satang"], g["saved_satang"], g["deadline"], inc["next_income_date"], inc["frequency"],
                                 max(0, m["discretionary_satang"])) for m in (m_before, m_after)]
        out.append({"goal_id": str(g["id"]), "name": g["name"], "feasible_before": f[0].feasible, "feasible_after": f[1].feasible})
        if f[0].feasible and not f[1].feasible:
            warnings.append(_warn("GOAL_BECOMES_INFEASIBLE", "medium", f"Goal '{g['name']}' would no longer be reachable by its deadline "
                                  "at the money left after this change.", goal_id=str(g["id"])))
    return {"changed": True, "basis": "capacity per income event = money left after commitments", "goals": out}


def _goal_card(conn, owner_id, p: dict, card: dict, ctx, inp, compute, txns) -> tuple[list[dict], list[dict], dict]:
    warnings: list[dict] = []
    if card["kind"] == "goal_update":
        g = conn.execute("select id,name,target_satang,saved_satang,deadline,contribution_satang_per_period,status from goal "
                         "where owner_id=%s and id=%s", (owner_id, p["goal_id"])).fetchone()
        before = {"target_satang": g["target_satang"], "deadline": _iso(g["deadline"]),
                  "contribution_satang_per_period": g["contribution_satang_per_period"]}
        after = {k: (p[k] if p.get(k) is not None else before[k]) for k in before}
        name, saved, source = g["name"], g["saved_satang"], f"goal:{g['id']}"
        card["summary"] = {"code": "GOAL_UPDATE", "text": f"Update goal '{name}'."}
    else:
        before = None
        after = {"target_satang": p["target_satang"], "deadline": p["deadline"], "contribution_satang_per_period": p["contribution_satang_per_period"]}
        name, saved, source = p["name"], p["saved_satang"], "goal:new"
        card["summary"] = {"code": "GOAL_CREATE", "text": f"Create goal '{name}': save {_thb(p['target_satang'])} by {p['deadline']}."}
    card["changes"] = [{"field": k, "before": before[k] if before else None, "after": after[k]}
                       for k in after if before is None or before[k] != after[k]]
    card["goal"] = {"name": name, "saved_satang": saved}
    facts: dict = {}
    if inp is None:
        card["effects"] = {}
        return warnings, [], facts
    sav = [sc for sc in inp.savings if sc.source_id != source]
    if after["contribution_satang_per_period"] > 0:
        sav.append(cf.SavingsCommitment(source, after["contribution_satang_per_period"]))
    m_before, m_after = _money(compute()), _money(compute(savings=tuple(sav)))
    card["effects"] = _effects(m_before, m_after)
    f = goals_d.feasibility(after["target_satang"], saved, date.fromisoformat(after["deadline"]), inp.next_income_date,
                            ctx["income"]["frequency"], after["contribution_satang_per_period"])
    card["effects"]["this_goal"] = {"contribution_events_until_deadline": f.contribution_events,
                                    "required_per_event_satang": f.required_per_event_satang,
                                    "contribution_per_event_satang": after["contribution_satang_per_period"],
                                    "contribution_covers_required": f.feasible}
    if not f.feasible:
        warnings.append(_warn("GOAL_CONTRIBUTION_BELOW_REQUIRED", "medium",
                              f"{_thb(after['contribution_satang_per_period'])} per income is not enough; {_thb(f.required_per_event_satang)} is needed "
                              f"to reach the target by {after['deadline']}.", required_per_event_satang=f.required_per_event_satang))
    plan = ctx["plan"]
    if plan:
        alloc = {str(r["pocket_id"]): r["allocation_satang"] for r in conn.execute(
            "select pocket_id,allocation_satang from pocket_allocation where owner_id=%s and plan_id=%s", (owner_id, plan["id"])).fetchall()}
        _, facts = _pocket_changes(conn, owner_id, plan["period_start"], plan["period_end"], alloc, alloc, txns)
        unspent = facts["unspent_after"]
        avail = max(0, m_after["discretionary_satang"])
        card["effects"]["unspent_budget"] = {"before_satang": unspent, "after_satang": unspent, "money_left_after_satang": avail,
                                             "fits": unspent <= avail}
        if unspent > avail:
            warnings.append(_warn("PLAN_EXCEEDS_MONEY_LEFT_AFTER", "high", f"Your pocket budgets ({_thb(unspent)} unspent) would exceed the "
                                  f"{_thb(avail)} left after this saving. Reduce pockets after approving.",
                                  unspent_satang=unspent, money_left_satang=avail))
    return warnings, [], facts
