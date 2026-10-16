# 13 — pocket-pal → Android integration mapping (for Codex review; nothing implemented)

Status 16 Oct 2026: study only. Sources read: `pocket-pal/` (Next.js 15 prototype: `CONTEXT.md`,
`design-system/pocket-pal/MASTER.md`, `web/src/**`, all data from `lib/demo-data.ts`) and shenzen backend
(`api/routes.py`, `services/*`, `05`) and Android (`core/`, `app/`). Response shapes below are not quoted from the
docs: they come from a real synthetic session (fake extraction, cloud test DB, scratch test not committed).

## 0. Summary

- pocket-pal is a design and interaction prototype. **Every number, state change and save is local demo state.**
  Approval is a `setTimeout(1200)`, saves are `useState`, and the review sheet always "reads" the same demo bill.
- Most screens have a matching backend API. The main differences are in meaning and units:
  - pocket-pal works in whole baht; the backend works in satang.
  - pocket-pal has fixed pocket kinds with Savings and Bills pockets; the backend has user-named pockets mapped to
    category codes.
  - Several pocket-pal features have no backend: Undo, "spent today", "mark bill paid" without a transaction, CSV
    import, "delete all data", and equal-period insight comparison.
- **Proposal: build the UI natively in Compose**, using pocket-pal as the visual and interaction specification.
  Keep the reviewed `core` (ApiClient, SessionGate, UploadQueue, Keystore token) unchanged. A web shell is not
  recommended (§3).
- **First vertical slice:** sign in → consent → upload → review → activity, using real backend data (§4).

## 1. Screen and action → API mapping

Legend: ✅ supported as is · 🟡 supported with a mapping or a small gap · ❌ not supported (demo only) · ⚠ the
prototype conflicts with a rule.

### 1.1 Onboarding (`/welcome`)

| pocket-pal | API | Status / gap |
|---|---|---|
| "Try it with demo data" | — | ❌ demo. In the app, only for a test account on a `test_mode` server, and labelled. |
| Step: balance + as-of date | `POST /accounts/{id}/balance-observations {amount_satang, as_of}` | ✅ |
| Step: income (confirmed vs not sure) | `PUT /me/profile {income_satang, income_frequency, next_income_date}` | 🟡 There is no "not sure" state; unconfirmed income must not be stored as income. |
| Step: bills and essentials | `PUT /me/profile essentials[]`, `POST /bills` | ✅ |
| Step: goal + buffer | goal via `POST /proposals kind=goal_create` (approval); buffer via `POST /plan/suggest?buffer_satang=` (proposal) | 🟡 Two approval cards, not a direct save. |
| "First look" estimate | `GET /plan` → `cashflow.discretionary_satang`, `daily_allowance_satang` | ✅ |
| "Import a bank CSV" | — | ❌ The prototype already says "coming soon"; keep it that way. |
| Account creation / sign in | `POST /auth/signup`, `/auth/login`, `GET /me` → SessionGate | ✅ pocket-pal has no auth screen at all; the existing Android sign-in stays. |

### 1.2 Pockets tab

| pocket-pal | API | Status / gap |
|---|---|---|
| Greeting name | — | 🟡 The backend has no display name; use the email local part, or drop the name. |
| Balance (Hide/Show) | `GET /plan` → `accounts[].projected_satang`, `as_of` | ✅ Must show the "as of" date. |
| Safe to spend + "a day until Nov 1" | `cashflow.discretionary_satang`, `daily_allowance_satang`, `days`; `profile.income.next_income_date` | ✅ |
| Gauge "spent today / daily" | — | 🟡 No "spent today" field. Either sum today's confirmed expenses on the client (integer satang, label "recorded today") or add a field to `/plan`; Codex to choose. |
| "On track" pill | `GET /insights` → `pace_alerts[]` | 🟡 Only a negative signal exists ("over" or "on pace to exceed"); "On track" = no alert. |
| Pocket grid: budget / spent / left / over | `GET /plan` → `pockets[]` (`allocation_satang`, `spent_confirmed_satang`, `spent_predicted_satang`, `remaining_satang`, `overspent`) | 🟡 Predicted spending must be shown separately ("incl. ฿X guessed"). The `(unassigned)` row must be shown. |
| Pocket kinds and icons (Food, Shopping, Transport, Leisure, Bills, Savings) | `GET /pockets` → `{name, categories[]}` | 🟡 Backend pockets are user-named: by default Food, Shopping, Transport, Entertainment, Other (with bills). Pick the icon from the category, not the name. There are no Savings or Bills pockets. |
| Savings pocket "Saved ฿3,500" | `GET /goals` → `saved_satang` | 🟡 Shown from the goal; not a pocket. |
| "Protected" lock | — | ❌ No protected flag. Bills and essentials are reserved in `cashflow.lines`; show "reserved", not "protected". |
| "Every baht has a pocket" / unallocated | `card.effects.unspent_budget` / `plan` | 🟡 Compute from plan allocations vs `discretionary_satang` server-side; do not compute on the client. |
| Upload slip / Ask Pal buttons | Upload screen / Chat | ✅ / see Chat |

