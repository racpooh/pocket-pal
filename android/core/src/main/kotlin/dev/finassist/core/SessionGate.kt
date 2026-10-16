package dev.finassist.core

/** What the app may show. Only [Ready] opens the signed-in screens and the upload queue (Codex CP3a re-review). */
sealed class SessionState {
    object SignedOut : SessionState()
    data class Checking(val epoch: Int) : SessionState()
    data class IdentityFailed(val epoch: Int, val reason: String) : SessionState()
    data class Ready(val epoch: Int, val owner: String) : SessionState()
}

/**
 * Gate between a session token and the per-account upload queue.
 *
 *  - [begin] (after sign-in, or at app start with a stored token) stops the queue at once and enters [SessionState.Checking];
 *    nothing of the queue is visible or usable until `GET /v1/me` succeeds and the queue is bound to that account.
 *  - [complete] applies a `/me` result only if it belongs to the CURRENT check (epoch). A late answer from an earlier
 *    session — after logout or a switch to another account — is ignored and cannot bind the queue.
 *  - identity failure → [SessionState.IdentityFailed]: queue stays stopped and hidden; [check] again to retry.
 *  - [signOut] (logout, 401 anywhere) stops the queue and invalidates any check in flight.
 * All methods run on the queue thread (the queue is single-threaded), except [requestStop], which is thread-safe.
 */
class SessionGate(private val queue: UploadQueue) {
    @Volatile var state: SessionState = SessionState.SignedOut
        private set
    private var epoch = 0
    var listener: ((SessionState) -> Unit)? = null
    /** How many queued photos of a previous account were discarded by the last successful check (for a visible notice). */
    var lastDiscarded = 0
        private set

    private fun set(s: SessionState) { state = s; listener?.invoke(s) }

    /** Thread-safe: stop sending immediately (used from the UI thread before the queue thread gets to [signOut]). */
    fun requestStop() = queue.requestPause(BlockReason.SIGNED_OUT)

    /** Stop sending; keep a stronger reason the user chose (their own pause, or withdrawn consent) so it survives re-checks. */
    private fun stopQueue() {
        if (queue.blocked == null) { queue.requestPause(BlockReason.SIGNED_OUT); queue.pause(BlockReason.SIGNED_OUT) }
    }

    fun begin(): Int {
        epoch += 1
        stopQueue()
        set(SessionState.Checking(epoch))
        return epoch
    }

    /** Returns true if this result was applied (it belonged to the current check). */
    fun complete(forEpoch: Int, me: Result<String>): Boolean {
        val s = state
        if (forEpoch != epoch || s !is SessionState.Checking) return false // stale: logout or another sign-in happened since
        me.fold(
            onSuccess = { id ->
                lastDiscarded = queue.bindOwner(id)         // another account's entries are discarded here
                if (queue.blocked == BlockReason.SIGNED_OUT) queue.resume()
                set(SessionState.Ready(epoch, id))
            },
            onFailure = { e -> set(SessionState.IdentityFailed(epoch, (e as? ApiException)?.code ?: e::class.java.simpleName)) },
        )
        return true
    }

    /**
     * Apply the outcome of the `/me` call of check [forEpoch]. A 401 ends the session ONLY if it belongs to the
     * current check and was for the current token; a late 401 of an earlier session is ignored entirely
     * (Codex CP3a re-review 2). Everything else goes to [complete]. Returns true if applied.
     */
    fun finish(forEpoch: Int, me: Result<String>): Boolean {
        val err = me.exceptionOrNull()
        if (err is SessionExpiredException) {
            if (err.staleToken || forEpoch != epoch || state !is SessionState.Checking) return false
            signOut(); return true
        }
        return complete(forEpoch, me)
    }

    /** A 401 seen outside an identity check (any API call). Ends the session unless it belongs to an older token. */
    fun onUnauthorized(e: SessionExpiredException): Boolean {
        if (e.staleToken) return false
        signOut(); return true
    }

    /** begin + /me + finish, synchronously (callers run it off the main thread). */
    fun check(me: () -> String): SessionState {
        val e = begin()
        finish(e, runCatching(me))
        return state
    }

    fun signOut() {
        epoch += 1
        stopQueue()
        set(SessionState.SignedOut)
    }

    /** The queue, only when the session is Ready and the queue is bound to that same account. */
    fun readyQueue(): UploadQueue? {
        val s = state as? SessionState.Ready ?: return null
        return queue.takeIf { it.owner == s.owner }
    }

    fun visibleEntries(): List<QueueEntry> = readyQueue()?.snapshot() ?: emptyList()

    fun enqueue(bytes: ByteArray, mime: String, capturedAtIso: String?, confirmedUndated: Boolean = false): QueueEntry =
        (readyQueue() ?: throw IllegalStateException("account not confirmed yet")).enqueue(bytes, mime, capturedAtIso, confirmedUndated)

    /** One send + status pass, only when Ready. */
    fun pumpOnce(): Int {
        val q = readyQueue() ?: return 0
        val n = q.runOnce(); q.refresh()
        if (q.blocked == BlockReason.SIGNED_OUT) signOut()
        return n
    }
}
