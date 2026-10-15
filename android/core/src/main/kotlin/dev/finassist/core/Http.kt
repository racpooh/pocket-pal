package dev.finassist.core

import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.util.UUID

class HttpRequest(val method: String, val url: String, val headers: Map<String, String>, val body: ByteArray? = null)

class HttpResponse(val status: Int, val body: ByteArray) {
    fun text(): String = body.toString(Charsets.UTF_8)
}

/** Network seam. Throws [IOException] when no HTTP response was received (offline, timeout, TLS failure). */
fun interface Transport {
    @Throws(IOException::class)
    fun send(request: HttpRequest): HttpResponse
}

/** java.net.HttpURLConnection works on Android and on a plain JVM (tests, E2E driver). No logging of any kind. */
class UrlConnectionTransport(private val connectTimeoutMs: Int = 10_000, private val readTimeoutMs: Int = 30_000) : Transport {
    override fun send(request: HttpRequest): HttpResponse {
        val c = URL(request.url).openConnection() as HttpURLConnection
        try {
            c.requestMethod = request.method
            c.connectTimeout = connectTimeoutMs
            c.readTimeout = readTimeoutMs
            c.instanceFollowRedirects = false // never forward the Authorization header to another location
            c.useCaches = false
            request.headers.forEach { (k, v) -> c.setRequestProperty(k, v) }
            if (request.body != null) {
                c.doOutput = true
                c.setFixedLengthStreamingMode(request.body.size)
                c.outputStream.use { it.write(request.body) }
            }
            val code = c.responseCode
            val stream = if (code >= 400) c.errorStream else c.inputStream
            val bytes = stream?.use { s -> ByteArrayOutputStream().also { s.copyTo(it) }.toByteArray() } ?: ByteArray(0)
            return HttpResponse(code, bytes)
        } finally {
            c.disconnect()
        }
    }
}

/**
 * SI-11 client side: release builds talk HTTPS only. Debug builds may use cleartext HTTP to the developer's own
 * machine only (adb reverse → 127.0.0.1, emulator host → 10.0.2.2). Anything else is refused before any request.
 */
object BaseUrlPolicy {
    val DEBUG_CLEARTEXT_HOSTS = setOf("127.0.0.1", "localhost", "10.0.2.2")

    fun check(url: String, debugBuild: Boolean): String {
        val u = try { URI(url) } catch (e: Exception) { throw IllegalArgumentException("invalid base URL") }
        val host = u.host?.lowercase() ?: throw IllegalArgumentException("base URL has no host")
        if (u.userInfo != null || u.query != null || u.fragment != null) throw IllegalArgumentException("base URL must be scheme://host[:port][/path]")
        when (u.scheme?.lowercase()) {
            "https" -> {}
            "http" -> if (!debugBuild || host !in DEBUG_CLEARTEXT_HOSTS)
                throw IllegalArgumentException("cleartext HTTP is allowed only in debug builds to ${DEBUG_CLEARTEXT_HOSTS.sorted()}")
            else -> throw IllegalArgumentException("unsupported scheme")
        }
        return url.trimEnd('/')
    }
}

object Multipart {
    /** One file part + optional text parts. Returns (Content-Type header value, body). */
    fun build(fields: List<Pair<String, String>>, fileField: String, fileName: String, mime: String, bytes: ByteArray): Pair<String, ByteArray> {
        val boundary = "----finassist" + UUID.randomUUID().toString().replace("-", "")
        val out = ByteArrayOutputStream()
        fun line(s: String) = out.write((s + "\r\n").toByteArray(Charsets.UTF_8))
        for ((k, v) in fields) {
            line("--$boundary"); line("Content-Disposition: form-data; name=\"${safe(k)}\""); line(""); line(v)
        }
        line("--$boundary")
        line("Content-Disposition: form-data; name=\"${safe(fileField)}\"; filename=\"${safe(fileName)}\"")
        line("Content-Type: $mime")
        line("")
        out.write(bytes)
        line("")
        line("--$boundary--")
        return "multipart/form-data; boundary=$boundary" to out.toByteArray()
    }

    private fun safe(s: String) = s.replace(Regex("[\"\\r\\n]"), "_")
}