### 1.3 Chat tab

| pocket-pal | API | Status / gap |
|---|---|---|
| Messages | `POST /chat/messages {text}` → `{reply, cards[]}` | 🟡 Exists, but `dev_server.py` has no chat model → `503 MODEL_UNAVAILABLE`. The scripted chat flag is CP3b (`11` §5). No paid model. |
| Status line ("Checked your October budget") | — | ❌ Not returned. It could be built from the tool names the agent used, if the response exposed them. Gap. |
| Quick prompts | client constants | ✅ |
| **Action card: Approve** | `POST /proposals/{id}/approve {payload_hash, card_hash}` + `Idempotency-Key` | ✅ ⚠ The prototype uses a timer. The app shows Applied **only** on a 200 response with `status:"applied"`. |
| Applying (buttons disabled) | in flight; retry with the same `Idempotency-Key` | ✅ A replay returns the same response. |
| Out of date → Recalculate | `409 PROPOSAL_STALE` with `details.replacement` (new card, recomputed) | ✅ Show the replacement card; the user approves it with a new tap. |
| Replaced (Edit) | `POST /proposals/{id}/edit {payload_hash, payload}` → 201 new; old `superseded` | ✅ |
| Cancelled (Not now) | `POST /proposals/{id}/cancel` | ✅ |
| Failed + Retry | network error or 5xx → keep the key and retry; `409 PROPOSAL_MISMATCH` → reload the card | ✅ "Failed" must never be shown as applied. |
| Expired | `status:"expired"` / `410` | 🟡 pocket-pal has no expired state; add one ("This plan expired — ask again"). |
| Not possible + alternatives | `budget_plan` BP-1 refusal (error), `POST /plan/tradeoff`, goal `later_deadline` / `smaller_target_satang` | 🟡 There is no single "not possible" card. Render it from the error code plus the tradeoff proposal. "Move ฿750 from Savings" is not supported. |
| Card content: headline before→after, "paid for by N pockets", % of flexible budget | `card.changes[]` (`allocation_before/after_satang`, `delta_satang`, `remaining_*`), `card.transfer`, `card.summary.text` | 🟡 The prototype omits **warnings, uncertainty, assumptions, expires_at, money-left effects**. These are required: high-severity warnings go above Approve. The percentage needs its base label, which comes from the card, not the client. |
| "Balance unchanged · Bills and Savings locked" pill | `card.effects.money_left` before == after; `effects.commitments.changed` | 🟡 Derive the text from card fields only. |
| Applied → Undo | — | ❌ No undo endpoint. Proposal: remove Undo, or make Undo create a reverse proposal that needs a new approval (no silent revert). Codex to decide. |
| Insight card → "Plan this" | `GET /insights` → `recommendations[]` (`category`, `last_month_satang`, `average_satang`, `suggested_monthly_cut_satang`, `estimated_savings_per_month_satang`, `basis`, `goal_impact[]`) | 🟡 Different meaning: the backend compares the last complete month with an average, while the prototype compares equal elapsed periods (Oct 1–14 vs Sep 1–14). Render the backend's comparison and wording. "Plan this" → `/plan/tradeoff` or a reallocate proposal. |
| Paperclip upload → review sheet | goes through UploadQueue → `/uploads` → worker → `/review-items` | ⚠ The prototype opens the sheet immediately with a fake extraction. Real flow: queued → processing → imported, or needs review; open the sheet only from a real review item. |

### 1.4 Activity tab

