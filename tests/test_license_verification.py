"""Contracts for licence evidence used before an arXiv PDF is fetched."""

import unittest

from neurolab.license_verification import (
    ArxivLicenseRequest,
    HtmlResponse,
    LicenseVerificationError,
    verify_arxiv_license,
)


SOURCE_KEY = "b" * 64


class LicenseVerificationTests(unittest.TestCase):
    def test_recognizes_explicit_cc_by_without_retaining_html(self):
        receipt = verify_arxiv_license(
            ArxivLicenseRequest(SOURCE_KEY, "2501.12345v2"),
            checked_on="2026-09-15",
            transport=lambda _: HtmlResponse(
                "text/html",
                b'<a href="http://creativecommons.org/licenses/by/4.0/">license</a>',
            ),
        )
        self.assertEqual(receipt.license_id, "CC-BY-4.0")
        self.assertEqual(len(receipt.evidence_sha256), 64)
        self.assertFalse(hasattr(receipt, "html"))

    def test_refuses_unknown_license_and_non_html_response(self):
        request = ArxivLicenseRequest(SOURCE_KEY, "2501.12345")
        with self.assertRaisesRegex(LicenseVerificationError, "not HTML"):
            verify_arxiv_license(request, checked_on="2026-09-15", transport=lambda _: HtmlResponse("application/pdf", b"%PDF"))
        with self.assertRaisesRegex(LicenseVerificationError, "no compatible"):
            verify_arxiv_license(request, checked_on="2026-09-15", transport=lambda _: HtmlResponse("text/html", b"license unknown"))

    def test_refuses_malformed_identifier(self):
        with self.assertRaises(LicenseVerificationError):
            ArxivLicenseRequest(SOURCE_KEY, "../2501.12345")


if __name__ == "__main__":
    unittest.main()
