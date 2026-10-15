package dev.finassist.core

import java.security.MessageDigest

/** Persisted queue state (Android: app-private SharedPreferences; tests: memory). */
interface QueueStore {
    fun load(): String?
    fun save(json: String)
}

/** Local copies of images waiting to be sent (Android: app-private noBackupFilesDir). Deleted once the server has them. */
interface BlobStore {
    fun put(key: String, bytes: ByteArray)
    fun get(key: String): ByteArray?
    fun delete(key: String)
}

/** Seam over [ApiClient] so the queue can be tested without HTTP. */
interface UploadApi {
    fun upload(bytes: ByteArray, mime: String, capturedAtIso: String?, expectedOwnerId: String, confirmedUndated: Boolean): UploadResult
    fun uploadStatus(uploadId: String): String
}

class ApiUploadAdapter(private val api: ApiClient) : UploadApi {
    override fun upload(bytes: ByteArray, mime: String, capturedAtIso: String?, expectedOwnerId: String, confirmedUndated: Boolean) =
        api.upload(bytes, mime, capturedAtIso, expectedOwnerId, confirmedUndated)
    override fun uploadStatus(uploadId: String): String = api.uploadDetail(uploadId).str("status") ?: "unknown"
}

enum class LocalState { QUEUED, UPLOADING, SENT, FAILED, GAVE_UP }

data class QueueEntry(
    val sha256: String,
    val mime: String,
    val capturedAt: String?,
    val createdAtMs: Long,
    val owner: String,
    var confirmedUndated: Boolean = false,
    var state: LocalState = LocalState.QUEUED,
    var attempts: Int = 0,
    var nextAttemptAtMs: Long = 0,
    var uploadId: String? = null,
    var serverStatus: String? = null,
    var duplicateImage: Boolean = false,
    var lastError: String? = null,
) {
    fun toMap(): Map<String, Any?> = linkedMapOf("sha256" to sha256, "mime" to mime, "captured_at" to capturedAt, "created_at_ms" to createdAtMs,
        "owner" to owner, "confirmed_undated" to confirmedUndated, "state" to state.name, "attempts" to attempts,
        "next_attempt_at_ms" to nextAttemptAtMs, "upload_id" to uploadId, "server_status" to serverStatus,
        "duplicate_image" to duplicateImage, "last_error" to lastError)

    companion object {
        fun from(m: Map<String, Any?>) = QueueEntry(m.str("sha256")!!, m.str("mime")!!, m.str("captured_at"), m.long("created_at_ms") ?: 0,
            m.str("owner") ?: "", m.bool("confirmed_undated") ?: false, LocalState.valueOf(m.str("state")!!), (m.long("attempts") ?: 0).toInt(),
            m.long("next_attempt_at_ms") ?: 0, m.str("upload_id"), m.str("server_status"), m.bool("duplicate_image") ?: false, m.str("last_error"))
    }
}

/** Why the queue is not sending. The queue never sends while blocked. */
enum class BlockReason { PAUSED_BY_USER, CONSENT_REQUIRED, SIGNED_OUT }

/**
 * Upload queue with exactly-once intent per image (by content hash), bound to ONE account:
 *  - every entry records the account it was queued for; the queue is bound to an owner and [bindOwner] with a
 *    different account discards all entries and local copies of the previous one before anything can run, so a
 *    photo of account A is never shown to or sent for account B (Codex CP3a #1). Uploads also carry the expected
 *    owner and the server refuses a mismatch (defence in depth);
 *  - enqueue of an image already in the queue returns the existing entry (no second upload);
 *  - state is persisted before every network call; after a crash/restart an UPLOADING entry goes back to QUEUED and
 *    is re-sent — the server answers 200 duplicate_image for the same sha256, so no second record exists;
 *  - transient failures (offline, 5xx, 429) back off; permanent ones (4xx) stop for that image;
 *  - CONSENT_REQUIRED, a user pause or the end of the session blocks the whole queue. [requestPause] may be called
 *    from any thread while a batch is being sent: it is checked before every request, so at most the image already
 *    in flight finishes (Codex CP3a #2).
 * Everything except [requestPause] runs on one thread (Android: a single-thread dispatcher).
 */
