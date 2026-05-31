from __future__ import annotations

import os
from pathlib import Path

try:
    import streamlit as st
except ImportError as exc:  # pragma: no cover - import guard for CLI checks
    raise RuntimeError(
        "Streamlit is not installed. Run: pip install -r requirements.txt"
    ) from exc

from answersheet_ocr.analytics import build_analytics
from answersheet_ocr.config import DEFAULT_DPI, DEFAULT_MODEL, ensure_directories, load_dotenv
from answersheet_ocr.models import PageOCR
from answersheet_ocr.ocr import OpenAIOCRClient, describe_ocr_exception
from answersheet_ocr.pdf import PDFRenderError, render_pdf_to_images
from answersheet_ocr.report import generate_docx_report
from answersheet_ocr.storage import (
    create_run_record,
    load_run,
    new_run_id,
    page_output_dir,
    save_run,
    save_uploaded_pdf,
    upsert_page,
)


def init_state() -> None:
    st.session_state.setdefault("run_id", "")


def load_streamlit_secrets() -> None:
    """Allow Streamlit Cloud secrets to provide the OpenAI API key."""
    try:
        api_key = st.secrets.get("OPENAI_API_KEY")
    except Exception:
        api_key = None
    if api_key:
        os.environ["OPENAI_API_KEY"] = str(api_key)


def load_current_run():
    run_id = st.session_state.get("run_id")
    if not run_id:
        return None
    try:
        return load_run(run_id)
    except FileNotFoundError:
        st.session_state["run_id"] = ""
        return None


def render_metrics(record) -> None:
    analytics = build_analytics(record)
    cols = st.columns(5)
    cols[0].metric("Pages", analytics["page_count"])
    cols[1].metric("OCR pages", analytics["ocr_page_count"])
    cols[2].metric("Questions", analytics["question_count"])
    cols[3].metric("Uncertainty", analytics["uncertainty_count"])
    cols[4].metric("Missing Q nos.", analytics["missing_question_numbers"])

    st.subheader("Languages")
    if analytics["detected_languages"]:
        st.write(analytics["detected_languages"])
    else:
        st.caption("No OCR language data yet.")

    if analytics["question_metrics"]:
        st.subheader("Question Word Counts")
        st.dataframe(
            [
                {
                    "page": item.page_number,
                    "question": item.question_number,
                    "word_count": item.word_count,
                    "uncertainty_flags": item.uncertainty_count,
                }
                for item in analytics["question_metrics"]
            ],
            hide_index=True,
            use_container_width=True,
        )


def review_page(record, page: PageOCR) -> None:
    image_path = Path(page.image_path) if page.image_path else record.image_for_page(page.page_number)
    left, right = st.columns([1, 1.2])
    with left:
        if image_path and image_path.exists():
            st.image(str(image_path), caption=f"Page {page.page_number}", use_container_width=True)
        else:
            st.warning("Page image not found.")

    with right:
        st.markdown(f"#### Page {page.page_number}")
        st.caption("Detected languages: " + (", ".join(page.detected_languages) or "None"))
        for index, question in enumerate(page.questions):
            label = question.question_number or f"Unnumbered block {index + 1}"
            with st.expander(f"Question {label}", expanded=True):
                st.text_area("Raw OCR", question.raw_text, disabled=True, key=f"raw_{page.page_number}_{index}")
                corrected = st.text_area(
                    "Reviewed correction",
                    question.corrected_text or question.raw_text,
                    key=f"corr_{page.page_number}_{index}",
                    height=180,
                )
                question.corrected_text = corrected if corrected != question.raw_text else ""
                if question.structure_elements:
                    st.caption("Structure: " + "; ".join(question.structure_elements))
                if question.margin_notes:
                    st.caption("Margin notes: " + "; ".join(question.margin_notes))
                if question.uncertainty_flags:
                    st.warning("Uncertainty: " + "; ".join(question.uncertainty_flags))


