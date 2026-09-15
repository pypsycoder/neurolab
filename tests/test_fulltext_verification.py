"""Negative contracts for the bounded open-access PDF verifier."""

import unittest

from neurolab.fulltext_verification import (
    FullTextVerificationError,
    OpenAccessPdfRequest,
    PdfResponse,
    verify_open_access_pdf,
)


SOURCE_KEY = "a" * 64


class FullTextVerificationTests(unittest.TestCase):
    def test_request_rejects_arbitrary_identifier_and_unknown_license(self):
        with self.assertRaises(FullTextVerificationError):
            OpenAccessPdfRequest(SOURCE_KEY, "https://example.test/document.pdf", "CC-BY-4.0")
        with self.assertRaises(FullTextVerificationError):
            OpenAccessPdfRequest(SOURCE_KEY, "2501.12345", "LICENSE-UNKNOWN")

    def test_response_must_be_bounded_pdf_before_any_parser_is_called(self):
        request = OpenAccessPdfRequest(SOURCE_KEY, "2501.12345v2", "CC-BY-4.0")
        with self.assertRaisesRegex(FullTextVerificationError, "not a PDF"):
            verify_open_access_pdf(request, transport=lambda _: PdfResponse("text/html", b"<html>"))
        with self.assertRaisesRegex(FullTextVerificationError, "signature"):
            verify_open_access_pdf(request, transport=lambda _: PdfResponse("application/pdf", b"not-a-pdf"))

    def test_open_license_request_has_only_fixed_arxiv_target(self):
        request = OpenAccessPdfRequest(SOURCE_KEY, "2501.12345", "cc-by-4.0")
        self.assertEqual(request.url, "https://export.arxiv.org/pdf/2501.12345")
        self.assertEqual(request.license_id.upper(), "CC-BY-4.0")


if __name__ == "__main__":
    unittest.main()