| pocket-pal | API | Status / gap |
|---|---|---|
| Transactions grouped by day | `GET /transactions` (`occurred_date`, `payee_display`, `amount_satang`, `kind`, `category_code`, `category_state`, `source`, `payment_status`) | ✅ Group by `occurred_date` in the profile timezone. Money in = `kind in (income, refund, transfer_in)`. |
| Pocket on row (or ?) | `category_code` → pocket via `/pockets` categories | 🟡 Client-side join. Show `category_state=predicted` as "guess". |
| Source tag (slip / receipt / manual / csv) | `source` = `auto_import` / `review_import` / `manual` | 🟡 Receipt vs slip is not on the transaction; show "From photo" / "Entered". No CSV. |
| "Needs review (n)" filter and tag | `GET /review-items` → `items[]` | 🟡 Review items are **not** transactions (they are not counted yet). Show them as their own rows ("Waiting for you"). This matches the prototype's "not counted in totals" copy. |
| Possible duplicate tag | review item `reason=possible_duplicate`, `candidates[]` | ✅ |
| Pending / failed transfers | `payment_status` | 🟡 Not in the prototype; must be shown as "not counted". |
| Upcoming bills | `GET /bills?status=unpaid` (`biller`, `amount_due_satang`, `due_date`, `status`) | ✅ |
| Bill "change vs last" | `GET /insights` → `bill_changes[]` | ✅ |
| Bill "Paid?" → mark paid | `POST /bills/{id}/link-payment {txn_id}` | 🟡 Needs the payment transaction. Without one, the backend cannot mark the bill paid (this is by design: a bill is counted once, as its payment). The sheet must ask "Which payment was it?" |
| Tap row → review sheet edit | transactions: `PATCH /transactions/{id} {version, changes}`, `POST /transactions/{id}/category` | 🟡 Editing a confirmed transaction is a PATCH with a version (409 on conflict), not a review. |

### 1.5 Review sheet

| pocket-pal field | Backend | Status / gap |
|---|---|---|
| Photo with zoom | `GET /uploads/{id}/image` (auth, `no-store`) | ✅ Must not be cached on disk. |
| Type (Receipt / Bill / Slip) | `extracted.doc_type` (`transfer_out`, `transfer_in`, `receipt`, `bill`, `not_financial`) | 🟡 The prototype has no transfer-in or "not a document"; add them. |
| Amount / date / shop | `extracted.amount_text`, `date_text`, `payee`; corrections sent as `fields` in `resolve {decision:"accept", fields}` | ✅ Corrections are sent as **text** and parsed by the server (no client float). Flag what the server marked missing or conflicting (`problem_fields`), not what the client guesses. |
| "Check this" / "Needed" | `problem_fields[]`, reason | ✅ |
| Save / Cancel | `allowed_decisions[]` drives the buttons: `accept` / `not_a_transaction` / `duplicate_of` / `link_receipt` / `distinct` with `candidates[]` | ⚠ The prototype has one Save. The app shows exactly the allowed decisions; for `receipt_link`, "Same purchase — attach" (shipped in CP3a). |
| Pocket chips | after accept: `POST /transactions/{txn_id}/category {category, set_payee_default}`, using `txn_id` from the resolve result | 🟡 Two calls. Or `batch-categorise` by `payee_key`. |
| "What was this payment for?" | `description` exists on transactions (PATCH) | 🟡 Not part of resolve. |
| Bill paid status | reviewed bill → `bill_id`; paid = link-payment | 🟡 as 1.4 |
| Unreadable photo | `reason=missing_fields`, `readability=poor` | ✅ |

### 1.6 Goal tab

| pocket-pal | API | Status / gap |
|---|---|---|
| Progress (saved / target, deadline, days left) | `GET /goals` (raw rows), `POST /goals/feasibility` | 🟡 `GET /goals` returns raw DB rows; acceptable for display. |
| Planned contributions per payday ("Fits" / "short") | feasibility: `contribution_events`, `required_per_event_satang`, `capacity_per_event_satang` | 🟡 The backend gives one capacity for every event, not a per-date "free" value. The schedule rows would show the same capacity. |
| Status On track / with changes / not possible yet | `feasible`, `later_deadline`, `smaller_target_satang`, `extra_saving_needed_per_event_satang` | 🟡 "with changes" = not feasible but an option exists. |
| Options: deadline / target / income / take from a pocket | `later_deadline`, `smaller_target_satang` → `goal_update` proposal; income → profile | 🟡 "Take ฿850 from Leisure" is not computed by the backend. |
| "Choose this" → chat | `POST /proposals kind=goal_update` → card → approve | ✅ No chat needed. |

