import unittest

from neurolab.gigachat_retry import GigaChatRetryError, bounded_gigachat_call, is_transient_gigachat_error, run_redacted_cli
from contextlib import redirect_stderr
from io import StringIO


class RateLimitError(Exception):
    pass


class GigaChatRetryTests(unittest.TestCase):
    def test_http_status_not_provider_text_controls_retry(self):
        error = RuntimeError("429 in a document is not a provider status")
        self.assertFalse(is_transient_gigachat_error(error))
        error.status_code = 429
        self.assertTrue(is_transient_gigachat_error(error))
        error.status_code = 401
        self.assertFalse(is_transient_gigachat_error(error))

    def test_cli_exit_protocol_never_prints_raw_error(self):
        for error, code in ((RateLimitError("secret-body"), 75), (ValueError("secret-body"), 1)):
            def fail():
                raise error
            captured = StringIO()
            with redirect_stderr(captured), self.assertRaises(SystemExit) as stopped:
                run_redacted_cli(fail, component="document_card")
            self.assertEqual(stopped.exception.code, code)
            self.assertNotIn("secret-body", captured.getvalue())

    def test_rate_limit_retries_with_bounded_backoff(self):
        attempts = []
        waits = []

        def call():
            attempts.append(1)
            if len(attempts) < 3:
                raise RateLimitError()
            return "ok"

        self.assertEqual(bounded_gigachat_call(call, sleep=waits.append), "ok")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(waits, [2.0, 4.0])

    def test_non_transient_failure_is_not_retried(self):
        attempts = []

        def call():
            attempts.append(1)
            raise ValueError("contract")

        with self.assertRaises(ValueError):
            bounded_gigachat_call(call, sleep=lambda _: None)
        self.assertEqual(len(attempts), 1)

    def test_exhausted_rate_limit_is_redacted(self):
        def call():
            raise RateLimitError("provider body must not escape")

        with self.assertRaisesRegex(GigaChatRetryError, "temporarily unavailable"):
            bounded_gigachat_call(call, max_retries=0, sleep=lambda _: None)
