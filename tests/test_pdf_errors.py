import unittest
from pathlib import Path
from unittest.mock import patch

from pdf2image.exceptions import PDFInfoNotInstalledError

from answersheet_ocr.pdf import PDFRenderError, render_pdf_to_images
from tests.helpers import workspace_temp_dir


class PdfErrorTests(unittest.TestCase):
    def test_missing_poppler_has_actionable_error(self):
        with workspace_temp_dir() as tmp_path:
            pdf_path = tmp_path / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4")

            with patch(
                "answersheet_ocr.pdf.convert_from_path",
                side_effect=PDFInfoNotInstalledError("missing"),
            ):
                with self.assertRaises(PDFRenderError) as ctx:
                    render_pdf_to_images(pdf_path, tmp_path / "pages")

            self.assertIn("packages.txt", str(ctx.exception))
            self.assertIn("poppler-utils", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
