package dev.finassist.core

import java.io.IOException
import java.net.URLEncoder
import java.util.UUID

/** Backend error envelope (docs/design/05 §2). Never contains submitted values. */
open class ApiException(
    val status: Int,
    val code: String,
    message: String,
    val requestId: String? = null,
    val retryable: Boolean = false,
    val details: Map<String, Any?> = emptyMap(),
    val fields: List<Map<String, Any?>> = emptyList(),
) : Exception(message)

/**
 * 401 for the token that was sent. If that token is still the current one it has been cleared ([staleToken] = false).
 * If the session changed while the request was in flight (logout, another account signed in), the 401 belongs to an
 * old session: the current token is left untouched and [staleToken] = true — callers must not end the new session.
 */
class SessionExpiredException(code: String, message: String, requestId: String?, val staleToken: Boolean = false) :
    ApiException(401, code, message, requestId)

/** No HTTP response at all (offline, timeout). Always safe to retry. */
class NetworkException(cause: IOException) : Exception("network unavailable", cause)

/** Where the session token lives. Android: Keystore-encrypted storage. Implementations must never log the value. */
interface TokenStore {
    fun get(): String?
    fun set(token: String?)
    /** Atomically clears the token only if it is still [expected]. Returns true if it was cleared. */
    fun clearIf(expected: String?): Boolean
}

class MemoryTokenStore : TokenStore {
    private var t: String? = null
    @Synchronized override fun get() = t
    @Synchronized override fun set(token: String?) { t = token }
    @Synchronized override fun clearIf(expected: String?): Boolean { if (expected == null || t != expected) return false; t = null; return true }
}

class UploadResult(val httpStatus: Int, val uploadId: String, val status: String, val duplicateImage: Boolean)

/**
 * Typed-enough wrapper over the backend API. The owner is never sent: the server derives it from the session.
 * The model API key never exists on the client (D2: backend only).
 */
