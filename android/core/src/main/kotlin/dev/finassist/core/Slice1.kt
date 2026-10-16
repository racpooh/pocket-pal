package dev.finassist.core

import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

/*
 * UI-independent logic for vertical slice 1 (sign in → consent → upload → review → activity), docs/design/13 §4.
 * Pure Kotlin so it is unit-tested on a plain JVM. Screens only render what these functions return; every amount is a
 * Long in satang from the backend and becomes text only here. Nothing in this file holds demo or sample data.
 */

/** Same limits as the backend: `Settings.max_upload_bytes` = 8 MiB, magic-byte check accepts JPEG and PNG only. */
object UploadLimits {
    const val MAX_BYTES: Int = 8 * 1024 * 1024
    val ACCEPTED_MIME = setOf("image/jpeg", "image/png")

    /** null = acceptable; otherwise a short reason shown to the user. The server checks again (413 / 415). */
    fun problem(sizeBytes: Long, mime: String?): String? = when {
        mime !in ACCEPTED_MIME -> "Not a JPG or PNG photo"
        sizeBytes > MAX_BYTES -> "Larger than 8 MB"
        sizeBytes <= 0 -> "Empty file"
        else -> null
    }
}

/**
 * Display formats for satang amounts (MASTER.md: no decimals unless satang matter). Never a Double.
 * Two kinds, chosen per call site (Codex slice-1 review, finding 2):
 *  - [magnitude] for a transaction/bill amount whose direction is said in words or by [signed] ("+฿160", "−฿89").
 *  - [amount] for a value that can be negative (safe to spend, daily allowance, balance): the sign is kept, so a
 *    shortage is never shown as money available.
 */
object MoneyText {
    private fun digits(a: Long): String {
        val whole = "฿" + "%,d".format(Locale.US, a / 100)
        return if (a % 100 == 0L) whole else whole + "." + "%02d".format(Locale.US, a % 100)
    }

    /** Size only (no sign). Callers must word the direction. */
    fun magnitude(satang: Long): String = digits(kotlin.math.abs(satang))

    /** Keeps the sign: −฿200, ฿0, ฿1,240.50 (U+2212 minus). */
    fun amount(satang: Long): String = (if (satang < 0) "−" else "") + digits(kotlin.math.abs(satang))

    /** "+฿160" for money in, "−฿89" for money out. [satang] is the transaction's (positive) amount. */
    fun signed(satang: Long, moneyIn: Boolean): String = (if (moneyIn) "+" else "−") + digits(kotlin.math.abs(satang))

    /** Safe to spend in words: "฿1,240 to spend" or "Short ฿200" — a negative value is never presented as available. */
    fun safeToSpend(satang: Long): String = if (satang < 0) "Short ${digits(-satang)}" else "${digits(satang)} to spend"
}

/** What happened to one resolve call. A 404 is NOT a success: the item is no longer open, which we cannot tell apart
 * from "never existed / deleted" (docs/design/13 §5.2), so the list is reloaded and the user is told to check. */
sealed class ResolveOutcome {
    data class Done(val decision: String, val txnId: String?, val billId: String?) : ResolveOutcome()
    data class NoLongerOpen(val requestId: String?) : ResolveOutcome()
    data class NotAllowed(val message: String) : ResolveOutcome()
    data class PossibleDuplicate(val message: String) : ResolveOutcome()
    data class Invalid(val message: String, val fields: List<String>) : ResolveOutcome()
    /** No HTTP response: it may or may not have been saved. Reload before offering the action again. */
    object Unknown : ResolveOutcome()
    data class Failed(val code: String, val message: String, val retryable: Boolean) : ResolveOutcome()

    val isSuccess: Boolean get() = this is Done

    fun userText(): String = when (this) {
        is Done -> when {
            decision == "not_a_transaction" -> "Marked as not a transaction. Nothing was recorded."
            decision == "link_receipt" -> "Attached to the existing record. No new spending was added."
            decision == "duplicate_of" -> "Kept as the same payment. Nothing was recorded twice."
            billId != null -> "Saved as a bill."
            else -> "Recorded."
        }
        is NoLongerOpen -> "This item is no longer waiting for you. It may already have been handled, or removed. " +
                "Nothing is shown as saved — the list was refreshed; check Activity."
        is NotAllowed -> "That choice is not possible for this item any more. The list was refreshed. ($message)"
        is PossibleDuplicate -> "A record with the same bank reference already exists. Choose “same payment” or “different payment”."
        is Invalid -> "Some details are still missing or invalid: ${fields.joinToString().ifEmpty { message }}"
        Unknown -> "No answer from the server — it may or may not have been saved. The list was refreshed; try again only if the item is still there."
        is Failed -> "$message ($code)"
    }
}

