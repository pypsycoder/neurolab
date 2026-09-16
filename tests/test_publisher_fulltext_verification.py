"""F1000 PDF route accepts only one constrained publisher redirect."""

import unittest

from neurolab.publisher_fulltext_verification import (
    F1000OpenAccessPdfRequest,
    PdfResponse,
    PublisherFullTextError,
    _stable_file_url,
    verify_f1000_open_access_pdf,
)


SOURCE_KEY = "c" * 64
STATIC_URL = "https://f1000research-files.f1000.com/manuscripts/187320/de69d868-c126-4d6c-854a-8d7be1e8adef_f1000res169927.pdf"


class PublisherFullTextTests(unittest.TestCase):
    def test_request_is_fixed_and_requires_cc_by(self):
        request = F1000OpenAccessPdfRequest(SOURCE_KEY, "14-905")
        self.assertEqual(request.publisher_url, "https://f1000research.com/articles/14-905/v1/pdf")
        with self.assertRaises(PublisherFullTextError):
            F1000OpenAccessPdfRequest(SOURCE_KEY, "https://example.test/a.pdf")
        with self.assertRaises(PublisherFullTextError):
            F1000OpenAccessPdfRequest(SOURCE_KEY, "14-905", license_id="CC0-1.0")

    def test_static_redirect_discards_query_and_rejects_other_hosts(self):
        self.assertEqual(_stable_file_url(STATIC_URL + "?temporary=value"), STATIC_URL)
        with self.assertRaises(PublisherFullTextError):
            _stable_file_url("https://example.test/manuscripts/187320/de69d868-c126-4d6c-854a-8d7be1e8adef_f1000res169927.pdf")

    def test_response_requires_pdf_before_parser(self):
        request = F1000OpenAccessPdfRequest(SOURCE_KEY, "14-905")
        with self.assertRaisesRegex(PublisherFullTextError, "MIME"):
            verify_f1000_open_access_pdf(
                request, transport=lambda _: PdfResponse("text/html", b"<html>", STATIC_URL)
            )
        with self.assertRaisesRegex(PublisherFullTextError, "signature"):
            verify_f1000_open_access_pdf(
                request, transport=lambda _: PdfResponse("application/octet-stream", b"not-a-pdf", STATIC_URL)
            )
