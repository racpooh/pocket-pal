package dev.finassist.core

import java.io.IOException

/**
 * Dependency-free test runner (the build environments used so far cannot download JUnit/Gradle plugins).
 * Run: gradle :core:selfTest, or kotlinc as in android/README.md. Exit code 1 on any failure.
 */
object CoreSelfTest {
    private val results = mutableListOf<Pair<String, String?>>()

    private fun test(name: String, body: () -> Unit) {
        val err = try { body(); null } catch (t: Throwable) { "${t::class.java.simpleName}: ${t.message}" }
        results += name to err
    }

    private fun eq(a: Any?, b: Any?, msg: String = "") { if (a != b) throw AssertionError("expected <$b> got <$a> $msg") }
    private fun yes(c: Boolean, msg: String) { if (!c) throw AssertionError(msg) }
    private inline fun <reified T : Throwable> throws(body: () -> Unit) {
        try { body() } catch (t: Throwable) { if (t is T) return; throw AssertionError("expected ${T::class.java.simpleName}, got $t") }
        throw AssertionError("expected ${T::class.java.simpleName}, nothing thrown")
    }

    // ---- fakes ----
    class MemStore : QueueStore { var v: String? = null; override fun load() = v; override fun save(json: String) { v = json } }
    class MemBlobs : BlobStore {
        val m = HashMap<String, ByteArray>()
        override fun put(key: String, bytes: ByteArray) { m[key] = bytes }
        override fun get(key: String) = m[key]
        override fun delete(key: String) { m.remove(key) }
    }
    class ScriptApi(val script: MutableList<() -> UploadResult>) : UploadApi {
        var calls = 0
        val owners = mutableListOf<String>()
        val undated = mutableListOf<Boolean>()
        val status = HashMap<String, String>()
        override fun upload(bytes: ByteArray, mime: String, capturedAtIso: String?, expectedOwnerId: String, confirmedUndated: Boolean): UploadResult {
            calls++; owners += expectedOwnerId; undated += confirmedUndated; return script.removeAt(0)()
        }
        override fun uploadStatus(uploadId: String) = status[uploadId] ?: "received"
    }
    private fun ok(id: String, dup: Boolean = false) = { UploadResult(if (dup) 200 else 202, id, "received", dup) }
    private fun fail(e: Exception): () -> UploadResult = { throw e }