object ReviewResolver {
    /** Maps the result of `ApiClient.resolveReview` to an outcome. 401 is never mapped here (the session layer handles it). */
    fun classify(decision: String, result: Result<Map<String, Any?>>): ResolveOutcome {
        val e = result.exceptionOrNull() ?: return result.getOrThrow().let { ResolveOutcome.Done(decision, it.str("txn_id"), it.str("bill_id")) }
        if (e is SessionExpiredException) throw e
        if (e is NetworkException) return ResolveOutcome.Unknown
        if (e !is ApiException) throw e
        return when {
            e.status == 404 -> ResolveOutcome.NoLongerOpen(e.requestId)
            e.status == 409 && e.code == "DECISION_NOT_ALLOWED" -> ResolveOutcome.NotAllowed(e.message ?: e.code)
            e.status == 409 && e.code == "POSSIBLE_DUPLICATE" -> ResolveOutcome.PossibleDuplicate(e.message ?: e.code)
            e.status == 400 -> ResolveOutcome.Invalid(e.message ?: e.code, e.fields.mapNotNull { it.str("path") })
            else -> ResolveOutcome.Failed(e.code, e.message ?: "Request failed", e.retryable)
        }
    }
}

/**
 * One review item as the review sheet shows it. Built only from backend fields.
 *
 * Inputs (Codex slice-1 review, finding 1): every field the backend needs to accept the item can be supplied, using the
 * extraction field names and values the server accepts (`resolve` re-validates with the same rules as the worker):
 *  - text: amount_text, date_text, time_text, payee, and due_date_text for bills;
 *  - choice `status` (transfers only): success / pending / failed / scheduled — never pre-selected when the reading was
 *    unknown or missing; what the user picks decides how the ledger counts it (completed counts; pending/failed do not);
 *  - choice `doc_type`: shown only when the type could not be determined (direction/doc_type problem) — never guessed.
 */
class ReviewView(item: Map<String, Any?>) {
    data class Candidate(val txnId: String, val amountSatang: Long?, val date: String?, val payee: String?, val source: String?)
    data class Choice(val value: String, val label: String)

    val id: String = item.str("id") ?: error("review item without id")
    val uploadId: String? = item.str("upload_id")
    val reason: String? = item.str("reason")
    val extracted: Map<String, Any?> = item.obj("extracted") ?: emptyMap()
    val problemFields: List<String> = item.list("problem_fields").map { it.toString() }
    val actions: List<ReviewActions.Action> = ReviewActions.forItem(item)
    val candidates: List<Candidate> = item.list("candidates").objs().mapNotNull { c ->
        c.str("txn_id")?.let { Candidate(it, c.long("amount_satang"), c.str("occurred_date"), c.str("payee_display"), c.str("source")) }
    }
    val docType: String? = extracted.str("doc_type")?.takeIf { it in DOC_TYPES }

    companion object {
        val DOC_TYPES = setOf("transfer_out", "transfer_in", "receipt", "bill", "not_financial")
        /** Values `status` may take on resolve (EXTRACTION_TOOL enum minus "unknown"), with what they mean for the ledger. */
        val STATUS_CHOICES = listOf(
            Choice("success", "Completed — counted"), Choice("pending", "Pending — recorded, not counted"),
            Choice("failed", "Failed — recorded, not counted"), Choice("scheduled", "Scheduled — recorded as pending, not counted"))
        val TYPE_CHOICES = listOf(
            Choice("transfer_out", "Money I sent"), Choice("transfer_in", "Money I received"),
            Choice("receipt", "Shop receipt"), Choice("bill", "Bill to pay"))
        private val READ_STATUS = setOf("success", "pending", "failed", "scheduled")
    }

    val title: String get() = when (reason) {
        "missing_fields" -> "Some details could not be read"
        "confirm_import" -> "Check before it is recorded"
        "possible_duplicate" -> "Possible duplicate"
        "receipt_link" -> "Receipt for a payment you already have?"
        "unpaid_bill_match" -> "Is this the payment of a bill?"
        else -> "Needs your check"
    }