def main() -> None:
    load_dotenv()
    ensure_directories()
    st.set_page_config(
        page_title="Answer Sheet OCR",
        page_icon="OCR",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()
    load_streamlit_secrets()
    st.title("Handwritten Answer Sheet Digitization")

    with st.sidebar:
        st.header("Settings")
        model = st.text_input("OpenAI model", value=DEFAULT_MODEL)
        dpi = st.slider("PDF render DPI", min_value=150, max_value=350, value=DEFAULT_DPI, step=10)
        max_pages = st.number_input("Max pages for demo run", min_value=0, value=0, help="0 processes all pages.")
        poppler_path = st.text_input("Poppler path override", value=os.getenv("POPPLER_PATH", ""))
        force_ocr = st.checkbox("Re-run OCR for pages already processed", value=False)
        trust_env_proxy = st.checkbox(
            "Use system proxy for OpenAI",
            value=os.getenv("OPENAI_TRUST_ENV_PROXY", "").strip().lower()
            in {"1", "true", "yes", "on"},
            help=(
                "Leave off unless your network requires HTTP_PROXY/HTTPS_PROXY. "
                "This machine may have blocked local proxy variables set."
            ),
        )
        api_key_ok = bool(os.getenv("OPENAI_API_KEY"))
        st.status("OPENAI_API_KEY loaded" if api_key_ok else "OPENAI_API_KEY missing", state="complete" if api_key_ok else "error")

    uploaded = st.file_uploader("Upload handwritten answer-sheet PDF", type=["pdf"])
    if uploaded:
        if st.button("Create run and render pages", type="primary"):
            run_id = new_run_id(uploaded.name)
            pdf_path = save_uploaded_pdf(uploaded, run_id=run_id)
            with st.spinner("Rendering PDF pages..."):
                try:
                    page_images = render_pdf_to_images(
                        pdf_path,
                        page_output_dir(run_id),
                        dpi=dpi,
                        poppler_path=poppler_path or None,
                        max_pages=max_pages or None,
                    )
                except PDFRenderError as exc:
                    st.error(str(exc))
                    st.stop()
            record = create_run_record(
                run_id=run_id,
                source_pdf_name=uploaded.name,
                source_pdf_path=pdf_path,
                model=model,
                dpi=dpi,
                page_images=page_images,
            )
            save_run(record)
            st.session_state["run_id"] = run_id
            st.success(f"Rendered {len(page_images)} page(s).")
            st.rerun()

    record = load_current_run()
    if not record:
        st.info("Upload a PDF to begin. Files and extracted text stay local.")
        return

    st.caption(f"Run ID: {record.metadata.run_id}")
    tabs = st.tabs(["Pages", "OCR & Review", "Analytics", "Export"])

    with tabs[0]:
        st.subheader("Rendered Pages")
        columns = st.columns(2)
        for index, image_path in enumerate(record.page_images):
            with columns[index % 2]:
                path = Path(image_path)
                if path.exists():
                    st.image(str(path), caption=f"Page {index + 1}", use_container_width=True)
                else:
                    st.error(f"Missing page image: {path}")

    with tabs[1]:
        st.subheader("OCR and Human Review")
        if not os.getenv("OPENAI_API_KEY"):
            st.warning("Add OPENAI_API_KEY to .env before running OCR.")

        if st.button("Run OCR on rendered pages", disabled=not os.getenv("OPENAI_API_KEY")):
            client = OpenAIOCRClient(model=model, trust_env_proxy=trust_env_proxy)
            progress = st.progress(0)
            failures: list[str] = []
            for index, image in enumerate(record.page_images, start=1):
                existing = record.page_by_number(index)
                if existing and not force_ocr:
                    progress.progress(index / len(record.page_images))
                    continue
                with st.spinner(f"Running OCR for page {index}..."):
                    try:
                        page = client.ocr_page(Path(image), page_number=index)
                    except Exception as exc:
                        failures.append(f"Page {index}: {describe_ocr_exception(exc)}")
                        st.error(failures[-1])
                        progress.progress(index / len(record.page_images))
                        break
                    else:
                        record = upsert_page(record, page)
                        save_run(record)
                progress.progress(index / len(record.page_images))
            if failures:
                st.warning("OCR stopped after the first failed page. Completed pages were saved.")
            else:
                st.success("OCR complete.")
                st.rerun()

        if not record.pages:
            st.info("Run OCR to populate question-level review blocks.")
        else:
            for page in sorted(record.pages, key=lambda item: item.page_number):
                review_page(record, page)
            if st.button("Save corrections"):
                save_run(record)
                st.success("Corrections saved.")

    with tabs[2]:
        render_metrics(record)

    with tabs[3]:
        st.subheader("DOCX Report")
        if st.button("Generate DOCX report"):
            report_path = generate_docx_report(record)
            st.success(f"Report generated: {report_path}")
        default_report = Path("reports") / f"{record.metadata.run_id}.docx"
        if default_report.exists():
            st.download_button(
                "Download DOCX report",
                default_report.read_bytes(),
                file_name=default_report.name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )


if __name__ == "__main__":
    main()
