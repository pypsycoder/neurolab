"""Runs only in the isolated research image, where pypdf is pinned."""

from io import BytesIO
import unittest

from pypdf import PdfWriter

from neurolab.fulltext_verification import OpenAccessPdfRequest, PdfResponse, verify_open_access_pdf


class PinnedPdfContractTests(unittest.TestCase):
    def test_bounded_pdf_is_parsed_in_memory_and_only_receipt_is_returned(self):
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        stream = BytesIO()
        writer.write(stream)
        receipt = verify_open_access_pdf(
            OpenAccessPdfRequest("a" * 64, "2501.12345", "CC-BY-4.0"),
            transport=lambda _: PdfResponse("application/pdf", stream.getvalue()),
        )
        self.assertEqual(receipt.page_count, 1)
        self.assertEqual(receipt.extracted_character_count, 0)
        self.assertEqual(len(receipt.sha256), 64)


if __name__ == "__main__":
    unittest.main()