    /** Amount as read, for list rows only (not counted anywhere). null when unreadable. */
    val amountReadSatang: Long? get() = extracted.str("amount_text")?.let { Money.parseThb(it) }

    /** The document type in effect: what the user picked, else what was read. */
    fun effectiveType(edited: Map<String, String>): String? = edited["doc_type"]?.takeIf { it.isNotBlank() } ?: docType

    /** Type chooser only when the type is unknown or flagged; a readable type is not re-asked. */
    val asksType: Boolean get() = docType == null || docType == "not_financial" || "direction" in problemFields || "doc_type" in problemFields

    /** Initial values for the inputs. `status` starts empty unless a valid status was read; `doc_type` starts empty when asked. */
    fun initialInputs(): Map<String, String> = buildMap {
        for (f in listOf("amount_text", "date_text", "time_text", "payee", "due_date_text")) put(f, extracted.str(f) ?: "")
        put("status", extracted.str("status")?.lowercase()?.takeIf { it in READ_STATUS } ?: "")
        put("doc_type", if (asksType) "" else docType ?: "")
    }

    /** Which inputs to show for the current choice of type. */
    fun inputs(edited: Map<String, String>): List<String> {
        val t = effectiveType(edited)
        return buildList {
            if (asksType) add("doc_type")
            addAll(listOf("amount_text", "date_text", "time_text", "payee"))
            if (t == "bill" || "due_date" in problemFields) add("due_date_text")
            if (t == "transfer_out" || t == "transfer_in" || "payment_status" in problemFields) add("status")
        }
    }

    fun flagged(field: String): Boolean = when (field) {
        "amount_text" -> "amount" in problemFields
        "date_text", "time_text" -> "occurred" in problemFields || "date" in problemFields
        "payee" -> "payee" in problemFields
        "due_date_text" -> "due_date" in problemFields
        "status" -> "payment_status" in problemFields
        "doc_type" -> asksType
        else -> field in problemFields
    }

    /**
     * Inputs the server requires before it accepts the item (same rule as `resolve`: bills need amount, date, due date;
     * transfers need amount, date, type and a known status; receipts amount, date, type). Presence only — the server parses.
     */
    fun missingRequired(edited: Map<String, String>): List<String> {
        val t = effectiveType(edited)
        val need = mutableListOf("amount_text", "date_text")
        if (t == null || t == "not_financial") need += "doc_type"
        if (t == "bill") need += "due_date_text"
        if (t == "transfer_out" || t == "transfer_in") need += "status"
        return need.filter { (edited[it] ?: "").isBlank() }
    }

    /** Only the inputs the user actually changed (compared with what was read); blank time becomes null. */
    fun changedFields(edited: Map<String, String>): Map<String, Any?>? {
        val out = linkedMapOf<String, Any?>()
        val before = mapOf("doc_type" to (extracted.str("doc_type") ?: ""), "status" to (extracted.str("status") ?: ""))
        for ((f, now) in edited) {
            if (f !in setOf("amount_text", "date_text", "time_text", "payee", "due_date_text", "status", "doc_type")) continue
            val old = before[f] ?: (extracted.str(f) ?: "")
            if (now == old) continue
            if ((f == "status" || f == "doc_type") && now.isBlank()) continue // an empty choice is not a change
            out[f] = if (f == "time_text" && now.isBlank()) null else now
        }
        return out.ifEmpty { null }
    }

    /** The txn to send with a decision that needs one; null if the decision needs none or the choice is missing/invalid. */
    fun txnFor(action: ReviewActions.Action, chosenTxnId: String?): String? {
        if (!action.needsCandidate) return null
        val ids = candidates.map { it.txnId }
        return when {
            chosenTxnId != null && chosenTxnId in ids -> chosenTxnId
            ids.size == 1 -> ids.single()
            else -> null
        }
    }

    /** accept/distinct need the required inputs; decisions about an existing record need a valid candidate. */
    fun canRun(action: ReviewActions.Action, chosenTxnId: String?, edited: Map<String, String> = initialInputs()): Boolean = when {
        action.needsCandidate -> txnFor(action, chosenTxnId) != null
        action.decision == "accept" || action.decision == "distinct" -> missingRequired(edited).isEmpty()
        else -> true
    }
}

