package dev.finassist.android

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import dev.finassist.core.ApiException
import dev.finassist.core.BlockReason
import dev.finassist.core.NetworkException
import dev.finassist.core.ResolveOutcome
import dev.finassist.core.ReviewActions
import dev.finassist.core.ReviewResolver
import dev.finassist.core.ReviewView
import dev.finassist.core.SessionExpiredException
import dev.finassist.core.SessionState
import dev.finassist.core.UploadQueue
import dev.finassist.core.bool
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.Executors

/**
 * UI state + the only place that talks to the network. All queue access runs on one thread (the queue is not
 * thread-safe) and goes through [dev.finassist.core.SessionGate]: signed-in screens and the queue exist only in
 * [SessionState.Ready], i.e. after GET /v1/me succeeded and the queue is bound to that account (Codex CP3a re-review).
 */
class AppState(val app: FinAssistApp, private val scope: CoroutineScope) {
    var testMode by mutableStateOf<Boolean?>(null)
    var serverError by mutableStateOf<String?>(null)
    var session by mutableStateOf<SessionState>(SessionState.SignedOut)
        private set
    var message by mutableStateOf<String?>(null)
    var busy by mutableStateOf(false)
    var queueTick by mutableIntStateOf(0)
        private set
    private var pumpJob: Job? = null

    companion object {
        val queueThread = Executors.newSingleThreadExecutor { r -> Thread(r, "upload-queue") }.asCoroutineDispatcher()
    }

    init {
        app.gate.listener = { st -> scope.launch(Dispatchers.Main) { session = st; queueTick++ } }
    }

    fun checkServer() = scope.launch {
        try {
            val h = withContext(Dispatchers.IO) { app.api.health() }
            testMode = h.bool("test_mode") == true; serverError = null
        } catch (e: Exception) {
            serverError = when (e) { is NetworkException -> "Server not reachable (${BuildConfig.API_BASE_URL})"; else -> e.message }
        }
    }

    suspend fun <T> onQueue(block: () -> T): T = withContext(queueThread) { block() }

    /** The queue only when the session is Ready for the account it is bound to; otherwise null (nothing to show/do). */
    suspend fun <T> withReadyQueue(block: (UploadQueue) -> T): T? = onQueue { app.gate.readyQueue()?.let(block) }

    fun touchQueue() { queueTick++ }

    /**
     * After sign-in, or at app start with a stored token: stop the queue, confirm who is signed in, bind the queue
     * to that account, then open the app. A failed check shows a retry; a late answer of an older check is ignored.
     */
    fun checkIdentity() = scope.launch {
        if (!app.api.isSignedIn) { onQueue { app.gate.signOut() }; return@launch }
        val epoch = onQueue { app.gate.begin() }
        val me = withContext(Dispatchers.IO) { runCatching { app.api.me() } }
        val err = me.exceptionOrNull()
        // finish() checks the epoch for every outcome, including 401: a late answer of an older check changes nothing.
        val applied = onQueue { app.gate.finish(epoch, me) }
        if (!applied) return@launch
        val discarded = onQueue { app.gate.lastDiscarded }
        message = when {
            err == null && discarded > 0 -> "$discarded unsent photo(s) from another account on this phone were discarded."
            err == null -> null
            err is SessionExpiredException -> "Session ended. Please sign in again."
            err is NetworkException -> "Cannot confirm your account (server not reachable)."
            else -> "Cannot confirm your account (${(err as? ApiException)?.code})."
        }
        if (err == null) pumpQueue()
    }

    /** A 401 from any call. Ignored if it belongs to an older session (the token sent is no longer the current one). */
    private fun sessionEnded(e: SessionExpiredException, text: String?) {
        if (e.staleToken) return
        app.gate.requestStop()
        scope.launch { onQueue { app.gate.onUnauthorized(e) } }
        message = text
    }

    /** Runs [block] off the main thread and turns every failure into a visible message. Never logs content. */
    fun <T> act(block: suspend () -> T, onOk: (T) -> Unit = {}) {
        scope.launch {
            busy = true; message = null
            try {
                val r = withContext(Dispatchers.IO) { block() }
                onOk(r)
            } catch (e: SessionExpiredException) {
                sessionEnded(e, if (e.code == "UNAUTHENTICATED") e.message else "Session ended (${e.code}). Please sign in again.")
            } catch (e: ApiException) {
                val fields = e.fields.joinToString { "${it["path"]}: ${it["issue"]}" }
                message = "${e.code}: ${e.message}" + (if (fields.isNotEmpty()) " [$fields]" else "") + (e.requestId?.let { " (request $it)" } ?: "")
            } catch (e: NetworkException) {
                message = "Server not reachable. Nothing was lost; try again."
            } finally { busy = false }
        }
    }

