package dev.finassist.android

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import dev.finassist.core.ApiException
import dev.finassist.core.BlockReason
import dev.finassist.core.NetworkException
import dev.finassist.core.SessionExpiredException
import dev.finassist.core.bool
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.Executors

/** UI state + the only place that talks to the network. All queue access runs on one thread (the queue is not thread-safe). */
class AppState(val app: FinAssistApp, private val scope: CoroutineScope) {
    var testMode by mutableStateOf<Boolean?>(null)
    var serverError by mutableStateOf<String?>(null)
    var signedIn by mutableStateOf(app.api.isSignedIn)
    var message by mutableStateOf<String?>(null)
    var busy by mutableStateOf(false)
    var queueTick by mutableIntStateOf(0)
        private set
    private var pumpJob: Job? = null

    companion object {
        val queueThread = Executors.newSingleThreadExecutor { r -> Thread(r, "upload-queue") }.asCoroutineDispatcher()
    }

    fun checkServer() = scope.launch {
        try {
            val h = withContext(Dispatchers.IO) { app.api.health() }
            testMode = h.bool("test_mode") == true; serverError = null
        } catch (e: Exception) {
            serverError = when (e) { is NetworkException -> "Server not reachable (${dev.finassist.android.BuildConfig.API_BASE_URL})"; else -> e.message }
        }
    }

    /** Runs [block] off the main thread and turns every failure into a visible message. Never logs content. */
    fun <T> act(block: suspend () -> T, onOk: (T) -> Unit = {}) {
        scope.launch {
            busy = true; message = null
            try {
                val r = withContext(Dispatchers.IO) { block() }
                onOk(r)
            } catch (e: SessionExpiredException) {
                app.queue.requestPause(BlockReason.SIGNED_OUT)
                signedIn = false
                message = if (e.code == "UNAUTHENTICATED") e.message else "Session ended (${e.code}). Please sign in again."
            } catch (e: ApiException) {
                val fields = e.fields.joinToString { "${it["path"]}: ${it["issue"]}" }
                message = "${e.code}: ${e.message}" + (if (fields.isNotEmpty()) " [$fields]" else "") + (e.requestId?.let { " (request $it)" } ?: "")
            } catch (e: NetworkException) {
                message = "Server not reachable. Nothing was lost; try again."
            } finally { busy = false }
        }
    }

    suspend fun <T> onQueue(block: () -> T): T = withContext(queueThread) { block() }

    fun touchQueue() { queueTick++ }

    /** Sends due images and follows their processing while there is work. One loop at a time. */
    fun pumpQueue() {
        if (pumpJob?.isActive == true) return
        pumpJob = scope.launch {
            while (true) {
                val (hasWork, blocked) = try {
                    onQueue { app.queue.runOnce(); app.queue.refresh(); app.queue.hasWork to app.queue.blocked }
                } catch (e: Exception) { false to null }
                touchQueue()
                if (blocked == BlockReason.SIGNED_OUT) { signedIn = false; message = "Session ended. Please sign in again."; break }
                if (!hasWork || blocked != null) break
                delay(2_000)
            }
        }
    }

    /**
     * After sign-in (or app start with a stored session): bind the upload queue to THIS account before anything is
     * shown or sent. A different account than the queue's owner discards the previous account's photos first
     * (Codex CP3a #1). Nothing is pumped until the binding is done.
     */
    fun signedInNow() {
        signedIn = true
        scope.launch {
            val me = try { withContext(Dispatchers.IO) { app.api.me() } } catch (e: SessionExpiredException) {
                signedIn = false; message = "Session ended. Please sign in again."; return@launch
            } catch (e: Exception) { message = "Server not reachable; uploads wait until it is."; return@launch }
            val discarded = onQueue {
                val n = app.queue.bindOwner(me)
                if (app.queue.blocked == BlockReason.SIGNED_OUT) app.queue.resume()
                n
            }
            if (discarded > 0) message = "$discarded unsent photo(s) from another account on this phone were discarded."
            touchQueue(); pumpQueue()
        }
    }

    /** Thread-safe pause: takes effect before the next image starts, even in the middle of a batch (Codex CP3a #2). */
    fun pauseQueue(reason: BlockReason) {
        app.queue.requestPause(reason)
        scope.launch { onQueue { app.queue.pause(reason) }; touchQueue() }
    }

    fun logout() = scope.launch {
        app.queue.requestPause(BlockReason.SIGNED_OUT)
        withContext(Dispatchers.IO) { app.api.logout() }
        onQueue { app.queue.clearAll() }
        signedIn = false; touchQueue(); message = "Signed out. Unsent photos on this phone were discarded."
    }
}
