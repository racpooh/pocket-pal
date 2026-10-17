package dev.finassist.pocketpal

import android.content.Context
import org.json.JSONObject
import java.time.LocalDate

class ScanStore(context: Context) {
    private val p = context.getSharedPreferences("gallery", Context.MODE_PRIVATE)
    var enabled: Boolean get() = p.getBoolean("enabled", false); set(v) { p.edit().putBoolean("enabled", v).commit() }
    var owner: String get() = p.getString("owner", "")!!; set(v) { p.edit().putString("owner", v).commit() }
    fun ownsSession(): Boolean {
        val cookie = android.webkit.CookieManager.getInstance().getCookie(BuildConfig.WEB_ORIGIN) ?: ""
        return cookie.isNotEmpty() && p.getString("session_hash", "") == sessionHash(cookie)
    }
    private fun sessionHash(cookie: String) = java.security.MessageDigest.getInstance("SHA-256").digest(cookie.toByteArray()).joinToString("") { "%02x".format(it) }
    fun bind(id: String, cookie: String) {
        if (owner != id) { p.edit().putString("owner", id).putBoolean("enabled", false).remove("message").remove("last_scan").remove("diagnostics").commit() }
        p.edit().putString("session_hash", sessionHash(cookie)).commit()
    }

    /*
     * Per-photo memory (keys are owner + MediaStore id + capture time + size, or owner + content SHA-256; never paths,
     * names or text):
     *   seen:<meta>                 legacy mark from the first scanner (accepted, filtered or refused — cause unknown)
     *   seen:acc:<meta>, seen:<owner>:<sha256>   accepted by the server → never sent again
     *   seen:rej:<meta>             refused by the server with 422 (date/consent) → not sent again automatically
     *   seen:flt:v<N>:<meta>        rejected by local filter version N → checked again only by a newer filter version
     */
    fun seen(key: String) = p.getBoolean("seen:$key", false)
    fun mark(key: String) { p.edit().putBoolean("seen:$key", true).commit() }
    fun attempts() = p.getInt("attempts:$owner:${LocalDate.now()}", 0)
    fun reserveAttempt() { p.edit().putInt("attempts:$owner:${LocalDate.now()}", attempts() + 1).commit() }
    fun note(message: String) { p.edit().putString("message", message).putLong("last_scan", System.currentTimeMillis()).commit() }
    fun progress(stage: String, counts: Map<String, Int>, labels: Map<String, String> = emptyMap()) {
        val diagnostic = JSONObject().put("stage", stage).put("updatedAt", System.currentTimeMillis())
        for ((key, value) in counts) diagnostic.put(key, value)
        for ((key, value) in labels) diagnostic.put(key, value)
        p.edit().putString("diagnostics", diagnostic.toString()).commit()
        // Counters, fixed stage codes and fixed labels only. Never log identity, paths, OCR or server bodies.
        android.util.Log.i("PocketPalScan", diagnostic.toString())
    }
    fun status(permission: String): JSONObject = JSONObject().put("available", true).put("enabled", enabled)
        .put("diagnostics", JSONObject(p.getString("diagnostics", "{}") ?: "{}"))
        .put("permission", permission).put("windowDays", 30).put("dailyLimit", ScanPolicy.DAILY_CAP)
        .put("attemptsToday", attempts()).put("lastScan", p.getLong("last_scan", 0))
        .put("message", p.getString("message", "Scanning is off. No gallery images have been sent."))
}
