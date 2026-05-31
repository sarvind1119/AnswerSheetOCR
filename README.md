# Handwritten Answer Sheet Digitization Prototype

Local Streamlit prototype for PDF answer-sheet upload, page rendering, OpenAI or Sarvam AI OCR, question-wise review, analytics, and DOCX export.

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

If you are using the already installed user Python instead of a virtual environment:

```powershell
py -m pip install -r requirements.txt
```

Edit `.env` and set at least one provider key:

- `OPENAI_API_KEY` for OpenAI OCR.
- `SARVAM_API_KEY` for Sarvam AI Document Digitization.

Sarvam jobs request Markdown output because the Sarvam API accepts `md` or
`html`; the app still reads the JSON file that Sarvam includes in the returned
output ZIP when it is available.

By default, the OpenAI client ignores system proxy environment variables because
some Windows sessions set blocked local proxies such as `127.0.0.1:9`. If your
network needs a real proxy, set `OPENAI_TRUST_ENV_PROXY=true` and configure
`SARVAM_TRUST_ENV_PROXY=true` as needed, then configure `HTTP_PROXY`/`HTTPS_PROXY`
normally.

Poppler is required for PDF rendering. If `pdftoppm` is not on `PATH`, set `POPPLER_PATH` in `.env`.

## Run

```powershell
py -m streamlit run app.py
```

## Streamlit Community Cloud Deployment

This app uses `pdf2image`, which requires Poppler system binaries. The repo
includes `packages.txt` with `poppler-utils` so Streamlit Community Cloud installs
`pdfinfo` and `pdftoppm` during deployment.

After pushing changes to GitHub, reboot or redeploy the Streamlit app from
`Manage app`. Add provider keys in Streamlit Cloud secrets:

```toml
OPENAI_API_KEY = "sk-proj-..."
SARVAM_API_KEY = "..."
OPENAI_TRUST_ENV_PROXY = false
SARVAM_TRUST_ENV_PROXY = false
```

## Test

```powershell
pytest
```

## Data Layout

- `data/uploads/` stores uploaded PDFs.
- `data/pages/` stores rendered page images.
- `data/runs/` stores OCR JSON and correction state.
- `reports/` stores generated DOCX reports.
