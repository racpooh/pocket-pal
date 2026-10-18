"""HTTP routes (docs/design/05). Thin: parse → service → JSON. owner_id only from the session."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from finassist.api.errors import ApiError
from finassist.infra import idempotent
from finassist.services import agent, budget, core, imports

router = APIRouter(prefix="/v1")


def _conn(request: Request):
    with request.app.state.db.connect() as conn:
        yield conn


def _token(authorization: str | None = Header(default=None)) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def owner(conn=Depends(_conn), token: str | None = Depends(_token)):
    return core.owner_from_token(conn, token)


def _out(code: int, body) -> JSONResponse:
    from fastapi.encoders import jsonable_encoder

    return JSONResponse(status_code=code, content=jsonable_encoder(body, custom_encoder={bytes: lambda b: b.hex()}))


IdemKey = Header(default=None, alias="Idempotency-Key")


# ---------- auth ----------
class Creds(BaseModel):
    model_config = {"extra": "forbid"}
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=256)


@router.post("/auth/signup")
def signup(body: Creds, conn=Depends(_conn)):
    return _out(201, core.signup(conn, body.email, body.password))


@router.post("/auth/login")
def login(body: Creds, conn=Depends(_conn)):
    return _out(200, core.login(conn, body.email, body.password))


@router.post("/auth/logout")
def logout(conn=Depends(_conn), token: str | None = Depends(_token), _o=Depends(owner)):
    core.logout(conn, token)
    return Response(status_code=204)


# ---------- profile / accounts ----------
class EssentialIn(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(max_length=80)
    amount_satang: int = Field(gt=0)
    due_day: int = Field(ge=1, le=31)


class ProfileIn(BaseModel):
    model_config = {"extra": "forbid"}
    income_satang: int = Field(gt=0)
    income_frequency: Literal["monthly", "biweekly", "weekly", "irregular"]
    next_income_date: date
    timezone: str = "Asia/Bangkok"
    essentials: list[EssentialIn] = []


@router.get("/me")
def me(o=Depends(owner)):
    # Lets the client bind its local upload queue to the signed-in account (CP3a review #1). No e-mail returned.
    return _out(200, {"user_id": str(o)})


@router.get("/me/profile")
def get_profile(o=Depends(owner), conn=Depends(_conn)):
    return _out(200, core.get_profile(conn, o))


@router.put("/me/profile")
def put_profile(body: ProfileIn, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, core.put_profile(conn, o, body.model_dump()))


@router.get("/accounts")
def accounts(o=Depends(owner), conn=Depends(_conn)):
    return _out(200, core.list_accounts(conn, o))


class BalanceIn(BaseModel):
    model_config = {"extra": "forbid"}
    amount_satang: int
    as_of: datetime | None = None
    as_of_date: date | None = None


@router.post("/accounts/{account_id}/balance-observations")
def balance(account_id: str, body: BalanceIn, o=Depends(owner), conn=Depends(_conn)):
    return _out(201, core.add_balance_observation(conn, o, _uuid(account_id), body.amount_satang, body.as_of, body.as_of_date))


# ---------- consent ----------
class ConsentIn(BaseModel):
    model_config = {"extra": "forbid"}
    scope: Literal["photo_processing", "auto_import", "chat_history_retention"]
    version: str = Field(max_length=40)
    params: dict = {}


@router.get("/consents")
def consents(o=Depends(owner), conn=Depends(_conn)):
    return _out(200, core.list_consents(conn, o))


@router.post("/consents")
def grant(body: ConsentIn, o=Depends(owner), conn=Depends(_conn)):
    return _out(201, core.grant_consent(conn, o, body.scope, body.version, body.params))


@router.delete("/consents/{scope}")
def revoke(scope: str, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, core.revoke_consent(conn, o, scope))


# ---------- transactions ----------
class TxnIn(BaseModel):
    model_config = {"extra": "forbid"}
    kind: Literal["expense", "income", "refund", "transfer_out", "transfer_in"]
    amount_satang: int = Field(gt=0)
    occurred_date: date
    occurred_at: datetime | None = None
    payee: str | None = Field(default=None, max_length=120)
    category: str | None = None
    description: str | None = Field(default=None, max_length=200)
    refund_of: str | None = None
    account_id: str | None = None
    confirm_distinct: bool = False


@router.get("/transactions")
def txns(o=Depends(owner), conn=Depends(_conn), start: date | None = Query(None, alias="from"), end: date | None = Query(None, alias="to"),
         category: str | None = None, state: str | None = None):
    return _out(200, core.list_txns(conn, o, start, end, category, state))


@router.post("/transactions")
def create_txn(body: TxnIn, o=Depends(owner), conn=Depends(_conn), key: str | None = IdemKey):
    d = body.model_dump()
    for k in ("refund_of", "account_id"):
        if d[k]:
            d[k] = _uuid(d[k])
    code, resp = idempotent(conn, o, key, "POST /transactions", body.model_dump(mode="json"), lambda c: core.create_manual_txn(c, o, d))
    return _out(code, resp)


class TxnPatch(BaseModel):
    model_config = {"extra": "forbid"}
    version: int
    changes: dict


@router.patch("/transactions/{txn_id}")
def patch_txn(txn_id: str, body: TxnPatch, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, core.patch_txn(conn, o, _uuid(txn_id), body.version, body.changes))


@router.delete("/transactions/{txn_id}")
def delete_txn(txn_id: str, o=Depends(owner), conn=Depends(_conn)):
    core.delete_txn(conn, o, _uuid(txn_id))
    return Response(status_code=204)


class CategoryIn(BaseModel):
    model_config = {"extra": "forbid"}
    category: str
    set_payee_default: bool = False


@router.post("/transactions/{txn_id}/category")
def set_cat(txn_id: str, body: CategoryIn, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, core.set_category(conn, o, _uuid(txn_id), body.category, body.set_payee_default))


# ---------- bills ----------
class BillIn(BaseModel):
    model_config = {"extra": "forbid"}
    biller: str = Field(max_length=120)
    amount_due_satang: int = Field(gt=0)
    due_date: date
    essential_expense_id: str | None = None


@router.get("/bills")
def bills(o=Depends(owner), conn=Depends(_conn), status: str | None = None):
    return _out(200, core.list_bills(conn, o, status))


@router.post("/bills")
def create_bill(body: BillIn, o=Depends(owner), conn=Depends(_conn)):
    d = body.model_dump()
    if d["essential_expense_id"]:
        d["essential_expense_id"] = _uuid(d["essential_expense_id"])
    with conn.transaction():
        return _out(201, core.create_bill(conn, o, d))


class LinkIn(BaseModel):
    model_config = {"extra": "forbid"}
    txn_id: str


@router.post("/bills/{bill_id}/link-payment")
def link(bill_id: str, body: LinkIn, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, core.link_bill_payment(conn, o, _uuid(bill_id), _uuid(body.txn_id)))


# ---------- pockets / plan / simulate ----------
class PocketIn(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=40)
    categories: list[str] = []


@router.get("/pockets")
def pockets(o=Depends(owner), conn=Depends(_conn)):
    return _out(200, budget.list_pockets(conn, o))


@router.post("/pockets")
def pocket(body: PocketIn, o=Depends(owner), conn=Depends(_conn)):
    return _out(201, budget.create_pocket(conn, o, body.name, body.categories))


@router.get("/plan")
def plan(o=Depends(owner), conn=Depends(_conn)):
    return _out(200, budget.get_plan(conn, o))


@router.post("/plan/suggest")
def suggest(o=Depends(owner), conn=Depends(_conn), buffer_satang: int = Query(0, ge=0)):
    return _out(201, budget.suggest_budget_plan(conn, o, buffer_satang))


@router.get("/insights")
def insights(o=Depends(owner), conn=Depends(_conn)):
    return _out(200, budget.insights(conn, o))


@router.get("/spending")
def spending_report(o=Depends(owner), conn=Depends(_conn), start: date = Query(..., alias="from"), end: date = Query(..., alias="to")):
    return _out(200, budget.spending_report(conn, o, start, end))


class TradeoffIn(BaseModel):
    model_config = {"extra": "forbid"}
    pocket_id: str
    increase_satang: int = Field(gt=0)


@router.post("/plan/tradeoff")
def tradeoff(body: TradeoffIn, o=Depends(owner), conn=Depends(_conn)):
    return _out(201, budget.propose_tradeoff(conn, o, body.pocket_id, body.increase_satang))


class SimIn(BaseModel):
    model_config = {"extra": "forbid"}
    amount_satang: int = Field(gt=0)


@router.post("/simulate/affordability")
def simulate(body: SimIn, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, budget.affordability(conn, o, body.amount_satang))


class GoalCheck(BaseModel):
    model_config = {"extra": "forbid"}
    target_satang: int = Field(gt=0)
    saved_satang: int = Field(ge=0, default=0)
    deadline: date


@router.post("/goals/feasibility")
def goal_check(body: GoalCheck, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, budget.goal_feasibility(conn, o, body.target_satang, body.saved_satang, body.deadline))


@router.get("/goals")
def goals(o=Depends(owner), conn=Depends(_conn)):
    return _out(200, conn.execute("select * from goal where owner_id=%s order by deadline", (o,)).fetchall())


# ---------- proposals ----------
class ProposalIn(BaseModel):
    model_config = {"extra": "forbid"}
    kind: Literal["budget_plan", "reallocate", "goal_create", "goal_update"]
    payload: dict


@router.post("/proposals")
def propose(body: ProposalIn, o=Depends(owner), conn=Depends(_conn)):
    return _out(201, budget.create_proposal(conn, o, body.kind, body.payload, "user"))


@router.get("/proposals")
def list_props(o=Depends(owner), conn=Depends(_conn), status: Literal["pending", "applied", "stale", "superseded", "cancelled", "expired"] | None = None,
               limit: int = Query(20, ge=1, le=100)):
    return _out(200, budget.list_proposals(conn, o, status, limit))


@router.get("/proposals/{pid}")
def get_prop(pid: str, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, budget.get_proposal(conn, o, _uuid(pid)))


class ApproveIn(BaseModel):
    model_config = {"extra": "forbid"}
    payload_hash: str = Field(max_length=80)
    card_hash: str = Field(max_length=80)  # binds the approval to the card the user saw (FI-32)


@router.post("/proposals/{pid}/approve")
def approve(pid: str, body: ApproveIn, o=Depends(owner), conn=Depends(_conn), key: str | None = IdemKey):
    p = _uuid(pid)
    code, resp = idempotent(conn, o, key, f"POST /proposals/{p}/approve", body.model_dump(),
                            lambda c: budget.approve(c, o, p, body.payload_hash, body.card_hash))
    return _out(code, resp)


class EditIn(BaseModel):
    model_config = {"extra": "forbid"}
    payload_hash: str = Field(max_length=80)  # of the proposal being edited
    payload: dict


@router.post("/proposals/{pid}/edit")
def edit(pid: str, body: EditIn, o=Depends(owner), conn=Depends(_conn)):
    code, resp = budget.edit_proposal(conn, o, _uuid(pid), body.payload_hash, body.payload)
    return _out(code, resp)


@router.post("/proposals/{pid}/cancel")
def cancel(pid: str, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, budget.cancel(conn, o, _uuid(pid)))


# ---------- uploads / review ----------
@router.post("/uploads")
async def upload(request: Request, image: UploadFile = File(...), captured_at: datetime | None = Form(None),
                 confirmed_undated: bool = Form(False), expected_owner_id: str | None = Form(None),
                 o=Depends(owner), conn=Depends(_conn)):
    max_b = request.app.state.settings.max_upload_bytes
    data = await image.read(max_b + 1)
    code, body = imports.create_upload(conn, request.app.state.storage, o, data, captured_at, max_b,
                                       confirmed_undated=confirmed_undated, expected_owner_id=expected_owner_id)
    return _out(code, body)


@router.get("/uploads")
def uploads(o=Depends(owner), conn=Depends(_conn), status: str | None = None):
    return _out(200, imports.list_uploads(conn, o, status))


@router.get("/uploads/{uid}")
def get_upload(uid: str, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, imports.get_upload(conn, o, _uuid(uid)))


@router.post("/uploads/{uid}/retry")
def retry_upload(uid: str, o=Depends(owner), conn=Depends(_conn)):
    return _out(202, imports.retry_upload(conn, o, _uuid(uid)))


@router.get("/uploads/{uid}/image")
def get_image(uid: str, request: Request, o=Depends(owner), conn=Depends(_conn)):
    data, mime = imports.read_image(conn, request.app.state.storage, o, _uuid(uid))
    return Response(content=data, media_type=mime, headers={"Cache-Control": "private, no-store"})


@router.delete("/uploads/{uid}")
def del_upload(uid: str, request: Request, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, imports.delete_upload(conn, request.app.state.storage, o, _uuid(uid)))


@router.get("/scan-status")
def scan_status(o=Depends(owner), conn=Depends(_conn)):
    return _out(200, imports.scan_status(conn, o))


@router.get("/review-items")
def review(o=Depends(owner), conn=Depends(_conn)):
    return _out(200, {"items": imports.list_review(conn, o), "uncategorised_payees": imports.uncategorised_groups(conn, o)})


class ResolveIn(BaseModel):
    model_config = {"extra": "forbid"}
    decision: Literal["accept", "not_a_transaction", "duplicate_of", "link_receipt", "distinct"]
    fields: dict | None = None
    txn_id: str | None = None


@router.post("/review-items/{rid}/resolve")
def resolve(rid: str, body: ResolveIn, o=Depends(owner), conn=Depends(_conn)):
    d = body.model_dump()
    if d["txn_id"]:
        d["txn_id"] = _uuid(d["txn_id"])
    return _out(200, imports.resolve_review(conn, o, _uuid(rid), d))


class BatchCat(BaseModel):
    model_config = {"extra": "forbid"}
    payee_key: str
    category: str
    set_default: bool = False


@router.post("/review-items/batch-categorise")
def batch(body: BatchCat, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, imports.batch_categorise(conn, o, body.payee_key, body.category, body.set_default))


class DeleteData(BaseModel):
    model_config = {"extra": "forbid"}
    scope: Literal["imported"]


@router.post("/data/delete")
def delete_data(body: DeleteData, request: Request, o=Depends(owner), conn=Depends(_conn)):
    return _out(200, imports.delete_all_imported(conn, request.app.state.storage, o))


@router.get("/audit")
def audit_log(o=Depends(owner), conn=Depends(_conn), limit: int = Query(50, le=200)):
    return _out(200, conn.execute("select actor,action,subject_type,subject_id,result,details,at from audit_event where owner_id=%s order by id desc limit %s", (o, limit)).fetchall())


# ---------- chat ----------
class ChatIn(BaseModel):
    model_config = {"extra": "forbid"}
    text: str = Field(min_length=1, max_length=2000)


@router.get("/chat/messages")
def chat_history(o=Depends(owner), conn=Depends(_conn)):
    return _out(200, agent.history(conn, o))


@router.delete("/chat/messages")
def delete_chat_history(o=Depends(owner), conn=Depends(_conn)):
    return _out(200, agent.clear_history(conn, o))


@router.post("/chat/messages")
def chat(body: ChatIn, request: Request, o=Depends(owner), conn=Depends(_conn)):
    model = request.app.state.chat_model
    if model is None:
        raise ApiError(503, "MODEL_UNAVAILABLE", "The assistant is not configured.", retryable=True)
    return _out(200, agent.chat(conn, o, body.text, model))


def _uuid(s: str):
    import uuid

    try:
        return uuid.UUID(str(s))
    except ValueError:
        raise ApiError(404, "NOT_FOUND", "Not found.") from None
