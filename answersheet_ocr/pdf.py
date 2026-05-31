from __future__ import annotations

from pathlib import Path

from pdf2image import convert_from_path
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError


class PDFRenderError(RuntimeError):
    """Raised when a PDF cannot be rendered into page images."""


def render_pdf_to_images(
    pdf_path: Path,
    output_dir: Path,
    *,
    dpi: int = 220,
    image_format: str = "png",
    poppler_path: str | None = None,
    max_pages: int | None = None,
) -> list[Path]:
    """Render a PDF into stable, one-indexed page image files."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if image_format.lower() not in {"png", "jpeg", "jpg"}:
        raise ValueError("image_format must be png, jpeg, or jpg")

    output_dir.mkdir(parents=True, exist_ok=True)
    last_page = max_pages if max_pages and max_pages > 0 else None
    try:
        pages = convert_from_path(
            pdf_path=str(pdf_path),
            dpi=dpi,
            fmt=image_format,
            output_folder=str(output_dir),
            output_file="page",
            paths_only=True,
            first_page=1,
            last_page=last_page,
            poppler_path=poppler_path,
        )
    except PDFInfoNotInstalledError as exc:
        raise PDFRenderError(
            "Poppler is not installed or is not on PATH. On Streamlit Community "
            "Cloud, add a root-level packages.txt file containing: poppler-utils"
        ) from exc
    except PDFPageCountError as exc:
        raise PDFRenderError(
            "Could not read the PDF page count. The file may be encrypted, corrupt, "
            "or unsupported by Poppler."
        ) from exc
    except PDFSyntaxError as exc:
        raise PDFRenderError("The uploaded PDF appears to be malformed.") from exc

    normalized_paths: list[Path] = []
    extension = "jpg" if image_format.lower() == "jpeg" else image_format.lower()
    for index, page_path in enumerate(pages, start=1):
        source = Path(page_path)
        target = output_dir / f"page_{index:03d}.{extension}"
        if source.resolve() != target.resolve():
            if target.exists():
                target.unlink()
            source.replace(target)
        normalized_paths.append(target)

    return normalized_paths
