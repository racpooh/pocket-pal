package dev.finassist.e2e

import dev.finassist.core.*
import java.awt.image.BufferedImage
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.UUID
import javax.imageio.ImageIO

/**
 * CP3a end-to-end scenario: the client core (same ApiClient + UploadQueue code the Android app uses) against the
 * REAL backend (FastAPI + Postgres with RLS + embedded worker) started by backend/scripts/dev_server.py.
 * Extraction is the FAKE provider preloaded with SYNTHETIC fixtures (test mode, no model calls).
 * This is not an Android UI test: it proves the client logic and the API contract, not screens or OS permissions.
 *
 * args: <baseUrl> <syntheticSlipsDir> <outDir>
 */
fun main(args: Array<String>) {
    val (base, slipsDir, outDir) = args
    val steps = mutableListOf<Map<String, Any?>>()
    fun step(name: String, expected: String, block: () -> Any?) {
        val t0 = System.currentTimeMillis()
        val (ok, actual) = try {
            val r = block()
            (r != false) to (if (r is Boolean) (if (r) "as expected" else "NOT as expected") else r.toString())
        } catch (e: Throwable) { false to "${e::class.java.simpleName}: ${e.message}" }
        steps += linkedMapOf("step" to name, "expected" to expected, "actual" to actual, "ok" to ok, "ms" to System.currentTimeMillis() - t0)
        println((if (ok) "PASS " else "FAIL ") + name + " — " + actual)
    }
    fun slip(name: String) = File(slipsDir, name).readBytes()
    fun waitUntil(timeoutMs: Long = 60_000, cond: () -> Boolean): Boolean {
        val end = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < end) { if (cond()) return true; Thread.sleep(500) }
        return false
    }
    val nonFixture = ByteArrayOutputStream().also { ImageIO.write(BufferedImage(64, 64, BufferedImage.TYPE_INT_RGB).apply {
        for (x in 0 until 64) for (y in 0 until 64) setRGB(x, y, (x * 4 shl 16) or (y * 4 shl 8)) }, "png", it) }.toByteArray()

    val transport = UrlConnectionTransport()
    val tokensA = MemoryTokenStore()
    val a = ApiClient(base, transport, tokensA, debugBuild = true)
    val emailA = "a-${UUID.randomUUID().toString().take(8)}@example.test"
    val pw = "correct horse battery"
    val store = object : QueueStore { var v: String? = null; override fun load() = v; override fun save(json: String) { v = json } }
    val blobs = object : BlobStore {
        val m = HashMap<String, ByteArray>()
        override fun put(key: String, bytes: ByteArray) { m[key] = bytes }
        override fun get(key: String) = m[key]
        override fun delete(key: String) { m.remove(key) }
    }
    var q = UploadQueue(store, blobs, ApiUploadAdapter(a))
    val captured = "2026-10-15T13:00:00+07:00"

    step("health reports test mode (client must show TEST MODE banner)", "test_mode=true") { a.health().bool("test_mode") == true }
    step("release build refuses cleartext base URL", "IllegalArgumentException") {
        try { ApiClient(base, transport, MemoryTokenStore(), debugBuild = false); false } catch (e: IllegalArgumentException) { true } }
    step("signup + wrong password is rejected and stores no token", "401, no token") {
        a.signup(emailA, pw)
        try { a.login(emailA, "wrong password!!"); false } catch (e: SessionExpiredException) { tokensA.get() == null }
    }
    step("login stores a session token; queue bound to the account from GET /me", "signed in, owner bound") {
        a.login(emailA, pw); q.bindOwner(a.me()); a.isSignedIn && q.owner != null }
    step("setup: profile, balance ฿15,000, five pockets", "plan has money left ฿10,000 after rent") {
        a.putProfile(2_000_000, "monthly", "2026-11-01", listOf(mapOf("name" to "Rent", "amount_satang" to 500_000L, "due_day" to 30L)))
        a.addBalance(a.accounts()[0].str("id")!!, 1_500_000)
        for ((n, c) in listOf("Food" to listOf("food"), "Shopping" to listOf("shopping"), "Transport" to listOf("transport"),
                "Entertainment" to listOf("entertainment"), "Other" to listOf("other", "bills"))) a.createPocket(n, c)
        a.plan().obj("cashflow")!!.long("discretionary_satang") == 1_000_000L
    }
    step("upload before photo consent: server refuses, queue blocks, nothing stored", "queue blocked CONSENT_REQUIRED, 0 uploads") {
        q.enqueue(slip("slip_003_transfer_out.png"), "image/png", captured)
        q.runOnce()
        q.blocked == BlockReason.CONSENT_REQUIRED && a.uploads().isEmpty()
    }
    step("grant photo processing (scan from 1 Jul) and auto-import separately; resume", "2 active scopes") {
        a.grantConsent("photo_processing", "v1", mapOf("scan_from" to "2026-07-01"))
        a.grantConsent("auto_import", "v1")
        q.resume()
        a.activeConsentScopes() == setOf("photo_processing", "auto_import")
    }
    step("enqueue: 003 again (same image), 004, 024 (blurred), 021, 028 (bill), non-fixture image", "6 entries, 003 not duplicated") {
        q.enqueue(slip("slip_003_transfer_out.png"), "image/png", captured)
        for (f in listOf("slip_004_transfer_out.png", "slip_024_transfer_out.png", "slip_021_transfer_out.png", "slip_028_bill.png"))
            q.enqueue(slip(f), "image/png", captured)
        q.enqueue(nonFixture, "image/png", captured)
        q.snapshot().size == 6
    }
    step("app restart: a new queue instance from the persisted state keeps all entries and its owner", "6 entries, same owner") {
        val o = q.owner; q = UploadQueue(store, blobs, ApiUploadAdapter(a)); q.snapshot().size == 6 && q.owner == o
    }
    step("send: every entry uploaded exactly once; local copies removed", "6 sent, 0 local blobs") {
        q.runOnce(); q.snapshot().all { it.state == LocalState.SENT } && blobs.m.isEmpty() && a.uploads().size == 6
    }
    step("server processing reaches a terminal state for all", "all terminal within 60 s") {
        waitUntil { q.refresh(); !q.hasWork }
    }
    val bySha = { name: String -> q.snapshot().first { it.sha256 == UploadQueue.sha256Hex(if (name == "nonfixture") nonFixture else slip(name)) } }
    step("outcomes: clear slips imported, blurred slip in review, bill in review/imported, unknown image failed", "see actual") {
        listOf("slip_003_transfer_out.png", "slip_004_transfer_out.png", "slip_021_transfer_out.png", "slip_024_transfer_out.png",
            "slip_028_bill.png", "nonfixture").joinToString { "${it.removeSuffix(".png")}=${bySha(it).serverStatus}" }
    }
    step("labels the UI would show", "human-readable, no raw codes for normal states") {
        q.snapshot().joinToString(" | ") { UploadLabels.label(it, q.blocked) }
    }
    step("server-side dedup: same bytes sent directly (bypassing local dedup) → 200 duplicate_image", "duplicate=true, same id") {
        val r = a.upload(slip("slip_003_transfer_out.png"), "image/png", captured)
        r.httpStatus == 200 && r.duplicateImage && r.uploadId == bySha("slip_003_transfer_out.png").uploadId
    }
    step("retry of the failed (non-fixture) image: server re-queues once; the fake extractor fails again honestly", "extract_failed again") {
        val e = bySha("nonfixture")
        UploadLabels.canRetryServer(e) && run { a.retryUpload(e.uploadId!!); q.markServerRetried(e.sha256)
            waitUntil { q.refresh(); bySha("nonfixture").serverStatus == "extract_failed" } }
    }
    step("review: blurred slip asks for the amount; user enters it; accept imports one transaction", "imported, txn created") {
        val items = a.reviewItems().list("items").objs()
        val it24 = items.first { it.str("upload_id") == bySha("slip_024_transfer_out.png").uploadId }
        val r = a.resolveReview(it24.str("id")!!, "accept", mapOf("amount_text" to "120.00"))
        q.refresh(); r.str("txn_id") != null && bySha("slip_024_transfer_out.png").let { a.uploadDetail(it.uploadId!!).str("status") } == "imported"
    }
    step("review: resolving the same item again is refused (no double import)", "404") {
        val id = bySha("slip_024_transfer_out.png").uploadId
        try { a.resolveReview(a.reviewItems().list("items").objs().firstOrNull { it.str("upload_id") == id }?.str("id") ?: "00000000-0000-0000-0000-000000000000", "accept"); false }
        catch (e: ApiException) { e.status == 404 }
    }
    step("ledger: transactions listed with source; unclassified payees surfaced", "≥3 txns; uncategorised list present") {
        val txns = a.transactions()
        val unc = a.reviewItems().list("uncategorised_payees").objs()
        "txns=${txns.size} sources=${txns.map { it.str("source") }.toSet()} unclassified_groups=${unc.size} money_left=${a.plan().obj("cashflow")!!.long("discretionary_satang")}"
    }

    step("undated photo: refused until the user confirms that photo; then sent with the confirmation", "CAPTURE_DATE_REQUIRED → imported") {
        val e = q.enqueue(slip("slip_009_transfer_out.png"), "image/png", null)
        q.runOnce()
        val asked = UploadLabels.needsUndatedConfirmation(q.snapshot().first { it.sha256 == e.sha256 })
        q.confirmUndated(e.sha256); q.runOnce()
        asked && waitUntil { q.refresh(); q.snapshot().first { it.sha256 == e.sha256 }.serverStatus in UploadQueue.TERMINAL_SERVER }
    }
    step("receipt for a purchase already recorded: review offers attach/different only; attaching adds no spending", "no accept; spending unchanged") {
        val gtRows = File(slipsDir, "ground_truth.jsonl").readLines().filter { it.isNotBlank() }.map { Json.obj(it) }
        val rec = gtRows.first { r -> r.str("doc_type") == "receipt" && r.list("group_tags").any { it.toString().startsWith("same_purchase_as") } }
        val pair = rec.list("group_tags").first { it.toString().startsWith("same_purchase_as") }.toString().substringAfter(":")
        q.enqueue(slip(pair), "image/png", captured); q.runOnce(); waitUntil { q.refresh(); !q.hasWork }
        val spendBefore = a.transactions().size
        q.enqueue(slip(rec.str("file")!!), "image/png", captured); q.runOnce(); waitUntil { q.refresh(); !q.hasWork }
        val item = a.reviewItems().list("items").objs().first { it.str("reason") == "receipt_link" }
        val actions = ReviewActions.forItem(item)
        val cand = item.list("candidates").objs().single()
        a.resolveReview(item.str("id")!!, "link_receipt", txnId = cand.str("txn_id"))
        actions.none { it.decision == "accept" } && actions.first().decision == "link_receipt" && a.transactions().size == spendBefore
    }

    // ---- vertical slice 1 (docs/design/13 §4): the models the new screens render, on real server data ----
    step("slice1: an image over the client limit is also refused by the server (limits agree)", "client problem + 413 UPLOAD_TOO_LARGE") {
        val big = ByteArray(UploadLimits.MAX_BYTES + 1).also { byteArrayOf(-119, 80, 78, 71, 13, 10, 26, 10).copyInto(it) }
        val client = UploadLimits.problem(big.size.toLong(), "image/png")
        val server = try { a.upload(big, "image/png", captured); "accepted" } catch (e: ApiException) { "${e.status} ${e.code}" }
        client != null && server == "413 UPLOAD_TOO_LARGE"
    }
    step("slice1: review sheet photo is the uploaded image (bytes, in memory)", "same sha256") {
        val e = bySha("slip_003_transfer_out.png")
        UploadQueue.sha256Hex(a.uploadImage(e.uploadId!!)) == e.sha256
    }
    step("slice1: activity model from real lists — waiting items not counted; totals = completed transactions only", "see actual") {
        val txns = a.transactions(); val items = a.reviewItems().list("items").objs()
        val sc = ActivityModel.build(txns, items, a.bills(), a.pockets(), java.time.LocalDate.now(java.time.ZoneId.of("Asia/Bangkok")))
        val outExpected = txns.filter { it.str("payment_status") == "completed" && it.str("kind") !in setOf("income", "refund", "transfer_in") }
            .sumOf { it.long("amount_satang") ?: 0L }
        val ok = sc.waiting.size == items.size && sc.waiting.none { it.counted } && sc.days.sumOf { it.outSatang } == outExpected &&
            sc.days.sumOf { it.rows.size } == txns.size
        if (!ok) false else "days=${sc.days.size} rows=${txns.size} waiting=${sc.waiting.size} unpaid_bills=${sc.bills.size} out=${MoneyText.magnitude(outExpected)}"
    }

    // ---- slice 1 fix (Codex finding 1): inputs the review sheet offers are enough to resolve these items ----
    val variants = File(slipsDir).resolveSibling("review_variants")
    fun reviewFor(file: String): ReviewView {
        val up = a.upload(File(variants, file).readBytes(), "image/png", captured, expectedOwnerId = a.me())
        waitUntil { a.uploadDetail(up.uploadId).str("status") == "needs_review" }
        return ReviewView(a.reviewItems().list("items").objs().first { it.str("upload_id") == up.uploadId })
    }
    step("slice1 fix: bill without due date → user enters it in the sheet → a bill, not an expense", "bill_id, txn count unchanged") {
        val v = reviewFor("var_bill_no_due_date.png")
        val ed = v.initialInputs().toMutableMap()
        val blocked = !v.canRun(v.actions.first { it.decision == "accept" }, null, ed) && "due_date_text" in v.inputs(ed)
        ed["due_date_text"] = "2026-10-20"
        val n = a.transactions().size
        val o = ReviewResolver.classify("accept", runCatching { a.resolveReview(v.id, "accept", v.changedFields(ed)) })
        val bill = (o as? ResolveOutcome.Done)?.billId?.let { id -> a.bills().firstOrNull { it.str("id") == id } }
        blocked && o.isSuccess && bill?.str("due_date") == "2026-10-20" && a.transactions().size == n
    }
    step("slice1 fix: unknown status → user picks Completed → recorded completed and counted", "completed, counted") {
        val v = reviewFor("var_slip_status_unknown_a.png")
        val ed = v.initialInputs().toMutableMap()
        val noDefault = ed["status"] == "" && !v.canRun(v.actions.first { it.decision == "accept" }, null, ed)
        ed["status"] = "success"
        val o = ReviewResolver.classify("accept", runCatching { a.resolveReview(v.id, "accept", v.changedFields(ed)) }) as ResolveOutcome.Done
        val t = a.transactions().first { it.str("id") == o.txnId }
        val sc = ActivityModel.build(a.transactions(), emptyList(), emptyList(), a.pockets(), java.time.LocalDate.parse("2026-10-16"))
        noDefault && t.str("payment_status") == "completed" && sc.days.flatMap { it.rows }.first { it.key == "t:${o.txnId}" }.counted
    }
    step("slice1 fix: unknown status → user picks Failed → recorded failed and NOT counted", "failed, not counted") {
        val v = reviewFor("var_slip_status_unknown_b.png")
        val ed = v.initialInputs().toMutableMap(); ed["status"] = "failed"
        val o = ReviewResolver.classify("accept", runCatching { a.resolveReview(v.id, "accept", v.changedFields(ed)) }) as ResolveOutcome.Done
        val t = a.transactions().first { it.str("id") == o.txnId }
        val row = ActivityModel.build(a.transactions(), emptyList(), emptyList(), a.pockets(), java.time.LocalDate.parse("2026-10-16"))
            .days.flatMap { it.rows }.first { it.key == "t:${o.txnId}" }
        t.str("payment_status") == "failed" && !row.counted && row.tags.contains("Failed · not counted")
    }

    // ---- account switch after a session ended with photos still queued (Codex CP3a #1) ----
    step("C's session ends with 2 photos queued; D signs in on the same phone → C's photos are neither shown nor sent", "0 uploads for C and D") {
        val tokens = MemoryTokenStore()
        val c = ApiClient(base, transport, tokens, true)
        val emailC = "c-${UUID.randomUUID().toString().take(8)}@example.test"; c.signup(emailC, pw); c.login(emailC, pw)
        c.grantConsent("photo_processing", "v1", mapOf("scan_from" to "2026-07-01"))
        val st = object : QueueStore { var v: String? = null; override fun load() = v; override fun save(json: String) { v = json } }
        val bl = object : BlobStore { val m = HashMap<String, ByteArray>(); override fun put(key: String, bytes: ByteArray) { m[key] = bytes }
            override fun get(key: String) = m[key]; override fun delete(key: String) { m.remove(key) } }
        val qc = UploadQueue(st, bl, ApiUploadAdapter(c)).also { it.bindOwner(c.me()) }
        qc.enqueue(slip("slip_032_transfer_out.png"), "image/png", captured); qc.enqueue(slip("slip_033_transfer_out.png"), "image/png", captured)
        val cToken = tokens.get()
        ApiClient(base, transport, MemoryTokenStore().apply { set(cToken) }, true).logout()  // session ends server-side (e.g. expiry)
        qc.runOnce()                                                                          // → SIGNED_OUT, nothing sent
        val blockedAfterExpiry = qc.blocked == BlockReason.SIGNED_OUT
        val emailD = "d-${UUID.randomUUID().toString().take(8)}@example.test"; c.signup(emailD, pw); c.login(emailD, pw)
        c.grantConsent("photo_processing", "v1", mapOf("scan_from" to "2026-07-01"))
        val discarded = qc.bindOwner(c.me()); qc.runOnce()
        val cUploads = ApiClient(base, transport, MemoryTokenStore(), true).let { it.login(emailC, pw); it.uploads().size }
        blockedAfterExpiry && discarded == 2 && qc.snapshot().isEmpty() && bl.m.isEmpty() && c.uploads().isEmpty() && cUploads == 0
    }
    step("gate: E queued photos; F signs in; /me fails (offline) → nothing visible or sent; retry → Ready for F only", "0 visible, 0 sent, then Ready") {
        var meFails = true
        val flaky = Transport { r -> if (meFails && r.url.endsWith("/v1/me")) throw java.io.IOException("offline") else transport.send(r) }
        val tokens = MemoryTokenStore()
        val api = ApiClient(base, flaky, tokens, true)
        val st = object : QueueStore { var v: String? = null; override fun load() = v; override fun save(json: String) { v = json } }
        val bl = object : BlobStore { val m = HashMap<String, ByteArray>(); override fun put(key: String, bytes: ByteArray) { m[key] = bytes }
            override fun get(key: String) = m[key]; override fun delete(key: String) { m.remove(key) } }
        val qe = UploadQueue(st, bl, ApiUploadAdapter(api)); val gate = SessionGate(qe)
        val emailE = "e-${UUID.randomUUID().toString().take(8)}@example.test"; api.signup(emailE, pw); api.login(emailE, pw)
        meFails = false; gate.check { api.me() }; meFails = true
        gate.enqueue(slip("slip_035_transfer_out.png"), "image/png", captured)   // E's photo; E has no consent → stays queued
        gate.pumpOnce()
        api.logout()
        val emailF = "f-${UUID.randomUUID().toString().take(8)}@example.test"; api.signup(emailF, pw); api.login(emailF, pw)
        val failed = gate.check { api.me() }
        val hidden = gate.visibleEntries().isEmpty() && gate.pumpOnce() == 0 &&
            runCatching { gate.enqueue(slip("slip_036_transfer_out.png"), "image/png", captured) }.isFailure
        meFails = false
        val ready = gate.check { api.me() }
        failed is SessionState.IdentityFailed && hidden && ready is SessionState.Ready && gate.visibleEntries().isEmpty() && api.uploads().isEmpty()
    }
    step("server refuses an upload that names another account (defence in depth)", "409 OWNER_MISMATCH") {
        try { a.upload(slip("slip_034_transfer_out.png"), "image/png", captured, expectedOwnerId = UUID.randomUUID().toString()); false }
        catch (e: ApiException) { e.code == "OWNER_MISMATCH" }
    }

    // ---- second user: no auto-import consent → every slip waits for confirmation ----
    val b = ApiClient(base, transport, MemoryTokenStore(), debugBuild = true)
    val emailB = "b-${UUID.randomUUID().toString().take(8)}@example.test"
    var bResolvedItem: String? = null
    step("user B without auto-import: slip goes to review (confirm_import), accept imports it", "needs_review → imported") {
        b.signup(emailB, pw); b.login(emailB, pw)
        b.putProfile(2_000_000, "monthly", "2026-11-01", emptyList()); b.addBalance(b.accounts()[0].str("id")!!, 500_000)
        b.grantConsent("photo_processing", "v1", mapOf("scan_from" to "2026-07-01"))
        val up = b.upload(slip("slip_009_transfer_out.png"), "image/png", captured, expectedOwnerId = b.me())
        waitUntil { b.uploadDetail(up.uploadId).str("status") == "needs_review" } && run {
            val item = b.reviewItems().list("items").objs().first { it.str("upload_id") == up.uploadId }
            bResolvedItem = item.str("id")
            item.str("reason") == "confirm_import" && b.resolveReview(item.str("id")!!, "accept").str("txn_id") != null }
    }
    step("slice1: resolving an item that is no longer open → NoLongerOpen (404), never shown as success", "NoLongerOpen, txn count unchanged") {
        val n = b.transactions().size
        // the same decision sent again for the item just resolved (e.g. after a lost response): must not count as saved
        val o1 = ReviewResolver.classify("accept", runCatching { b.resolveReview(bResolvedItem!!, "accept") })
        o1 is ResolveOutcome.NoLongerOpen && !o1.isSuccess && b.transactions().size == n &&
            b.reviewItems().list("items").objs().none { it.str("id") == bResolvedItem }
    }
    step("isolation: B cannot read A's upload (404)", "404") {
        try { b.uploadDetail(bySha("slip_003_transfer_out.png").uploadId!!); false } catch (e: ApiException) { e.status == 404 }
    }
    step("revoke photo consent: queue pauses, new images are not sent, direct upload refused", "0 sent, 403") {
        a.revokeConsent("photo_processing"); q.pause(BlockReason.CONSENT_REQUIRED)
        q.enqueue(slip("slip_010_transfer_out.png"), "image/png", captured)
        val sent = q.runOnce()
        val direct = try { a.upload(slip("slip_010_transfer_out.png"), "image/png", captured); "accepted" } catch (e: ApiException) { e.code }
        sent == 0 && direct == "CONSENT_REQUIRED"
    }
    step("logout clears the local token and revokes it on the server (old token → SESSION_EXPIRED)", "signed out; old token rejected") {
        val old = tokensA.get()
        a.logout()
        val after = try { a.plan(); "ok" } catch (e: SessionExpiredException) { e.code }          // no token sent at all
        val replay = try { ApiClient(base, transport, MemoryTokenStore().apply { set(old) }, true).plan(); "ok" }
                     catch (e: SessionExpiredException) { e.code }                                // stolen/old token
        !a.isSignedIn && after == "UNAUTHENTICATED" && replay == "SESSION_EXPIRED"
    }

    val okAll = steps.all { it["ok"] == true }
    File(outDir).mkdirs()
    File(outDir, "client_e2e_steps.json").writeText(Json.write(mapOf("all_ok" to okAll, "steps" to steps)))
    println("${steps.count { it["ok"] == true }}/${steps.size} steps ok")
    if (!okAll) kotlin.system.exitProcess(1)
}
