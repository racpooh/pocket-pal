package dev.finassist.core

/**
 * Minimal JSON reader/writer (no third-party dependency, so the core module builds and is tested on a plain JVM).
 * Objects → Map<String, Any?> (insertion order kept), arrays → List<Any?>, integers → Long, decimals → Double.
 * Money is always integer satang from the backend, so Double only appears for non-money fields.
 */
object Json {
    fun parse(text: String): Any? {
        val p = Parser(text)
        val v = p.value()
        p.ws()
        if (p.i != text.length) throw IllegalArgumentException("trailing characters at ${p.i}")
        return v
    }

    @Suppress("UNCHECKED_CAST")
    fun obj(text: String): Map<String, Any?> = parse(text) as? Map<String, Any?> ?: throw IllegalArgumentException("not a JSON object")

    fun write(v: Any?): String = StringBuilder().also { w(it, v) }.toString()

    private fun w(sb: StringBuilder, v: Any?) {
        when (v) {
            null -> sb.append("null")
            is String -> str(sb, v)
            is Boolean -> sb.append(v)
            is Int, is Long, is Short, is Byte -> sb.append(v.toString())
            is Double -> { require(v.isFinite()) { "non-finite number" }; sb.append(v.toString()) }
            is Float -> w(sb, v.toDouble())
            is Map<*, *> -> {
                sb.append('{')
                var first = true
                for ((k, value) in v) {
                    if (!first) sb.append(',')
                    first = false
                    str(sb, k.toString()); sb.append(':'); w(sb, value)
                }
                sb.append('}')
            }
            is Iterable<*> -> {
                sb.append('[')
                var first = true
                for (x in v) { if (!first) sb.append(','); first = false; w(sb, x) }
                sb.append(']')
            }
            else -> throw IllegalArgumentException("cannot encode ${v::class.java.simpleName}")
        }
    }

    private fun str(sb: StringBuilder, s: String) {
        sb.append('"')
        for (c in s) {
            when (c) {
                '"' -> sb.append("\\\"")
                '\\' -> sb.append("\\\\")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                '\b' -> sb.append("\\b")
                '\u000C' -> sb.append("\\f")
                else -> if (c < ' ') sb.append(String.format("\\u%04x", c.code)) else sb.append(c)
            }
        }
        sb.append('"')
    }

    private class Parser(val s: String) {
        var i = 0

        fun ws() { while (i < s.length && s[i] in " \t\r\n") i++ }

        fun value(): Any? {
            ws()
            if (i >= s.length) throw IllegalArgumentException("unexpected end")
            return when (val c = s[i]) {
                '{' -> objectValue()
                '[' -> arrayValue()
                '"' -> stringValue()
                't' -> literal("true", true)
                'f' -> literal("false", false)
                'n' -> literal("null", null)
                else -> if (c == '-' || c in '0'..'9') number() else throw IllegalArgumentException("unexpected '$c' at $i")
            }
        }

        private fun literal(word: String, v: Any?): Any? {
            if (!s.startsWith(word, i)) throw IllegalArgumentException("bad literal at $i")
            i += word.length
            return v
        }

        private fun objectValue(): Map<String, Any?> {
            val m = LinkedHashMap<String, Any?>()
            i++; ws()
            if (s.getOrNull(i) == '}') { i++; return m }
            while (true) {
                ws()
                if (s.getOrNull(i) != '"') throw IllegalArgumentException("expected key at $i")
                val k = stringValue()
                ws()
                if (s.getOrNull(i) != ':') throw IllegalArgumentException("expected ':' at $i")
                i++
                m[k] = value()
                ws()
                when (s.getOrNull(i)) {
                    ',' -> i++
                    '}' -> { i++; return m }
                    else -> throw IllegalArgumentException("expected ',' or '}' at $i")
                }
            }
        }

        private fun arrayValue(): List<Any?> {
            val l = ArrayList<Any?>()
            i++; ws()
            if (s.getOrNull(i) == ']') { i++; return l }
            while (true) {
                l.add(value())
                ws()
                when (s.getOrNull(i)) {
                    ',' -> i++
                    ']' -> { i++; return l }
                    else -> throw IllegalArgumentException("expected ',' or ']' at $i")
                }
            }
        }

        private fun stringValue(): String {
            val sb = StringBuilder()
            i++
            while (true) {
                if (i >= s.length) throw IllegalArgumentException("unterminated string")
                val c = s[i++]
                when (c) {
                    '"' -> return sb.toString()
                    '\\' -> {
                        when (val e = s.getOrNull(i++) ?: throw IllegalArgumentException("bad escape")) {
                            '"' -> sb.append('"'); '\\' -> sb.append('\\'); '/' -> sb.append('/')
                            'b' -> sb.append('\b'); 'f' -> sb.append('\u000C'); 'n' -> sb.append('\n')
                            'r' -> sb.append('\r'); 't' -> sb.append('\t')
                            'u' -> {
                                if (i + 4 > s.length) throw IllegalArgumentException("bad \\u escape")
                                sb.append(s.substring(i, i + 4).toInt(16).toChar()); i += 4
                            }
                            else -> throw IllegalArgumentException("bad escape \\$e")
                        }
                    }
                    else -> sb.append(c)
                }
            }
        }

        private fun number(): Any {
            val start = i
            if (s[i] == '-') i++
            while (i < s.length && s[i].isDigit()) i++
            var frac = false
            if (i < s.length && s[i] == '.') { frac = true; i++; while (i < s.length && s[i].isDigit()) i++ }
            if (i < s.length && (s[i] == 'e' || s[i] == 'E')) {
                frac = true; i++
                if (i < s.length && (s[i] == '+' || s[i] == '-')) i++
                while (i < s.length && s[i].isDigit()) i++
            }
            val t = s.substring(start, i)
            return if (frac) t.toDouble() else t.toLong()
        }
    }
}

@Suppress("UNCHECKED_CAST")
fun Map<String, Any?>.obj(k: String): Map<String, Any?>? = this[k] as? Map<String, Any?>
@Suppress("UNCHECKED_CAST")
fun Map<String, Any?>.list(k: String): List<Any?> = this[k] as? List<Any?> ?: emptyList()
fun Map<String, Any?>.str(k: String): String? = this[k]?.toString()
fun Map<String, Any?>.long(k: String): Long? = (this[k] as? Number)?.toLong()
fun Map<String, Any?>.bool(k: String): Boolean? = this[k] as? Boolean
@Suppress("UNCHECKED_CAST")
fun List<Any?>.objs(): List<Map<String, Any?>> = mapNotNull { it as? Map<String, Any?> }