class UploadQueue(
    private val store: QueueStore,
    private val blobs: BlobStore,
    private val api: UploadApi,
    private val now: () -> Long = System::currentTimeMillis,
) {
    companion object {
        const val MAX_ATTEMPTS = 6
        const val BASE_BACKOFF_MS = 5_000L
        const val MAX_BACKOFF_MS = 10 * 60_000L
        val TERMINAL_SERVER = setOf("imported", "needs_review", "rejected", "merged_duplicate", "extract_failed", "cancelled_consent", "deleted")

        fun sha256Hex(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    }

    private val entries = LinkedHashMap<String, QueueEntry>()
    var blocked: BlockReason? = null
        private set
    var owner: String? = null
        private set
    @Volatile private var pauseRequested: BlockReason? = null

    init { restore() }

    private fun restore() {
        val raw = store.load() ?: return
        val m = Json.obj(raw)
        blocked = m.str("blocked")?.let { BlockReason.valueOf(it) }
        owner = m.str("owner")
        for (e in m.list("entries").objs().map(QueueEntry::from)) {
            if (e.state == LocalState.UPLOADING) { e.state = LocalState.QUEUED; e.nextAttemptAtMs = 0 } // crashed mid-send
            if (e.owner == owner) entries[e.sha256] = e else blobs.delete(e.sha256) // never keep another account's photo
        }
        persist()
    }

    private fun persist() = store.save(Json.write(mapOf("owner" to owner, "blocked" to blocked?.name, "entries" to entries.values.map { it.toMap() })))

    /** Shows only the bound account's entries (there are no others: [bindOwner] discards them). */
    fun snapshot(): List<QueueEntry> = entries.values.map { it.copy() }

    /**
     * Call with the signed-in account id (GET /v1/me) before resuming or enqueuing. Same account → keeps its queue
     * (e.g. after a session expiry and sign-in again). Different account → discards the previous account's entries
     * and local copies first. Returns how many entries were discarded.
     */
    fun bindOwner(accountId: String): Int {
        if (owner == accountId) return 0
        val n = entries.size
        entries.values.forEach { blobs.delete(it.sha256) }
        entries.clear()
        owner = accountId
        blocked = null; pauseRequested = null
        persist()
        return n
    }

    /** Explicit logout: discard everything and unbind. */
    fun clearAll() {
        entries.values.forEach { blobs.delete(it.sha256) }
        entries.clear(); owner = null; blocked = null; pauseRequested = null
        persist()
    }

    /** Returns the entry for this image, creating it only if the image is not already known. */
    fun enqueue(bytes: ByteArray, mime: String, capturedAtIso: String?, confirmedUndated: Boolean = false): QueueEntry {
        val acct = owner ?: throw IllegalStateException("queue is not bound to a signed-in account")
        val sha = sha256Hex(bytes)
        entries[sha]?.let { return it.copy() }
        blobs.put(sha, bytes)
        val e = QueueEntry(sha, mime, capturedAtIso, now(), acct, confirmedUndated = confirmedUndated && capturedAtIso == null)
        entries[sha] = e
        persist()
        return e.copy()
    }

    /** Thread-safe: takes effect before the next request starts, even in the middle of [runOnce]. */
    fun requestPause(reason: BlockReason = BlockReason.PAUSED_BY_USER) { pauseRequested = reason }

    fun pause(reason: BlockReason = BlockReason.PAUSED_BY_USER) { pauseRequested = null; blocked = reason; persist() }
    fun resume() { pauseRequested = null; blocked = null; persist() }

    /** User asks to try again an image that gave up or failed locally. */
    fun retryLocal(sha: String): Boolean {
        val e = entries[sha] ?: return false
        if (e.state != LocalState.GAVE_UP && e.state != LocalState.FAILED) return false
        if (blobs.get(sha) == null) return false
        e.state = LocalState.QUEUED; e.attempts = 0; e.nextAttemptAtMs = 0; e.lastError = null
        persist()
        return true
    }

    /** The user confirmed sending this undated photo (server answered CAPTURE_DATE_REQUIRED). */
    fun confirmUndated(sha: String): Boolean {
        val e = entries[sha] ?: return false
        if (e.capturedAt != null || e.lastError != "CAPTURE_DATE_REQUIRED") return false
        e.confirmedUndated = true
        persist()
        return retryLocal(sha)
    }

    /** Remove an entry the user discards (also its local copy). Server-side data is deleted via the API, not here. */
    fun forget(sha: String) { entries.remove(sha); blobs.delete(sha); persist() }

    /** Sends due entries, one request at a time, re-checking pause/consent/session before each. Returns how many were sent. */
    fun runOnce(): Int {
        var sent = 0
        val acct = owner ?: return 0
        for (e in entries.values.sortedBy { it.createdAtMs }) {
            pauseRequested?.let { pause(it) }
            if (blocked != null) return sent
            if (e.state != LocalState.QUEUED || e.nextAttemptAtMs > now() || e.owner != acct) continue
            val bytes = blobs.get(e.sha256)
            if (bytes == null) { e.state = LocalState.FAILED; e.lastError = "LOCAL_COPY_MISSING"; persist(); continue }
            e.state = LocalState.UPLOADING; e.attempts += 1; persist()
            try {
                val r = api.upload(bytes, e.mime, e.capturedAt, e.owner, e.confirmedUndated)
                e.state = LocalState.SENT; e.uploadId = r.uploadId; e.serverStatus = r.status; e.duplicateImage = r.duplicateImage; e.lastError = null
                persist()
                blobs.delete(e.sha256) // the server has it; keep no extra copy on the phone
                sent++
            } catch (x: NetworkException) {
                backoff(e, "NETWORK")
            } catch (x: SessionExpiredException) {
                e.state = LocalState.QUEUED; e.attempts -= 1; blocked = BlockReason.SIGNED_OUT; persist(); return sent
            } catch (x: ApiException) {
                when {
                    x.code == "CONSENT_REQUIRED" -> { e.state = LocalState.QUEUED; e.attempts -= 1; blocked = BlockReason.CONSENT_REQUIRED; persist(); return sent }
                    x.code == "OWNER_MISMATCH" -> { e.state = LocalState.FAILED; e.lastError = x.code; blocked = BlockReason.SIGNED_OUT; persist(); return sent }
                    x.retryable || x.status >= 500 || x.status == 429 -> backoff(e, x.code)
                    else -> { e.state = LocalState.FAILED; e.lastError = x.code; persist() } // OUTSIDE_CONSENTED_RANGE, CAPTURE_DATE_REQUIRED, …
                }
            }
        }
        return sent
    }

    private fun backoff(e: QueueEntry, code: String) {
        e.lastError = code
        if (e.attempts >= MAX_ATTEMPTS) { e.state = LocalState.GAVE_UP } else {
            e.state = LocalState.QUEUED
            e.nextAttemptAtMs = now() + minOf(MAX_BACKOFF_MS, BASE_BACKOFF_MS shl (e.attempts - 1))
        }
        persist()
    }

    /** Polls the server status of sent images that are still being processed. Returns entries that changed. */
    fun refresh(): List<QueueEntry> {
        val changed = mutableListOf<QueueEntry>()
        for (e in entries.values) {
            val id = e.uploadId ?: continue
            if (e.state != LocalState.SENT || e.serverStatus in TERMINAL_SERVER) continue
            val s = try { api.uploadStatus(id) } catch (x: NetworkException) { continue } catch (x: SessionExpiredException) {
                blocked = BlockReason.SIGNED_OUT; persist(); return changed
            } catch (x: ApiException) {
                if (x.status == 404) "deleted" else continue
            }
            if (s != e.serverStatus) { e.serverStatus = s; changed += e.copy() }
        }
        if (changed.isNotEmpty()) persist()
        return changed
    }

    /** After the server re-queued a failed extraction (POST /uploads/{id}/retry). */
    fun markServerRetried(sha: String) { entries[sha]?.let { it.serverStatus = "received"; persist() } }

    val hasWork: Boolean get() = entries.values.any { it.state == LocalState.QUEUED || it.state == LocalState.UPLOADING ||
            (it.state == LocalState.SENT && it.serverStatus !in TERMINAL_SERVER) }
}

/** What the user sees for an entry: local transfer state first, then the server's processing state. */
object UploadLabels {
    fun label(e: QueueEntry, blocked: BlockReason?): String = when (e.state) {
        LocalState.QUEUED -> when {
            blocked == BlockReason.CONSENT_REQUIRED -> "Waiting: photo processing is not allowed"
            blocked == BlockReason.PAUSED_BY_USER -> "Paused"
            blocked == BlockReason.SIGNED_OUT -> "Waiting: sign in again"
            e.attempts > 0 -> "Waiting to retry (${e.lastError})"
            else -> "Waiting to upload"
        }
        LocalState.UPLOADING -> "Uploading"
        LocalState.FAILED -> when (e.lastError) {
            "CAPTURE_DATE_REQUIRED" -> "This photo has no date — confirm to send it"
            "OUTSIDE_CONSENTED_RANGE" -> "Not sent: older than the date range you allowed"
            else -> "Not sent: ${e.lastError}"
        }
        LocalState.GAVE_UP -> "Upload failed after ${e.attempts} tries — tap retry"
        LocalState.SENT -> when (e.serverStatus) {
            "received", "extracting", "validated" -> "Processing"
            "imported" -> if (e.duplicateImage) "Already imported (same image)" else "Imported"
            "needs_review" -> "Needs your review"
            "extract_failed" -> "Could not read — tap retry"
            "rejected" -> "Not a transaction"
            "merged_duplicate" -> "Attached to an existing record"
            "cancelled_consent" -> "Stopped: consent withdrawn"
            "deleted" -> "Deleted"
            else -> e.serverStatus ?: "Sent"
        }
    }

    fun canRetryServer(e: QueueEntry) = e.state == LocalState.SENT && e.serverStatus in setOf("extract_failed", "cancelled_consent")
    fun canRetryLocal(e: QueueEntry) = (e.state == LocalState.GAVE_UP || e.state == LocalState.FAILED) && e.lastError != "CAPTURE_DATE_REQUIRED"
    fun needsUndatedConfirmation(e: QueueEntry) = e.state == LocalState.FAILED && e.lastError == "CAPTURE_DATE_REQUIRED"
}

/**
 * Review actions come from the server's `allowed_decisions` for the item (Codex CP3a #3). The client never offers
 * "confirm as new" for a receipt or a likely duplicate — that would count the money twice.
 */
object ReviewActions {
    data class Action(val decision: String, val label: String, val needsCandidate: Boolean)

    fun forItem(item: Map<String, Any?>): List<Action> {
        val allowed = item.list("allowed_decisions").map { it.toString() }
        val reason = item.str("reason")
        return allowed.mapNotNull { d ->
            when (d) {
                "accept" -> Action(d, if (reason == "confirm_import") "Record it" else "Confirm with these details", false)
                "link_receipt" -> Action(d, "Same purchase — attach as evidence", true)
                "duplicate_of" -> Action(d, "Same payment — do not record again", true)
                "distinct" -> Action(d, if (reason == "receipt_link") "Different purchase — record separately" else "Different payment — record it", false)
                "not_a_transaction" -> Action(d, "Not a transaction", false)
                else -> null // unknown decision from a newer server: not offered
            }
        }
    }
}
