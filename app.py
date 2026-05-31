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
from answersheet_ocr.config import (
    DEFAULT_DPI,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_SARVAM_LANGUAGE,
    SARVAM_LANGUAGES,
    ensure_directories,
    load_dotenv,
)
from answersheet_ocr.models import PageOCR
from answersheet_ocr.ocr import OpenAIOCRClient, describe_ocr_exception
from answersheet_ocr.pdf import PDFRenderError, render_pdf_to_images
from answersheet_ocr.providers import OPENAI_PROVIDER, SARVAM_PROVIDER, create_ocr_client, provider_label
from answersheet_ocr.report import generate_docx_report
from answersheet_ocr.sarvam import SarvamOCRClient, describe_sarvam_exception
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
    """Allow Streamlit Cloud secrets to provide provider API keys."""
    for key in (
        "OPENAI_API_KEY",
        "SARVAM_API_KEY",
        "OPENAI_TRUST_ENV_PROXY",
        "SARVAM_TRUST_ENV_PROXY",
    ):
        try:
            value = st.secrets.get(key)
        except Exception:
            value = None
        if value is not None:
            os.environ[key] = str(value)


def sarvam_language_options() -> list[str]:
    return [f"{name} ({code})" for name, code in SARVAM_LANGUAGES.items()]


def sarvam_code_from_option(option: str) -> str:
    if "(" not in option or not option.endswith(")"):
        return DEFAULT_SARVAM_LANGUAGE
    return option.rsplit("(", 1)[1].rstrip(")")


def sarvam_option_from_code(code: str | None) -> str:
    for option in sarvam_language_options():
        if option.endswith(f"({code})"):
            return option
    return f"Hindi ({DEFAULT_SARVAM_LANGUAGE})"


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
        provider_options = {
            "OpenAI": OPENAI_PROVIDER,
            "Sarvam AI": SARVAM_PROVIDER,
        }
        provider_name = st.selectbox(
            "OCR provider",
            options=list(provider_options.keys()),
            index=0 if DEFAULT_PROVIDER == OPENAI_PROVIDER else 1,
        )
        selected_provider = provider_options[provider_name]

        model = DEFAULT_MODEL
        sarvam_language_code = DEFAULT_SARVAM_LANGUAGE
        if selected_provider == OPENAI_PROVIDER:
            model = st.text_input("OpenAI model", value=DEFAULT_MODEL)
        else:
            sarvam_language = st.selectbox(
                "Sarvam language",
                options=sarvam_language_options(),
                index=sarvam_language_options().index(
                    sarvam_option_from_code(DEFAULT_SARVAM_LANGUAGE)
                ),
            )
            sarvam_language_code = sarvam_code_from_option(sarvam_language)

        dpi = st.slider("PDF render DPI", min_value=150, max_value=350, value=DEFAULT_DPI, step=10)
        max_pages = st.number_input("Max pages for demo run", min_value=0, value=0, help="0 processes all pages.")
        poppler_path = st.text_input("Poppler path override", value=os.getenv("POPPLER_PATH", ""))
        force_ocr = st.checkbox("Re-run OCR for pages already processed", value=False)
        trust_env_proxy = st.checkbox(
            "Use system proxy for provider APIs",
            value=os.getenv("OPENAI_TRUST_ENV_PROXY", "").strip().lower()
            in {"1", "true", "yes", "on"}
            or os.getenv("SARVAM_TRUST_ENV_PROXY", "").strip().lower()
            in {"1", "true", "yes", "on"},
            help=(
                "Leave off unless your network requires HTTP_PROXY/HTTPS_PROXY. "
                "This machine may have blocked local proxy variables set."
            ),
        )
        openai_key_ok = bool(os.getenv("OPENAI_API_KEY"))
        sarvam_key_ok = bool(os.getenv("SARVAM_API_KEY"))
        if selected_provider == OPENAI_PROVIDER:
            st.status(
                "OPENAI_API_KEY loaded" if openai_key_ok else "OPENAI_API_KEY missing",
                state="complete" if openai_key_ok else "error",
            )
        else:
            st.status(
                "SARVAM_API_KEY loaded" if sarvam_key_ok else "SARVAM_API_KEY missing",
                state="complete" if sarvam_key_ok else "error",
            )

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
                ocr_provider=selected_provider,
                sarvam_language_code=(
                    sarvam_language_code if selected_provider == SARVAM_PROVIDER else None
                ),
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
        provider_key_ok = (
            bool(os.getenv("OPENAI_API_KEY"))
            if selected_provider == OPENAI_PROVIDER
            else bool(os.getenv("SARVAM_API_KEY"))
        )
        if not provider_key_ok:
            key_name = "OPENAI_API_KEY" if selected_provider == OPENAI_PROVIDER else "SARVAM_API_KEY"
            st.warning(f"Add {key_name} to .env or Streamlit secrets before running OCR.")

        st.caption(
            "Selected provider: "
            f"{provider_label(selected_provider)}"
            + (
                f" | Language: {sarvam_language_code}"
                if selected_provider == SARVAM_PROVIDER
                else f" | Model: {model}"
            )
        )

        if st.button("Run OCR on rendered pages", disabled=not provider_key_ok):
            record.metadata.ocr_provider = selected_provider
            record.metadata.model = model if selected_provider == OPENAI_PROVIDER else "sarvam-vision"
            record.metadata.sarvam_language_code = (
                sarvam_language_code if selected_provider == SARVAM_PROVIDER else None
            )
            record.metadata.provider_job_ids = []
            save_run(record)

            client = create_ocr_client(
                selected_provider,
                openai_model=model,
                trust_env_proxy=trust_env_proxy,
                sarvam_language_code=sarvam_language_code,
            )
            progress = st.progress(0)
            failures: list[str] = []

            if selected_provider == OPENAI_PROVIDER:
                assert isinstance(client, OpenAIOCRClient)
                for index, image in enumerate(record.page_images, start=1):
                    existing = record.page_by_number(index)
                    if existing and not force_ocr:
                        progress.progress(index / len(record.page_images))
                        continue
                    with st.spinner(f"Running OpenAI OCR for page {index}..."):
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
            else:
                assert isinstance(client, SarvamOCRClient)
                if record.pages and not force_ocr:
                    st.info("This run already has OCR output. Enable re-run OCR to replace it.")
                    progress.progress(1.0)
                else:
                    with st.spinner("Running Sarvam OCR jobs..."):
                        try:
                            sarvam_pages = client.ocr_pages(
                                [Path(image) for image in record.page_images],
                                run_id=record.metadata.run_id,
                            )
                        except Exception as exc:
                            failures.append(describe_sarvam_exception(exc))
                            st.error(failures[-1])
                        else:
                            record.pages = []
                            for page in sarvam_pages:
                                record = upsert_page(record, page)
                            record.metadata.provider_job_ids = client.job_ids
                            save_run(record)
                            progress.progress(1.0)
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
