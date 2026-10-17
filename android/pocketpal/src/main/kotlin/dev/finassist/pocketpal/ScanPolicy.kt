package dev.finassist.pocketpal

/** Pure policy: capture date only, never file modification/import date. */
object ScanPolicy {
    const val WINDOW_MS = 30L * 24 * 60 * 60 * 1000
    const val MAX_BYTES = 8 * 1024 * 1024
    const val DAILY_CAP = 20
    /**
     * Version of [candidate]. Photos rejected by an older filter version are checked again once (locally) by a newer
     * one; photos already accepted by the server are never sent again (metadata + content-hash markers).
     * v1: English words only. v2 (17 Oct 2026): also a slip LAYOUT read by the Latin recognizer, so Thai-language slips
     * (whose Thai words the Latin model cannot read) can match on their digits.
     */
    const val FILTER_VERSION = 2
    fun mayAttempt(scanned: Int, attempted: Int, daily: Int) = scanned < 100 && attempted < 10 && daily < DAILY_CAP
    fun readBounded(input: java.io.InputStream): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (out.size() <= MAX_BYTES) {
            val count = input.read(buffer, 0, minOf(buffer.size, MAX_BYTES + 1 - out.size()))
            if (count < 0) break
            if (count == 0) continue
            out.write(buffer, 0, count)
        }
        return out.toByteArray()
    }
    fun recent(captured: Long, now: Long) = captured > 0 && captured <= now && captured >= now - WINDOW_MS

    /** Where an accessible photo's capture date puts it. Metadata only; used for the scan census. */
    enum class DateClass { UNDATED, OLDER, FUTURE, IN_WINDOW }
    fun dateClass(dateTaken: Long?, now: Long): DateClass = when {
        dateTaken == null || dateTaken <= 0 -> DateClass.UNDATED
        dateTaken > now -> DateClass.FUTURE
        dateTaken < now - WINDOW_MS -> DateClass.OLDER
        else -> DateClass.IN_WINDOW
    }

    private val money = Regex("\\d[\\d,]*[.]\\d{2}(?!\\d)")
    // Colon only: "12.50" is an amount, not a time.
    private val time = Regex("(?<!\\d)([01]?\\d|2[0-3]):[0-5]\\d(?!\\d)")
    private val thaiYear = Regex("(?<![\\d.,])25[6-7]\\d(?![\\d]|[.,]\\d)")
    private val masked = Regex("[xX*]{3,}[\\dxX*\\-\\s]{0,10}\\d{3,4}")

    /** A printed reference: one alphanumeric token of 12+ characters with at least 6 digits. */
    fun hasReference(text: String): Boolean = text.split(Regex("[^A-Za-z0-9]+")).any { tok -> tok.length >= 12 && tok.count { it.isDigit() } >= 6 }

    /** v1 rule, unchanged: English payment words + an amount with satang + supporting financial words. */
    fun englishSlip(text: String): Boolean {
        val t = text.lowercase()
        val transaction = Regex("\\b(payment|transfer|transaction|paid|successful|completed)\\b").containsMatchIn(t)
        val evidence = Regex("\\b(reference|bank|amount|baht|thb|recipient|transaction)\\b").containsMatchIn(t)
        return transaction && money.containsMatchIn(t) && evidence
    }

    /**
     * v2 layout rule (language-independent digits): an amount with satang, AND a masked account number or a long
     * reference, AND a time or a Buddhist-Era year. All three together are typical of a bank slip and rare in ordinary
     * photos. Still a heuristic: not validated on an image benchmark (FP/FN unknown); the server decides what it is.
     */
    fun layoutSlip(text: String): Boolean =
        money.containsMatchIn(text) && (masked.containsMatchIn(text) || hasReference(text)) &&
            (time.containsMatchIn(text) || thaiYear.containsMatchIn(text))

    fun candidate(text: String): Boolean = englishSlip(text) || layoutSlip(text)

    /** For the monitor only: an amount was read but the rest of the slip evidence was not (counts, never text). */
    fun moneyOnly(text: String): Boolean = money.containsMatchIn(text) && !candidate(text)
}