    /**
     * Screen data with explicit Loading / Failed(retry) / Ready states. A 401 ends the session (unless it belongs to an
     * older session); every other failure becomes a visible message with Retry. Never logs content.
     */
    fun <T> load(block: suspend () -> T, quiet: Boolean = false, set: (Load<T>) -> Unit) {
        scope.launch {
            if (!quiet) set(Load.Loading)
            try {
                set(Load.Ready(withContext(Dispatchers.IO) { block() }))
            } catch (e: SessionExpiredException) {
                sessionEnded(e, "Session ended. Please sign in again."); set(Load.Failed("Session ended."))
            } catch (e: ApiException) {
                if (!quiet) set(Load.Failed("${e.message} (${e.code}${e.requestId?.let { ", request $it" } ?: ""})"))
            } catch (e: NetworkException) {
                if (!quiet) set(Load.Failed("Server not reachable. Nothing was lost — check the connection and retry."))
            } // quiet refresh: on failure the last good data stays on screen

        }
    }

    /**
     * One review decision. The outcome comes only from the server's answer: a 404 (item no longer open) or a lost
     * response is NOT reported as saved (docs/design/13 §5.2); the caller reloads the list in every non-success case.
     */
    fun resolve(view: ReviewView, action: ReviewActions.Action, edited: Map<String, String>, chosenTxn: String?,
                onResult: (ResolveOutcome) -> Unit) {
        val txn = view.txnFor(action, chosenTxn)
        if (!view.canRun(action, chosenTxn, edited)) {
            message = if (action.needsCandidate) "Choose which existing record it is first."
                      else "Fill in the marked details first: ${view.missingRequired(edited).joinToString()}"
            return
        }
        scope.launch {
            busy = true
            try {
                val fields = if (action.decision == "accept" || action.decision == "distinct") view.changedFields(edited) else null
                val r = withContext(Dispatchers.IO) { runCatching { app.api.resolveReview(view.id, action.decision, fields, txn) } }
                val outcome = ReviewResolver.classify(action.decision, r)
                message = outcome.userText()
                onResult(outcome)
                if (outcome.isSuccess) pumpQueue() // queue entries follow the server's new upload status
            } catch (e: SessionExpiredException) {
                sessionEnded(e, "Session ended. Please sign in again.")
            } catch (e: Exception) {
                message = "Unexpected error (${e::class.java.simpleName}). Nothing is shown as saved; refresh and check."
                onResult(ResolveOutcome.Unknown)
            } finally { busy = false }
        }
    }

    /** Sends due images and follows their processing while there is work and the session is Ready. One loop at a time. */
    fun pumpQueue() {
        if (pumpJob?.isActive == true) return
        pumpJob = scope.launch {
            while (true) {
                val (ready, hasWork, blocked) = try {
                    onQueue {
                        app.gate.pumpOnce()
                        val q = app.gate.readyQueue()
                        Triple(q != null, q?.hasWork == true, q?.blocked)
                    }
                } catch (e: Exception) { Triple(false, false, null) }
                touchQueue()
                if (!ready) { if (session is SessionState.SignedOut) message = "Session ended. Please sign in again."; break }
                if (!hasWork || blocked != null) break
                delay(2_000)
            }
        }
    }

    /** Thread-safe pause: takes effect before the next image starts, even in the middle of a batch (Codex CP3a #2). */
    fun pauseQueue(reason: BlockReason) {
        app.queue.requestPause(reason)
        scope.launch { withReadyQueue { it.pause(reason) }; touchQueue() }
    }

    fun logout() = scope.launch {
        app.gate.requestStop()
        onQueue { app.gate.signOut() }                 // screens close and the queue stops before the network call
        withContext(Dispatchers.IO) { app.api.logout() }
        onQueue { app.queue.clearAll() }
        touchQueue(); message = "Signed out. Unsent photos on this phone were discarded."
    }
}
