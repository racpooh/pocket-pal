"""Real Uvicorn formatting and source-free application diagnostics."""
import logging
from finassist.logsafe import RedactingFilter, log_exception


def test_access_formatter_keeps_redacted_structured_arguments():
    from uvicorn.logging import AccessFormatter
    record = logging.LogRecord('uvicorn.access', logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ('127.0.0.1:1234', 'GET', '/v1/example?email=synthetic@example.test', '1.1', 200), None)
    RedactingFilter().filter(record)
    result = AccessFormatter('%(request_line)s %(status_code)s', use_colors=False).format(record)
    assert 'synthetic@example.test' not in result
    assert '[EMAIL]' in result and '200' in result


def test_exception_frames_do_not_include_source_literals(caplog):
    logger = logging.getLogger('finassist.webtest')
    try:
        raise RuntimeError('SYNTHETIC_PRIVATE_SOURCE_LITERAL')
    except RuntimeError as error:
        with caplog.at_level(logging.ERROR):
            log_exception(logger, 'test_failure', error)
    assert 'test_web_log_compatibility.py' in caplog.text
    assert 'exc=RuntimeError' in caplog.text
    assert 'SYNTHETIC_PRIVATE_SOURCE_LITERAL' not in caplog.text
