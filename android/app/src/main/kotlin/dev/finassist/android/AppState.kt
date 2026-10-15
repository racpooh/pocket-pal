package dev.finassist.android

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import dev.finassist.core.ApiException
import dev.finassist.core.BlockReason
import dev.finassist.core.NetworkException
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
        if (err is SessionExpiredException) { onQueue { app.gate.signOut() }; message = "Session ended. Please sign in again."; return@launch }
        val applied = onQueue { app.gate.complete(epoch, me) }
        if (applied && err == null) pumpQueue()
        if (applied && err != null) message = if (err is NetworkException) "Cannot confirm your account (server not reachable)." else "Cannot confirm your account (${(err as? ApiException)?.code})."
    }

    private fun sessionEnded(text: String?) {
        app.gate.requestStop()
        scope.launch { onQueue { app.gate.signOut() } }
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
                sessionEnded(if (e.code == "UNAUTHENTICATED") e.message else "Session ended (${e.code}). Please sign in again.")
            } catch (e: ApiException) {
                val fields = e.fields.joinToString { "${it["path"]}: ${it["issue"]}" }
                message = "${e.code}: ${e.message}" + (if (fields.isNotEmpty()) " [$fields]" else "") + (e.requestId?.let { " (request $it)" } ?: "")
            } catch (e: NetworkException) {
                message = "Server not reachable. Nothing was lost; try again."
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