### 1.7 Settings

| pocket-pal | API | Status / gap |
|---|---|---|
| Recent changes | `GET /proposals?status=applied`, `GET /audit` | 🟡 Read-only list. Undo: see 1.3. |
| Profile rows → "Change" via chat | `PUT /me/profile` (direct, user action) | 🟡 A direct form is allowed; the chat is not needed. |
| "Delete uploaded photos" | `POST /data/delete {scope:"imported"}` → `complete`, `images_pending_purge` | 🟡 The backend scope "imported" deletes the imported records **and** their images, not only the photos. The copy must say exactly what is deleted. |
| "Delete all my data" | — | ❌ Scope `all` is not implemented. |
| ⚠ "Nothing from your photo album is read automatically" | album scan (R2.1, CP3b) | ⚠ Contradicts the required album scan once consented. Rewrite: "Only photos from the date you allowed, and only after you turn it on." |
| ⚠ "Only the fields needed are sent to the AI service. Account numbers are removed where possible." | the extraction provider receives the **whole image** (`providers.py`) | ⚠ Not true today. Copy must say "the photo is sent to the extraction service (Anthropic) to read it". |
| Consent screen | `GET/POST/DELETE /consents` (photo_processing with `scan_from`, auto_import) | ✅ The prototype has no consent screen; keep the CP3a one, restyled. |
| Session / account | — | The prototype has no sign-out or account switch; keep CP3a's (SessionGate, discard notice). |

## 2. Demo-only vs backend-supported

| Demo only in pocket-pal (do not ship as real) | Backend-supported (wire to the API) |
|---|---|
| Demo user Mook, demo money, demo pockets, demo proposal, "not possible" detail, extracted bill, delivery insight, trip plan, bills, transactions, recent changes, profile | auth, profile, balance, consents, uploads + queue, review items + allowed decisions + candidates, transactions + category, bills + link payment, plan / cashflow / pockets, insights (month vs average, pace, bill changes, recommendations), spending report, affordability, goal feasibility, proposals + approval cards (reallocate, budget_plan, goal_create/update, tradeoff), data delete (imported), audit, chat (with a configured model) |
| Timer approval, local Undo, local "deleted" notices, CSV "got file" | — |
| Equal-period insight; per-payday "free" goal schedule; "take from pocket" goal option; "spent today"; protected pockets; Savings pocket | gaps: listed in §1, each needs a decision (implement in backend, or drop from the UI) |

## 3. Compose vs web shell

Hard requirements: album scan (MediaStore, partial access, revocation), WorkManager background work with its own
identity check, account isolation (one session, one owner-bound queue, discard on switch), Keystore token, no
API key in the client, release HTTPS only.

| | **A. Native Compose, pocket-pal as the spec** | B. WebView shell running pocket-pal |
|---|---|---|
| Album scan, background, permissions | native, same process as the queue (as designed in `11`) | still native; the web needs a JS bridge to queue, status and permission state |
| Session and account isolation | one SessionGate, one token store; CP3a guarantees stay | two session states (native and WebView JS/storage) that must stay in sync. This is the class of bug CP3a fixed (late 401, account switch). |
| Token exposure | Keystore; never visible to UI code | the token in JS (or a cookie in the WebView store) is reachable by any script/XSS in the bundle; needs a native proxy for every call |
| Upload path | Photo Picker → UploadQueue (exactly once, owner-bound) | `<input type=file>` bypasses the queue unless every upload goes through the bridge |
| Build | already builds; Compose BOM pinned | Next.js 15 needs `output: export` (no server), asset loader, CSP; new toolchain in the APK build |
| Review / Codex | changes stay inside reviewed boundaries | a new trust boundary (bridge API) to design and review |
| Cost | rewrite ~3.2k lines TSX as Compose screens (tokens, cards, sheet, tab bar) | less UI work, more security and integration work |
| Demo fidelity | close (tokens, radii, fonts: Plus Jakarta Sans + Noto Sans Thai as bundled fonts) | exact |

