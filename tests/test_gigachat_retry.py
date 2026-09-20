import unittest

from neurolab.gigachat_retry import GigaChatRetryError, bounded_gigachat_call


class RateLimitError(Exception):
    pass


class GigaChatRetryTests(unittest.TestCase):
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
