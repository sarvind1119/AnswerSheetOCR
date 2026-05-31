import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from answersheet_ocr.models import PageOCR, QuestionOCR, RunMetadata, RunRecord
from answersheet_ocr.pdf import render_pdf_to_images
from answersheet_ocr.report import generate_docx_report
from tests.helpers import workspace_temp_dir


def make_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path))
    pdf.drawString(72, 720, "Answer sheet page 1")
    pdf.showPage()
    pdf.drawString(72, 720, "Answer sheet page 2")
    pdf.save()


class PdfAndReportTests(unittest.TestCase):
    def test_render_pdf_to_images(self):
        with workspace_temp_dir() as tmp_path:
            pdf_path = tmp_path / "sample.pdf"
            make_pdf(pdf_path)

            images = render_pdf_to_images(
                pdf_path, tmp_path / "pages", dpi=120, image_format="png"
            )

            self.assertEqual(len(images), 2)
            self.assertEqual(images[0].name, "page_001.png")
            self.assertTrue(images[1].exists())

    def test_generate_docx_report(self):
        with workspace_temp_dir() as tmp_path:
            record = RunRecord(
                metadata=RunMetadata(
                    run_id="report-test",
                    source_pdf_name="sample.pdf",
                    source_pdf_path="sample.pdf",
                    model="gpt-4o-mini",
                    dpi=220,
                ),
                page_images=["page_001.png"],
                pages=[
                    PageOCR(
                        page_number=1,
                        image_path="page_001.png",
                        detected_languages=["English"],
                        questions=[
                            QuestionOCR(
                                question_number="1",
                                raw_text="Original OCR text",
                                corrected_text="Corrected answer text",
                                structure_elements=["bullet list"],
                                uncertainty_flags=["one word unclear"],
                                page_refs=[1],
                            )
                        ],
                    )
                ],
            )

            output = generate_docx_report(record, tmp_path / "report.docx")

            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