    @JvmStatic
    fun main(args: Array<String>) {
        test("json roundtrip incl. Thai, escapes, nesting, numbers") {
            val src = mapOf("a" to "ร้านป้าสมาน \"q\" \\ \n\t", "n" to 123456789012L, "d" to 1.5, "l" to listOf(1L, null, true), "o" to mapOf("x" to false))
            eq(Json.parse(Json.write(src)), src)
            eq(Json.parse("""{"u":"ก","e":-1e2}"""), mapOf("u" to "ก", "e" to -100.0))
            throws<IllegalArgumentException> { Json.parse("{\"a\":1} x") }
            throws<IllegalArgumentException> { Json.parse("{\"a\":") }
        }
        test("money: THB text → satang like the backend; format back") {
            eq(Money.parseThb("1,234.5"), 123450L); eq(Money.parseThb("฿15,000"), 1_500_000L); eq(Money.parseThb("120.00 บาท"), 12000L)
            eq(Money.parseThb("1.234"), null); eq(Money.parseThb("-5"), null); eq(Money.parseThb("1,23"), null); eq(Money.parseThb("1e3"), null)
            eq(Money.format(123450), "฿1,234.50"); eq(Money.format(5), "฿0.05")
        }
        test("base URL policy: release HTTPS only; debug cleartext only to the developer machine") {
            eq(BaseUrlPolicy.check("https://api.example.test/", false), "https://api.example.test")
            throws<IllegalArgumentException> { BaseUrlPolicy.check("http://127.0.0.1:8000", false) }
            eq(BaseUrlPolicy.check("http://127.0.0.1:8000", true), "http://127.0.0.1:8000")
            eq(BaseUrlPolicy.check("http://10.0.2.2:8000", true), "http://10.0.2.2:8000")
            throws<IllegalArgumentException> { BaseUrlPolicy.check("http://192.168.1.20:8000", true) }
            throws<IllegalArgumentException> { BaseUrlPolicy.check("https://user:pw@api.example.test", false) }
            throws<IllegalArgumentException> { BaseUrlPolicy.check("ftp://api.example.test", true) }
        }
        test("multipart body has one file part and the captured_at field; filename is generic") {
            val (ct, body) = Multipart.build(listOf("captured_at" to "2026-10-15T13:00:00+07:00"), "image", "image", "image/png", byteArrayOf(1, 2, 3))
            val s = body.toString(Charsets.ISO_8859_1)
            yes(ct.startsWith("multipart/form-data; boundary="), ct)
            yes(s.contains("name=\"captured_at\"\r\n\r\n2026-10-15T13:00:00+07:00\r\n"), "field")
            yes(s.contains("name=\"image\"; filename=\"image\"\r\nContent-Type: image/png\r\n\r\n\u0001\u0002\u0003\r\n"), "file")
        }
        test("api: 401 clears the stored token; error envelope parsed; no token sent when signed out") {
            val tokens = MemoryTokenStore().apply { set("secret-token") }
            val seen = mutableListOf<HttpRequest>()
            val api = ApiClient("http://127.0.0.1:8000", { r -> seen += r
                HttpResponse(401, """{"error":{"code":"SESSION_EXPIRED","message":"Session expired or invalid.","request_id":"rid-1"}}""".toByteArray()) },
                tokens, debugBuild = true)
            val e = try { api.plan(); null } catch (x: SessionExpiredException) { x }
            yes(e != null && e.code == "SESSION_EXPIRED" && e.requestId == "rid-1", "session error")
            eq(tokens.get(), null, "token cleared")
            eq(seen[0].headers["Authorization"], "Bearer secret-token")
            try { api.plan() } catch (_: SessionExpiredException) {}
            eq(seen[1].headers.containsKey("Authorization"), false)
        }
        test("api: manual transaction sends an Idempotency-Key; retrying the action can reuse it") {
            val seen = mutableListOf<HttpRequest>()
            val api = ApiClient("http://127.0.0.1:8000", { r -> seen += r; HttpResponse(201, """{"id":"t1"}""".toByteArray()) },
                MemoryTokenStore().apply { set("t") }, true)
            api.createTransaction(mapOf("kind" to "expense"), "k-1"); api.createTransaction(mapOf("kind" to "expense"), "k-1")
            eq(seen.map { it.headers["Idempotency-Key"] }, listOf("k-1", "k-1"))
        }
        test("api: logout clears the token even when the server is unreachable") {
            val tokens = MemoryTokenStore().apply { set("t") }
            ApiClient("http://127.0.0.1:8000", { throw IOException("offline") }, tokens, true).logout()
            eq(tokens.get(), null)
        }
        test("api: offline becomes NetworkException, 5xx is retryable, 4xx is not") {
            val api = ApiClient("http://127.0.0.1:8000", { throw IOException("x") }, MemoryTokenStore(), true)
            throws<NetworkException> { api.health() }
            val a5 = ApiClient("http://127.0.0.1:8000", { HttpResponse(503, "oops".toByteArray()) }, MemoryTokenStore(), true)
            val e5 = try { a5.health(); null } catch (x: ApiException) { x }
            yes(e5!!.retryable && e5.code == "HTTP_503", "5xx")
            val a4 = ApiClient("http://127.0.0.1:8000", { HttpResponse(403, """{"error":{"code":"CONSENT_REQUIRED","message":"m","retryable":false}}""".toByteArray()) }, MemoryTokenStore(), true)
            val e4 = try { a4.health(); null } catch (x: ApiException) { x }
            yes(!e4!!.retryable && e4.code == "CONSENT_REQUIRED", "4xx")
        }

        // ---- upload queue ----
        test("queue: same image enqueued twice → one entry, one upload; local copy deleted once sent") {
            val blobs = MemBlobs(); val api = ScriptApi(mutableListOf(ok("u1")))
            val q = UploadQueue(MemStore(), blobs, api) { 1000 }.also { it.bindOwner("A") }
            val a = q.enqueue(byteArrayOf(9, 9), "image/png", null); val b = q.enqueue(byteArrayOf(9, 9), "image/png", null)
            eq(a.sha256, b.sha256); eq(q.snapshot().size, 1)
            eq(q.runOnce(), 1); eq(q.runOnce(), 0); eq(api.calls, 1)
            eq(q.snapshot()[0].state, LocalState.SENT); eq(blobs.m.isEmpty(), true)
        }
        test("queue: restart after a crash mid-upload re-sends; server duplicate answer → still one record") {
            val store = MemStore(); val blobs = MemBlobs()
            val crash = ScriptApi(mutableListOf({ throw IllegalStateException("process killed") }))
            val q1 = UploadQueue(store, blobs, crash) { 1000 }.also { it.bindOwner("A") }
            q1.enqueue(byteArrayOf(1), "image/png", null)
            try { q1.runOnce() } catch (_: IllegalStateException) {}
            yes(store.v!!.contains("UPLOADING"), "persisted before network call")
            val api2 = ScriptApi(mutableListOf(ok("u1", dup = true)))
            val q2 = UploadQueue(store, blobs, api2) { 2000 } // app restarted
            eq(q2.snapshot()[0].state, LocalState.QUEUED)
            eq(q2.runOnce(), 1); eq(q2.snapshot()[0].uploadId, "u1"); eq(q2.snapshot()[0].duplicateImage, true)
        }
        test("queue: transient errors back off, then succeed; repeated runs before the backoff do nothing") {
            var t = 0L
            val api = ScriptApi(mutableListOf(fail(NetworkException(IOException())), fail(ApiException(503, "HTTP_503", "x", retryable = true)), ok("u1")))
            val q = UploadQueue(MemStore(), MemBlobs(), api) { t }.also { it.bindOwner("A") }
            q.enqueue(byteArrayOf(2), "image/png", null)
            q.runOnce(); eq(q.snapshot()[0].nextAttemptAtMs, 5_000L); q.runOnce(); eq(api.calls, 1)
            t = 5_000; q.runOnce(); eq(q.snapshot()[0].nextAttemptAtMs, 15_000L)
            t = 15_000; eq(q.runOnce(), 1); eq(api.calls, 3)
        }
        test("queue: gives up after MAX_ATTEMPTS; manual retry restarts") {
            var t = 0L
            val api = ScriptApi(MutableList(UploadQueue.MAX_ATTEMPTS) { fail(NetworkException(IOException())) }.also { it += ok("u9") })
            val q = UploadQueue(MemStore(), MemBlobs(), api) { t }.also { it.bindOwner("A") }
            val e = q.enqueue(byteArrayOf(3), "image/png", null)
            repeat(UploadQueue.MAX_ATTEMPTS) { t += 3_600_000; q.runOnce() }
            eq(q.snapshot()[0].state, LocalState.GAVE_UP)
            yes(q.retryLocal(e.sha256), "retry allowed"); eq(q.runOnce(), 1)
        }
        test("queue: CONSENT_REQUIRED blocks the whole queue; nothing is sent until resume") {
            val api = ScriptApi(mutableListOf(fail(ApiException(403, "CONSENT_REQUIRED", "x")), ok("u1"), ok("u2")))
            val q = UploadQueue(MemStore(), MemBlobs(), api) { 0 }.also { it.bindOwner("A") }
            q.enqueue(byteArrayOf(4), "image/png", null); q.enqueue(byteArrayOf(5), "image/png", null)
            eq(q.runOnce(), 0); eq(q.blocked, BlockReason.CONSENT_REQUIRED); eq(api.calls, 1)
            eq(q.runOnce(), 0); eq(api.calls, 1)
            q.resume(); eq(q.runOnce(), 2)
        }
        test("queue: user pause persists across restart and blocks sending") {
            val store = MemStore(); val api = ScriptApi(mutableListOf(ok("u1")))
            val q = UploadQueue(store, MemBlobs(), api) { 0 }.also { it.bindOwner("A") }
            q.enqueue(byteArrayOf(6), "image/png", null); q.pause()
            val q2 = UploadQueue(store, MemBlobs().apply { put(q.snapshot()[0].sha256, byteArrayOf(6)) }, api) { 0 }.also { it.bindOwner("A") }
            eq(q2.blocked, BlockReason.PAUSED_BY_USER); eq(q2.runOnce(), 0); eq(api.calls, 0)
        }
        test("queue: session expiry stops sending without burning attempts") {
            val api = ScriptApi(mutableListOf(fail(SessionExpiredException("SESSION_EXPIRED", "x", null))))
            val q = UploadQueue(MemStore(), MemBlobs(), api) { 0 }.also { it.bindOwner("A") }
            q.enqueue(byteArrayOf(7), "image/png", null)
            q.runOnce(); eq(q.blocked, BlockReason.SIGNED_OUT); eq(q.snapshot()[0].attempts, 0)
        }
        test("queue: permanent 4xx fails only that image and keeps the local copy for an explicit retry/discard") {
            val blobs = MemBlobs()
            val api = ScriptApi(mutableListOf(fail(ApiException(403, "OUTSIDE_CONSENTED_RANGE", "x")), ok("u2")))
            val q = UploadQueue(MemStore(), blobs, api) { 0 }.also { it.bindOwner("A") }
            val a = q.enqueue(byteArrayOf(8), "image/png", "2026-01-01T00:00:00+07:00"); q.enqueue(byteArrayOf(10), "image/png", null)
            eq(q.runOnce(), 1)
            eq(q.snapshot().first { it.sha256 == a.sha256 }.state, LocalState.FAILED)
            yes(blobs.get(a.sha256) != null, "kept until discarded"); q.forget(a.sha256); eq(blobs.get(a.sha256), null)
        }
        test("queue: refresh follows server status to a terminal state; labels") {
            val api = ScriptApi(mutableListOf(ok("u1")))
            val q = UploadQueue(MemStore(), MemBlobs(), api) { 0 }.also { it.bindOwner("A") }
            q.enqueue(byteArrayOf(11), "image/png", null); q.runOnce()
            api.status["u1"] = "needs_review"
            eq(q.refresh().size, 1); eq(q.refresh().size, 0)
            eq(UploadLabels.label(q.snapshot()[0], null), "Needs your review")
            eq(q.hasWork, false)
        }

        // ---- Codex CP3a review ----
        test("#1 owner: A's photos are discarded (never sent or shown) when B signs in after A's session expired") {
            val store = MemStore(); val blobs = MemBlobs()
            val api = ScriptApi(mutableListOf(fail(SessionExpiredException("SESSION_EXPIRED", "x", null)), ok("b1")))
            val q = UploadQueue(store, blobs, api) { 0 }.also { it.bindOwner("A") }
            q.enqueue(byteArrayOf(20), "image/png", "2026-10-15T13:00:00+07:00"); q.enqueue(byteArrayOf(21), "image/png", "2026-10-15T13:00:00+07:00")
            q.runOnce(); eq(q.blocked, BlockReason.SIGNED_OUT)                     // A's session ended with 2 photos waiting
            val restarted = UploadQueue(store, blobs, api) { 0 }                    // app may also have been restarted
            eq(restarted.snapshot().size, 2)
            eq(restarted.bindOwner("B"), 2)                                         // B signs in → A's entries discarded first
            eq(restarted.snapshot(), emptyList<QueueEntry>()); eq(blobs.m.isEmpty(), true)
            eq(restarted.runOnce(), 0); eq(api.calls, 1)                            // nothing of A's is ever sent with B's token
            restarted.enqueue(byteArrayOf(22), "image/png", "2026-10-15T13:00:00+07:00"); eq(restarted.runOnce(), 1)
            eq(api.owners, listOf("A", "B"))                                        // each request names its account
            eq(UploadQueue(store, blobs, api) { 0 }.snapshot().all { it.owner == "B" }, true)
        }
        test("#1 owner: same account signing in again keeps its queue; unbound queue sends nothing") {
            val store = MemStore(); val api = ScriptApi(mutableListOf(ok("a1")))
            val unbound = UploadQueue(store, MemBlobs(), api) { 0 }
            throws<IllegalStateException> { unbound.enqueue(byteArrayOf(1), "image/png", null) }
            eq(unbound.runOnce(), 0)
            val blobs = MemBlobs(); val q = UploadQueue(store, blobs, api) { 0 }.also { it.bindOwner("A") }
            q.enqueue(byteArrayOf(23), "image/png", "2026-10-15T13:00:00+07:00"); q.pause(BlockReason.SIGNED_OUT)
            eq(q.bindOwner("A"), 0); eq(q.snapshot().size, 1); q.resume(); eq(q.runOnce(), 1)
            q.clearAll(); eq(q.owner, null); eq(q.snapshot().size, 0)
        }
        test("#2 pause requested while the first upload is in flight → the second never starts") {
            val inFlight = java.util.concurrent.CountDownLatch(1); val release = java.util.concurrent.CountDownLatch(1)
            var q: UploadQueue? = null
            val api = object : UploadApi {
                var calls = 0
                override fun upload(bytes: ByteArray, mime: String, capturedAtIso: String?, expectedOwnerId: String, confirmedUndated: Boolean): UploadResult {
                    calls++; inFlight.countDown(); release.await(); return UploadResult(202, "u$calls", "received", false)
                }
                override fun uploadStatus(uploadId: String) = "received"
            }
            q = UploadQueue(MemStore(), MemBlobs(), api) { 0 }.also { it.bindOwner("A") }
            q.enqueue(byteArrayOf(30), "image/png", "2026-10-15T13:00:00+07:00"); q.enqueue(byteArrayOf(31), "image/png", "2026-10-15T13:00:00+07:00")
            val worker = Thread { q.runOnce() }.apply { start() }                // the queue thread
            yes(inFlight.await(5, java.util.concurrent.TimeUnit.SECONDS), "first upload started")
            q.requestPause()                                                      // the UI thread, mid-request
            release.countDown(); worker.join(5_000)
            eq(api.calls, 1); eq(q.blocked, BlockReason.PAUSED_BY_USER)
            eq(q.snapshot().map { it.state }.sorted(), listOf(LocalState.QUEUED, LocalState.SENT))
        }
        test("undated photo: server asks for confirmation; only an explicit confirm sends it, with the flag") {
            val api = ScriptApi(mutableListOf(fail(ApiException(422, "CAPTURE_DATE_REQUIRED", "x")), ok("u1")))
            val q = UploadQueue(MemStore(), MemBlobs(), api) { 0 }.also { it.bindOwner("A") }
            val e = q.enqueue(byteArrayOf(40), "image/png", null)
            q.runOnce(); val s1 = q.snapshot()[0]
            yes(UploadLabels.needsUndatedConfirmation(s1) && !UploadLabels.canRetryLocal(s1), "asks, plain retry not offered")
            eq(q.runOnce(), 0)                                                    // not re-sent by itself
            yes(q.confirmUndated(e.sha256), "confirmed"); eq(q.runOnce(), 1); eq(api.undated, listOf(false, true))
            val dated = q.enqueue(byteArrayOf(41), "image/png", "2026-10-15T13:00:00+07:00", confirmedUndated = true)
            eq(dated.confirmedUndated, false)                                     // the flag is meaningless with a date
        }
        test("#3 review actions follow the server: receipt/duplicate items never offer 'accept'") {
            val receipt = mapOf("reason" to "receipt_link", "allowed_decisions" to listOf("link_receipt", "distinct", "not_a_transaction"))
            eq(ReviewActions.forItem(receipt).map { it.decision }, listOf("link_receipt", "distinct", "not_a_transaction"))
            yes(ReviewActions.forItem(receipt).first().needsCandidate, "link needs the candidate")
            val dup = mapOf("reason" to "possible_duplicate", "allowed_decisions" to listOf("duplicate_of", "distinct", "not_a_transaction"))
            yes(ReviewActions.forItem(dup).none { it.decision == "accept" }, "no accept")
            eq(ReviewActions.forItem(mapOf("reason" to "x", "allowed_decisions" to listOf("teleport"))), emptyList<ReviewActions.Action>())
        }

        // ---- Codex CP3a re-review: nothing of the queue before identity is confirmed ----
        test("gate: A has a queue → B signs in → /me fails → A's queue hidden, no enqueue, no send → retry ok → Ready for B") {
            val store = MemStore(); val blobs = MemBlobs(); val api = ScriptApi(mutableListOf(ok("b1")))
            val q = UploadQueue(store, blobs, api) { 0 }.also { it.bindOwner("A") }
            q.enqueue(byteArrayOf(50), "image/png", "2026-10-15T13:00:00+07:00")  // A's photo waiting
            val gate = SessionGate(q)
            val e = gate.begin()                                                    // B just signed in
            yes(gate.state is SessionState.Checking, "checking")
            eq(gate.readyQueue(), null); eq(gate.visibleEntries(), emptyList<QueueEntry>())
            throws<IllegalStateException> { gate.enqueue(byteArrayOf(51), "image/png", "2026-10-15T13:00:00+07:00") }
            eq(gate.pumpOnce(), 0); eq(q.runOnce(), 0); eq(api.calls, 0)          // even a direct run sends nothing (queue stopped)
            gate.complete(e, Result.failure(NetworkException(java.io.IOException("offline"))))
            yes(gate.state is SessionState.IdentityFailed, "identity failed"); eq(gate.visibleEntries(), emptyList<QueueEntry>())
            eq(gate.pumpOnce(), 0); eq(api.calls, 0)
            eq(gate.check { "B" }, SessionState.Ready(2, "B"))                       // retry succeeds
            eq(gate.visibleEntries(), emptyList<QueueEntry>()); eq(blobs.m.isEmpty(), true) // A's photo discarded, never shown
            eq(gate.lastDiscarded, 1)                                               // the app shows "1 unsent photo(s) … discarded"
            gate.enqueue(byteArrayOf(51), "image/png", "2026-10-15T13:00:00+07:00"); eq(gate.pumpOnce(), 1); eq(api.owners, listOf("B"))
        }
        test("gate: a late /me answer from an earlier session cannot bind the queue (after logout or account switch)") {
            val q = UploadQueue(MemStore(), MemBlobs(), ScriptApi(mutableListOf())) { 0 }.also { it.bindOwner("A") }
            q.enqueue(byteArrayOf(60), "image/png", "2026-10-15T13:00:00+07:00")
            val gate = SessionGate(q)
            val e1 = gate.begin()                                                   // check for B starts…
            gate.signOut()                                                          // …user logs out before /me returns
            eq(gate.complete(e1, Result.success("B")), false); eq(gate.state, SessionState.SignedOut); eq(q.owner, "A")
            val e2 = gate.begin()                                                   // C signs in
            eq(gate.complete(e1, Result.success("B")), false); eq(q.owner, "A")     // B's late answer still ignored
            eq(gate.complete(e2, Result.success("C")), true); eq(gate.state, SessionState.Ready(e2, "C")); eq(q.snapshot(), emptyList<QueueEntry>())
        }
        test("gate: session end while Ready stops the queue and hides it; same account re-check keeps its photos") {
            val api = ScriptApi(mutableListOf(fail(SessionExpiredException("SESSION_EXPIRED", "x", null)), ok("a1")))
            val q = UploadQueue(MemStore(), MemBlobs(), api) { 0 }
            val gate = SessionGate(q); gate.check { "A" }
            gate.enqueue(byteArrayOf(70), "image/png", "2026-10-15T13:00:00+07:00")
            gate.pumpOnce(); eq(gate.state, SessionState.SignedOut); eq(gate.visibleEntries(), emptyList<QueueEntry>())
            gate.check { "A" }; eq(gate.visibleEntries().size, 1); eq(gate.pumpOnce(), 1)
            gate.readyQueue()!!.pause(BlockReason.PAUSED_BY_USER); gate.signOut(); gate.check { "A" }
            eq(gate.readyQueue()!!.blocked, BlockReason.PAUSED_BY_USER)  // the user's own pause survives a re-check
        }

        // ---- Codex CP3a re-review 2: a late 401 of an older session must not end the new one ----
        test("late 401 of A's /me after B is Ready: B's token stays, gate stays Ready(B), queue stays B's") {
            val tokens = MemoryTokenStore().apply { set("tokA") }
            val aInFlight = java.util.concurrent.CountDownLatch(1); val releaseA = java.util.concurrent.CountDownLatch(1)
            val transport = Transport { r ->
                when (r.headers["Authorization"]) {
                    "Bearer tokA" -> { aInFlight.countDown(); releaseA.await()
                        HttpResponse(401, """{"error":{"code":"SESSION_EXPIRED","message":"expired"}}""".toByteArray()) }
                    "Bearer tokB" -> HttpResponse(200, """{"user_id":"B"}""".toByteArray())
                    else -> HttpResponse(401, """{"error":{"code":"UNAUTHENTICATED","message":"x"}}""".toByteArray())
                }
            }
            val api = ApiClient("http://127.0.0.1:8000", transport, tokens, true)
            val q = UploadQueue(MemStore(), MemBlobs(), ScriptApi(mutableListOf())) { 0 }
            val gate = SessionGate(q)
            val e1 = gate.begin()                                                         // check for A starts
            var lateA: Result<String>? = null
            val t = Thread { lateA = runCatching { api.me() } }.apply { start() }
            yes(aInFlight.await(5, java.util.concurrent.TimeUnit.SECONDS), "A's /me in flight")
            tokens.set("tokB")                                                            // B signs in
            eq(gate.check { api.me() }, SessionState.Ready(e1 + 1, "B"))
            releaseA.countDown(); t.join(5_000)                                           // A's /me now answers 401
            val err = lateA!!.exceptionOrNull() as SessionExpiredException
            yes(err.staleToken, "401 recognised as belonging to the old session")
            eq(tokens.get(), "tokB")                                                      // API client did not clear B's token
            eq(gate.finish(e1, lateA!!), false)                                           // app layer ignores it (epoch + stale)
            eq(gate.state, SessionState.Ready(e1 + 1, "B")); eq(q.owner, "B")
        }
        test("each layer alone: client keeps a newer token; gate ignores an old-epoch 401; queue not stopped by a stale 401") {
            val tokens = MemoryTokenStore().apply { set("new") }
            eq(tokens.clearIf("old"), false); eq(tokens.get(), "new"); eq(tokens.clearIf("new"), true); eq(tokens.get(), null)
            val q = UploadQueue(MemStore(), MemBlobs(), ScriptApi(mutableListOf(
                fail(SessionExpiredException("SESSION_EXPIRED", "x", null, staleToken = true)), ok("u1")))) { 0 }
            val gate = SessionGate(q)
            val e1 = gate.begin(); gate.check { "B" }
            eq(gate.finish(e1, Result.failure(SessionExpiredException("SESSION_EXPIRED", "x", null, staleToken = false))), false)
            yes(gate.state is SessionState.Ready, "still ready")
            eq(gate.onUnauthorized(SessionExpiredException("SESSION_EXPIRED", "x", null, staleToken = true)), false)
            yes(gate.state is SessionState.Ready, "still ready after stale 401 elsewhere")
            gate.enqueue(byteArrayOf(80), "image/png", "2026-10-15T13:00:00+07:00")
            eq(gate.pumpOnce(), 0); eq(q.blocked, null); yes(gate.state is SessionState.Ready, "stale upload 401 does not sign out")
            eq(gate.pumpOnce(), 1)                                                        // next round sends with the current token
            eq(gate.onUnauthorized(SessionExpiredException("SESSION_EXPIRED", "x", null)), true); eq(gate.state, SessionState.SignedOut)
        }

        val failed = results.filter { it.second != null }
        results.forEach { (n, e) -> println((if (e == null) "PASS " else "FAIL ") + n + (e?.let { "\n     $it" } ?: "")) }
        println("${results.size - failed.size}/${results.size} passed")
        if (failed.isNotEmpty()) kotlin.system.exitProcess(1)
    }
}