**Proposal: A.** Port the design tokens (`MASTER.md`) into a Compose theme and components: card, icon tile, hint
pill, progress track, gauge, action card, review sheet, tab bar. pocket-pal stays the design reference. Its
`CONTEXT.md` vocabulary is reused for UI strings where it matches backend meaning, and corrected where it doesn't
(§1.7 ⚠ items). Not proposed: shipping both.

## 4. Vertical slice 1: sign in → consent → upload → review → activity

Real backend (`dev_server.py --profile dev --provider fake`) and synthetic slips. No reset of the phone DB by
Claude; automated tests use the `e2e` profile.

| Step | Screen (pocket-pal style) | Calls | States that must work |
|---|---|---|---|
| 1 | Sign in / sign up (new style; not in pocket-pal) | `/auth/*`, `GET /me` via SessionGate | Checking → Ready / IdentityFailed + Retry; 401 → Session ended; account switch → discard notice |
| 2 | Consent (restyled CP3a: three separate switches) | `GET/POST/DELETE /consents` | photo processing with `scan_from`; auto-import separate; withdraw → queue blocks with a reason |
| 3 | Upload: paperclip / "Upload slip" → Photo Picker → queue list | UploadQueue → `POST /uploads` (multipart, `captured_at`, `expected_owner_id`, `confirmed_undated`) | JPEG/PNG only, **≤ 8 MiB = backend `max_upload_bytes`** (the prototype's 10 MB is wrong); waiting / processing / imported / needs review / failed + retry; pause; undated confirmation |
| 4 | Review sheet (pocket-pal variant A layout) | `GET /review-items`, `GET /uploads/{id}/image`, `POST /review-items/{id}/resolve`, then `POST /transactions/{txn}/category` | buttons = `allowed_decisions`; candidates shown for duplicate / receipt; `problem_fields` flagged; corrections as text; 409 `DECISION_NOT_ALLOWED` / `POSSIBLE_DUPLICATE` handled; 404 after a lost response = "already done" → refresh |
| 5 | Activity (pocket-pal layout, real data) | `GET /transactions`, `GET /review-items`, `GET /bills?status=unpaid`, `GET /pockets` | grouped by day; "Waiting for you" rows from review items, not counted; pending/failed shown as not counted; amounts from `amount_satang` via `Money` (Long satang). Today `Money.format` always prints `.00`; slice 1 adds a compact form (no decimals when satang = 0, as `MASTER.md` asks), with tests. |

Out of slice 1: chat and action cards (needs the scripted chat flag, CP3b), goal tab, insights, bills paid, settings
delete, album scan.

Acceptance for slice 1 (proposal):
- Core JVM tests:
  - money formatting from satang (no Double)
  - the upload limit equals the backend value
  - review buttons are exactly `allowed_decisions`
  - "Waiting" items are excluded from day totals
- E2E (`e2e` profile, extended `Cp3aE2E`):
  - signup → consent → upload 003 / 024 / 015+016
  - resolve 024 with amount "120.00"
  - link 016 as receipt (no new spending)
  - the activity data equals the server lists
- Device (owner, user-reported): the CP3a checklist lines on the new screens, plus a visual check against the pocket-pal style board.
- Existing CP3a tests stay green (27/27 core, 27/27 E2E).

## 5. Contract notes for Codex (no backend added yet)

1. Upload limit: `max_upload_bytes` (8 MiB) is not visible to clients. Options:
   - add `limits.max_upload_bytes` to `/v1/health` (one field, not a new endpoint);
   - or a client constant with a test that reads `Settings`.

   Either way the 10 MB in pocket-pal must change.
2. `05` says every mutating request needs `Idempotency-Key`, but only `POST /transactions` and `/approve` use one.
   `resolve` is at-most-once (the row is locked; a repeat gives 404), so it is safe but cannot tell "already done"
   from "not found". Proposal: add the existing `idempotent()` wrapper to `resolve` and `category` (same helper, no new
   backend).
3. Decisions needed from the team / Codex: Undo; "spent today"; "protected"; Savings pocket; equal-period insights;
   the per-payday goal schedule; delete-all. Each one is either built in the backend or removed from the UI. None is
   faked on the client.
