"""Publisher HTML evidence stays fixed-origin, bounded and review-only."""

import unittest

from neurolab.publisher_evidence import (
    F1000ArticleRequest,
    HtmlResponse,
    PublisherEvidenceError,
    verify_f1000_article,
)


SOURCE_KEY = "e" * 64


class PublisherEvidenceTests(unittest.TestCase):
    def test_receipt_and_bounded_visible_excerpt(self):
        page = b'''<html><head><style>hidden</style></head><body>
          <a href="https://creativecommons.org/licenses/by/4.0/">CC BY</a>
          <h1>Evidence title</h1><script>ignore()</script><p>Practical result.</p>
        </body></html>'''
        evidence = verify_f1000_article(
            F1000ArticleRequest(SOURCE_KEY, "14-905"),
            checked_on="2026-09-15",
            transport=lambda _: HtmlResponse("text/html", page),
        )
        self.assertEqual(evidence.receipt.provider, "f1000research")
        self.assertEqual(evidence.receipt.license_id, "CC-BY-4.0")
        self.assertEqual(len(evidence.receipt.html_sha256), 64)
        self.assertEqual(len(evidence.receipt.visible_text_sha256), 64)
        self.assertIn("Evidence title", evidence.excerpt)
        self.assertNotIn("ignore", evidence.excerpt)
        self.assertFalse(hasattr(evidence.receipt, "html"))

    def test_fails_closed_for_unlicensed_or_unfixed_input(self):
        with self.assertRaises(PublisherEvidenceError):
            F1000ArticleRequest(SOURCE_KEY, "https://f1000research.com/articles/14-905")
        request = F1000ArticleRequest(SOURCE_KEY, "14-905")
        with self.assertRaisesRegex(PublisherEvidenceError, "compatible"):
            verify_f1000_article(
                request,
                checked_on="2026-09-15",
                transport=lambda _: HtmlResponse("text/html", b"<p>no license</p>"),
            )
        with self.assertRaisesRegex(PublisherEvidenceError, "not HTML"):
            verify_f1000_article(
                request,
                checked_on="2026-09-15",
                transport=lambda _: HtmlResponse("application/pdf", b"%PDF"),
            )


if __name__ == "__main__":
    unittest.main()
