"""Application-log redaction (SI-8, R9.8).

Primary rule: code never logs content (slip fields, OCR text, chat text, amounts tied to a person, tokens). This
module is the second layer for what we do not control the wording of — exception messages and tracebacks (e.g.
Postgres `DETAIL: Key (email)=(...)`) and third-party log lines. It rewrites every record that reaches a handler it
is installed on: message, arguments and exception text.

Free text such as Thai payee names cannot be recognised by pattern; it is kept out by the primary rule, and the
tests check that the API's error log carries no request content.
"""

from __future__ import annotations

import logging
import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b(authorization|x-api-key|cookie)(\"?\s*[:=]\s*\"?)(bearer\s+)?[^\s\",}]+"), r"\1\2[REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]+"), "[REDACTED_KEY]"),
    (re.compile(r"(?i)\b(password|passwd|token|secret|api_key)(\"?\s*[:=]\s*\"?)[^\s\",}]+"), r"\1\2[REDACTED]"),
    (re.compile(r"(?i)\b(postgres(?:ql)?|https?)://[^\s/@]+:[^\s/@]+@"), r"\1://[REDACTED]@"),
    (re.compile(r"(DETAIL:\s+Key .*?\)=)\(.*\)(?=\s+(?:already exists|is not present))"), r"\1([REDACTED])"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"(?<![\w-])[A-Za-z]{0,6}\d{10,}[A-Za-z0-9]*(?![\w-])"), "[NUMBER]"),  # account numbers, bank refs
]


def redact(text: str) -> str:
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # bad format args must not leak raw args either
            msg = str(record.msg)
        record.msg, record.args = redact(msg), None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


def log_exception(logger: logging.Logger, event: str, exc: BaseException, **context) -> None:
    """Log an exception WITHOUT its message: event, context, exception type and stack frames (file, line, code).
    Messages can carry row values or free text (payee names, OCR text) that no pattern can recognise, so they are
    never logged by our own code. Context values must be ids or codes, never content."""
    import traceback

    ctx = " ".join(f"{k}={v}" for k, v in context.items())
    frames = "".join(traceback.format_tb(exc.__traceback__))
    logger.error("%s %s exc=%s\n%s", event, ctx, type(exc).__name__, frames)


_FILTER = RedactingFilter()
LOGGERS = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "finassist")


def install_redaction() -> None:
    """Attach the filter to every handler of the root, uvicorn and finassist loggers (idempotent). Adds a root
    handler when none exists so that app logs are never emitted unfiltered by a later default handler."""
    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(h)
    for name in LOGGERS:
        for h in logging.getLogger(name).handlers:
            if _FILTER not in h.filters:
                h.addFilter(_FILTER)
