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
    fun upload(bytes: ByteArray, mime: String, capturedAtIso: String?): UploadResult
    fun uploadStatus(uploadId: String): String
}

class ApiUploadAdapter(private val api: ApiClient) : UploadApi {
    override fun upload(bytes: ByteArray, mime: String, capturedAtIso: String?) = api.upload(bytes, mime, capturedAtIso)
    override fun uploadStatus(uploadId: String): String = api.uploadDetail(uploadId).str("status") ?: "unknown"
}

enum class LocalState { QUEUED, UPLOADING, SENT, FAILED, GAVE_UP }

data class QueueEntry(
    val sha256: String,
    val mime: String,
    val capturedAt: String?,
    val createdAtMs: Long,
    var state: LocalState = LocalState.QUEUED,
    var attempts: Int = 0,
    var nextAttemptAtMs: Long = 0,
    var uploadId: String? = null,
    var serverStatus: String? = null,
    var duplicateImage: Boolean = false,
    var lastError: String? = null,
) {
    fun toMap(): Map<String, Any?> = linkedMapOf("sha256" to sha256, "mime" to mime, "captured_at" to capturedAt, "created_at_ms" to createdAtMs,
        "state" to state.name, "attempts" to attempts, "next_attempt_at_ms" to nextAttemptAtMs, "upload_id" to uploadId,
        "server_status" to serverStatus, "duplicate_image" to duplicateImage, "last_error" to lastError)

    companion object {
        fun from(m: Map<String, Any?>) = QueueEntry(m.str("sha256")!!, m.str("mime")!!, m.str("captured_at"), m.long("created_at_ms") ?: 0,
            LocalState.valueOf(m.str("state")!!), (m.long("attempts") ?: 0).toInt(), m.long("next_attempt_at_ms") ?: 0, m.str("upload_id"),
            m.str("server_status"), m.bool("duplicate_image") ?: false, m.str("last_error"))
    }
}

/** Why the queue is not sending. The queue never sends while blocked. */
enum class BlockReason { PAUSED_BY_USER, CONSENT_REQUIRED, SIGNED_OUT }

/**
 * Upload queue with exactly-once intent per image (by content hash):
 *  - enqueue of an image already in the queue returns the existing entry (no second upload);
 *  - state is persisted before every network call; after a crash/restart an UPLOADING entry goes back to QUEUED and
 *    is re-sent — the server then answers 200 duplicate_image for the same sha256, so no second record exists;
 *  - transient failures (offline, 5xx, 429) back off; permanent ones (4xx) stop for that image;
 *  - CONSENT_REQUIRED or a user pause blocks the whole queue: nothing new is sent until [resume].
 * Not thread-safe by design: callers run [runOnce]/[refresh] from one worker at a time (Android: one coroutine / one
 * unique WorkManager job).
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

    init { restore() }

    private fun restore() {
        val raw = store.load() ?: return
        val m = Json.obj(raw)
        blocked = m.str("blocked")?.let { BlockReason.valueOf(it) }
        for (e in m.list("entries").objs().map(QueueEntry::from)) {
            if (e.state == LocalState.UPLOADING) { e.state = LocalState.QUEUED; e.nextAttemptAtMs = 0 } // crashed mid-send
            entries[e.sha256] = e
        }
        persist()
    }

    private fun persist() = store.save(Json.write(mapOf("blocked" to blocked?.name, "entries" to entries.values.map { it.toMap() })))

    fun snapshot(): List<QueueEntry> = entries.values.map { it.copy() }

    /** Returns the entry for this image, creating it only if the image is not already known. */
    fun enqueue(bytes: ByteArray, mime: String, capturedAtIso: String?): QueueEntry {
        val sha = sha256Hex(bytes)
        entries[sha]?.let { return it.copy() }
        blobs.put(sha, bytes)
        val e = QueueEntry(sha, mime, capturedAtIso, now())
        entries[sha] = e
        persist()
        return e.copy()
    }

    fun pause(reason: BlockReason = BlockReason.PAUSED_BY_USER) { blocked = reason; persist() }
    fun resume() { blocked = null; persist() }

    /** User asks to try again an image that gave up or failed locally. */
    fun retryLocal(sha: String): Boolean {
        val e = entries[sha] ?: return false
        if (e.state != LocalState.GAVE_UP && e.state != LocalState.FAILED) return false
        if (blobs.get(sha) == null) return false
        e.state = LocalState.QUEUED; e.attempts = 0; e.nextAttemptAtMs = 0; e.lastError = null
        persist()
        return true
    }

    /** Remove an entry the user discards (also its local copy). Server-side data is deleted via the API, not here. */
    fun forget(sha: String) { entries.remove(sha); blobs.delete(sha); persist() }

    /** Sends every due entry once. Returns how many were sent. Stops at the first queue-wide block. */
    fun runOnce(): Int {
        var sent = 0
        if (blocked != null) return 0
        for (e in entries.values.sortedBy { it.createdAtMs }) {
            if (e.state != LocalState.QUEUED || e.nextAttemptAtMs > now()) continue
            val bytes = blobs.get(e.sha256)
            if (bytes == null) { e.state = LocalState.FAILED; e.lastError = "LOCAL_COPY_MISSING"; persist(); continue }
            e.state = LocalState.UPLOADING; e.attempts += 1; persist()
            try {
                val r = api.upload(bytes, e.mime, e.capturedAt)
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
                    x.retryable || x.status >= 500 || x.status == 429 -> backoff(e, x.code)
                    else -> { e.state = LocalState.FAILED; e.lastError = x.code; persist() } // e.g. OUTSIDE_CONSENTED_RANGE, UPLOAD_TOO_LARGE
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
            val s = try { api.uploadStatus(id) } catch (x: NetworkException) { continue } catch (x: ApiException) {
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
        LocalState.FAILED -> "Not sent: ${e.lastError}"
        LocalState.GAVE_UP -> "Upload failed after ${e.attempts} tries — tap retry"
        LocalState.SENT -> when (e.serverStatus) {
            "received", "extracting", "validated" -> "Processing"
            "imported" -> if (e.duplicateImage) "Already imported (same image)" else "Imported"
            "needs_review" -> "Needs your review"
            "extract_failed" -> "Could not read — tap retry"
            "rejected" -> "Not a transaction"
            "merged_duplicate" -> "Duplicate of an existing record"
            "cancelled_consent" -> "Stopped: consent withdrawn"
            "deleted" -> "Deleted"
            else -> e.serverStatus ?: "Sent"
        }
    }

    fun canRetryServer(e: QueueEntry) = e.state == LocalState.SENT && e.serverStatus in setOf("extract_failed", "cancelled_consent")
    fun canRetryLocal(e: QueueEntry) = e.state == LocalState.GAVE_UP || e.state == LocalState.FAILED
}