class ApiClient(
    baseUrl: String,
    private val transport: Transport,
    private val tokens: TokenStore,
    debugBuild: Boolean,
    private val newKey: () -> String = { UUID.randomUUID().toString() },
) {
    private val base = BaseUrlPolicy.check(baseUrl, debugBuild) + "/v1"

    // ---------- plumbing ----------
    private fun call(method: String, path: String, body: Any? = null, idempotencyKey: String? = null, auth: Boolean = true,
                     rawBody: Pair<String, ByteArray>? = null): Pair<Int, Any?> {
        val h = linkedMapOf("Accept" to "application/json")
        val sent = if (auth) tokens.get() else null // remember which session this request belongs to
        if (sent != null) h["Authorization"] = "Bearer $sent"
        if (idempotencyKey != null) h["Idempotency-Key"] = idempotencyKey
        var bytes: ByteArray? = null
        if (rawBody != null) { h["Content-Type"] = rawBody.first; bytes = rawBody.second }
        else if (body != null) { h["Content-Type"] = "application/json; charset=utf-8"; bytes = Json.write(body).toByteArray(Charsets.UTF_8) }
        val resp = try { transport.send(HttpRequest(method, base + path, h, bytes)) } catch (e: IOException) { throw NetworkException(e) }
        val text = resp.text()
        val parsed: Any? = if (text.isBlank()) null else try { Json.parse(text) } catch (e: IllegalArgumentException) { null }
        if (resp.status >= 400) throw toError(resp.status, parsed, sent)
        return resp.status to parsed
    }

    private fun toError(status: Int, parsed: Any?, sentToken: String?): ApiException {
        val e = (parsed as? Map<*, *>)?.get("error") as? Map<*, *>
        @Suppress("UNCHECKED_CAST") val em = (e as? Map<String, Any?>) ?: emptyMap()
        val code = em.str("code") ?: "HTTP_$status"
        val msg = em.str("message") ?: "Request failed ($status)."
        val rid = em.str("request_id")
        if (status == 401) {
            // Clear only the session this request was sent with; never a newer one (Codex CP3a re-review 2).
            val cleared = tokens.clearIf(sentToken)
            val stale = sentToken != null && !cleared && tokens.get() != null
            return SessionExpiredException(code, msg, rid, staleToken = stale)
        }
        return ApiException(status, code, msg, rid, em.bool("retryable") ?: (status >= 500 || status == 429),
            em.obj("details") ?: emptyMap(), em.list("fields").objs())
    }

    @Suppress("UNCHECKED_CAST")
    private fun obj(r: Pair<Int, Any?>): Map<String, Any?> = r.second as? Map<String, Any?> ?: emptyMap()
    private fun arr(r: Pair<Int, Any?>): List<Map<String, Any?>> = (r.second as? List<Any?>)?.objs() ?: emptyList()
    private fun q(s: String) = URLEncoder.encode(s, "UTF-8")

    val isSignedIn: Boolean get() = tokens.get() != null

    // ---------- health / auth ----------
    fun health(): Map<String, Any?> = obj(call("GET", "/health", auth = false))

    fun signup(email: String, password: String) { call("POST", "/auth/signup", mapOf("email" to email, "password" to password), auth = false) }

    fun login(email: String, password: String) {
        val r = obj(call("POST", "/auth/login", mapOf("email" to email, "password" to password), auth = false))
        tokens.set(r.str("token") ?: throw ApiException(500, "BAD_RESPONSE", "No token in login response."))
    }

    /** Clears the local token even if the server cannot be reached; the server-side session then expires on its own. */
    fun logout() {
        try { if (tokens.get() != null) call("POST", "/auth/logout") } catch (_: Exception) { } finally { tokens.set(null) }
    }

    // ---------- profile / accounts ----------
    fun profile(): Map<String, Any?> = obj(call("GET", "/me/profile"))

    fun putProfile(incomeSatang: Long, frequency: String, nextIncomeDate: String, essentials: List<Map<String, Any?>>): Map<String, Any?> =
        obj(call("PUT", "/me/profile", mapOf("income_satang" to incomeSatang, "income_frequency" to frequency,
            "next_income_date" to nextIncomeDate, "timezone" to "Asia/Bangkok", "essentials" to essentials)))

    fun accounts(): List<Map<String, Any?>> = arr(call("GET", "/accounts"))

    fun addBalance(accountId: String, amountSatang: Long): Map<String, Any?> =
        obj(call("POST", "/accounts/${q(accountId)}/balance-observations", mapOf("amount_satang" to amountSatang)))

    fun pockets(): List<Map<String, Any?>> = arr(call("GET", "/pockets"))

    fun createPocket(name: String, categories: List<String>): Map<String, Any?> =
        obj(call("POST", "/pockets", mapOf("name" to name, "categories" to categories)))

    // ---------- consent ----------
    fun consents(): List<Map<String, Any?>> = arr(call("GET", "/consents"))
    fun activeConsentScopes(): Set<String> = consents().filter { it["revoked_at"] == null }.mapNotNull { it.str("scope") }.toSet()

    fun grantConsent(scope: String, version: String, params: Map<String, Any?> = emptyMap()): Map<String, Any?> =
        obj(call("POST", "/consents", mapOf("scope" to scope, "version" to version, "params" to params)))

    fun revokeConsent(scope: String): Map<String, Any?> = obj(call("DELETE", "/consents/${q(scope)}"))

    // ---------- uploads / review ----------
    /** The signed-in account id, used to bind the local upload queue to its owner. */
    fun me(): String = obj(call("GET", "/me")).str("user_id") ?: throw ApiException(500, "BAD_RESPONSE", "No user id.")

    /**
     * expectedOwnerId: the account the image was queued for; the server refuses a mismatch (OWNER_MISMATCH).
     * confirmedUndated: the user explicitly confirmed sending this photo although it has no capture date.
     */
    fun upload(bytes: ByteArray, mime: String, capturedAtIso: String?, expectedOwnerId: String? = null, confirmedUndated: Boolean = false): UploadResult {
        val fields = mutableListOf<Pair<String, String>>()
        if (capturedAtIso != null) fields += "captured_at" to capturedAtIso
        if (expectedOwnerId != null) fields += "expected_owner_id" to expectedOwnerId
        if (confirmedUndated) fields += "confirmed_undated" to "true"
        // Generic file name: the original name (often a timestamp or app name) is not sent.
        val (status, body) = call("POST", "/uploads", rawBody = Multipart.build(fields, "image", "image", mime, bytes))
        @Suppress("UNCHECKED_CAST") val m = body as? Map<String, Any?> ?: emptyMap()
        return UploadResult(status, m.str("upload_id") ?: throw ApiException(500, "BAD_RESPONSE", "No upload id."),
            m.str("status") ?: "received", m.bool("duplicate_image") ?: false)
    }

    fun uploads(): List<Map<String, Any?>> = arr(call("GET", "/uploads"))
    fun uploadDetail(id: String): Map<String, Any?> = obj(call("GET", "/uploads/${q(id)}"))
    fun retryUpload(id: String): Map<String, Any?> = obj(call("POST", "/uploads/${q(id)}/retry"))
    fun deleteUpload(id: String): Map<String, Any?> = obj(call("DELETE", "/uploads/${q(id)}"))
    fun scanStatus(): Map<String, Any?> = obj(call("GET", "/scan-status"))

    fun reviewItems(): Map<String, Any?> = obj(call("GET", "/review-items"))

    fun resolveReview(id: String, decision: String, fields: Map<String, Any?>? = null, txnId: String? = null): Map<String, Any?> {
        val body = linkedMapOf<String, Any?>("decision" to decision)
        if (fields != null) body["fields"] = fields
        if (txnId != null) body["txn_id"] = txnId
        return obj(call("POST", "/review-items/${q(id)}/resolve", body))
    }

    // ---------- ledger ----------
    fun transactions(): List<Map<String, Any?>> = arr(call("GET", "/transactions"))
    fun plan(): Map<String, Any?> = obj(call("GET", "/plan"))

    fun setCategory(txnId: String, category: String, setDefault: Boolean): Map<String, Any?> =
        obj(call("POST", "/transactions/${q(txnId)}/category", mapOf("category" to category, "set_payee_default" to setDefault)))

    /** Manual entry (R3.1). One idempotency key per user action: pass the same key when retrying that action. */
    fun createTransaction(body: Map<String, Any?>, idempotencyKey: String = newKey()): Pair<Int, Map<String, Any?>> {
        val r = call("POST", "/transactions", body, idempotencyKey)
        return r.first to obj(r)
    }
}
