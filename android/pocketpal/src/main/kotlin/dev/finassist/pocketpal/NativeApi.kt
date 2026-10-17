package dev.finassist.pocketpal

import android.webkit.CookieManager
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant

class NativeApi {
    private val origin = BuildConfig.WEB_ORIGIN
    /** Snapshot one authenticated cookie; never use a newer account's cookie for old image bytes. */
    val cookie: String = CookieManager.getInstance().getCookie(origin) ?: ""
    fun unchanged() = cookie.isNotEmpty() && CookieManager.getInstance().getCookie(origin) == cookie
    private fun connection(path: String) = (URL(origin + path).openConnection() as HttpURLConnection).apply {
        instanceFollowRedirects = false; connectTimeout = 15000; readTimeout = 120000
        setRequestProperty("Cookie", cookie); setRequestProperty("Origin", origin)
    }
    private fun getText(path: String): String {
        check(unchanged()) { "SESSION_CHANGED" }
        val c = connection(path)
        try { check(c.responseCode == 200) { "SESSION_OR_SERVER_UNAVAILABLE" }; return c.inputStream.bufferedReader().use { it.readText() } }
        finally { c.disconnect() }
    }
    fun get(path: String) = JSONObject(getText(path))
    private val zone by lazy { java.time.ZoneId.of(get("/api/backend/me/profile").getString("timezone")) }
    fun consentDateAllowed(captured: Long): Boolean {
        val grants = org.json.JSONArray(getText("/api/backend/consents"))
        val date = Instant.ofEpochMilli(captured).atZone(zone).toLocalDate()
        for (i in 0 until grants.length()) {
            val grant = grants.getJSONObject(i)
            if (grant.optString("scope") == "photo_processing" && grant.isNull("revoked_at")) {
                val params = grant.optJSONObject("params") ?: return false
                val from = params.optString("scan_from")
                return from.isNotBlank() && !date.isBefore(java.time.LocalDate.parse(from))
            }
        }
        return false
    }
    fun allowed(owner: String): Boolean = unchanged() && get("/api/session").optString("user_id") == owner && get("/api/backend/scan-status").optBoolean("processing_allowed")
    fun upload(bytes: ByteArray, mime: String, captured: Long, owner: String): Int {
        check(allowed(owner) && consentDateAllowed(captured) && unchanged()) { "SCAN_NOT_ALLOWED" }
        val boundary = "PocketPalNative" + java.util.UUID.randomUUID().toString()
        val c = connection("/api/backend/uploads")
        try {
            c.requestMethod = "POST"; c.doOutput = true
            c.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
            c.outputStream.use { out ->
                fun field(name: String, value: String) { out.write("--$boundary\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n$value\r\n".toByteArray()) }
                field("expected_owner_id", owner); field("captured_at", Instant.ofEpochMilli(captured).atZone(zone).toOffsetDateTime().toString())
                out.write("--$boundary\r\nContent-Disposition: form-data; name=\"image\"; filename=\"image\"\r\nContent-Type: $mime\r\n\r\n".toByteArray())
                out.write(bytes); out.write("\r\n--$boundary--\r\n".toByteArray())
            }
            return c.responseCode
        } finally { c.disconnect() }
    }
}