/** Activity tab model (pocket-pal "Activity" layout, real backend data). */
object ActivityModel {
    private val MONEY_IN = setOf("income", "refund", "transfer_in")

    data class Row(
        val key: String, val title: String, val amountSatang: Long?, val moneyIn: Boolean,
        /** Counted in totals: a completed transaction. Waiting items, pending and failed payments are not. */
        val counted: Boolean, val tags: List<String>, val pocket: String?, val source: String, val reviewId: String?,
    )
    data class Day(val date: String, val label: String, val rows: List<Row>, val outSatang: Long, val inSatang: Long)
    data class Bill(val id: String, val biller: String, val amountSatang: Long, val due: String, val daysUntil: Long)
    data class Screen(val bills: List<Bill>, val waiting: List<Row>, val days: List<Day>, val pocketFilters: List<String>)

    private val SHORT = DateTimeFormatter.ofPattern("d MMM", Locale.ENGLISH)

    fun dayLabel(date: String, today: LocalDate): String {
        val d = runCatching { LocalDate.parse(date) }.getOrNull() ?: return date
        return when (d) { today -> "Today"; today.minusDays(1) -> "Yesterday"; else -> d.format(SHORT) }
    }

    /** category code → pocket name, from GET /pockets ({name, categories[]}). */
    fun pocketByCategory(pockets: List<Map<String, Any?>>): Map<String, String> =
        pockets.flatMap { p -> p.list("categories").map { it.toString() to (p.str("name") ?: "") } }.toMap()

    fun build(txns: List<Map<String, Any?>>, reviewItems: List<Map<String, Any?>>, bills: List<Map<String, Any?>>,
              pockets: List<Map<String, Any?>>, today: LocalDate): Screen {
        val byCat = pocketByCategory(pockets)
        val rows = txns.mapNotNull { t ->
            val id = t.str("id") ?: return@mapNotNull null
            val status = t.str("payment_status")
            val tags = mutableListOf<String>()
            when (status) { "pending" -> tags += "Pending · not counted"; "failed" -> tags += "Failed · not counted" }
            if (t.str("category_state") == "predicted") tags += "Guessed pocket"
            val cat = t.str("category_code")
            (t.str("occurred_date") ?: "") to Row(
                key = "t:$id", title = t.str("payee_display")?.takeIf { it.isNotBlank() } ?: "(no name)",
                amountSatang = t.long("amount_satang"), moneyIn = t.str("kind") in MONEY_IN, counted = status == "completed",
                tags = tags, pocket = cat?.let { byCat[it] }, source = when (t.str("source")) {
                    "auto_import", "review_import" -> "From photo"; "manual" -> "Entered"; else -> t.str("source") ?: "" },
                reviewId = null)
        }
        val days = rows.groupBy({ it.first }, { it.second }).toSortedMap(compareByDescending { it }).map { (date, rs) ->
            Day(date, dayLabel(date, today), rs,
                rs.filter { it.counted && !it.moneyIn }.sumOf { it.amountSatang ?: 0L },
                rs.filter { it.counted && it.moneyIn }.sumOf { it.amountSatang ?: 0L })
        }
        val waiting = reviewItems.mapNotNull { runCatching { ReviewView(it) }.getOrNull() }.map { v ->
            Row("r:${v.id}", v.extracted.str("payee")?.takeIf { it.isNotBlank() } ?: v.title, v.amountReadSatang,
                v.docType == "transfer_in", counted = false,
                tags = listOf(if (v.reason == "possible_duplicate") "Possible duplicate" else "Needs review", "Not counted yet"),
                pocket = null, source = "From photo", reviewId = v.id)
        }
        val unpaid = bills.filter { it.str("status") == "unpaid" }.mapNotNull { b ->
            val due = b.str("due_date") ?: return@mapNotNull null
            val d = runCatching { LocalDate.parse(due) }.getOrNull() ?: return@mapNotNull null
            Bill(b.str("id") ?: return@mapNotNull null, b.str("biller") ?: "Bill", b.long("amount_due_satang") ?: 0L, due,
                java.time.temporal.ChronoUnit.DAYS.between(today, d))
        }.sortedBy { it.due }
        return Screen(unpaid, waiting, days, rows.mapNotNull { it.second.pocket }.distinct().sorted())
    }
}
