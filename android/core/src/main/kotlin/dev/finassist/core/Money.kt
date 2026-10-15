package dev.finassist.core

import java.math.BigDecimal

/** Client-side THB ↔ satang, same rules as the backend (FI-2): no floats, at most two decimals, no negatives. */
object Money {
    private val RE = Regex("""^(?:฿\s*)?((?:\d{1,3}(?:,\d{3})+)|\d+)(?:\.(\d{1,2}))?(?:\s*บาท)?$""")

    fun parseThb(text: String): Long? {
        val m = RE.matchEntire(text.trim()) ?: return null
        val whole = m.groupValues[1].replace(",", "")
        val frac = m.groupValues[2].padEnd(2, '0')
        return BigDecimal("$whole.$frac").movePointRight(2).longValueExact()
    }

    fun format(satang: Long): String {
        val sign = if (satang < 0) "-" else ""
        val a = kotlin.math.abs(satang)
        return "$sign฿" + "%,d".format(a / 100) + "." + "%02d".format(a % 100)
    }
}
