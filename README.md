# Handwritten Answer Sheet Digitization Prototype

Local Streamlit prototype for PDF answer-sheet upload, page rendering, GPT-4o-mini OCR, question-wise review, analytics, and DOCX export.

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

Edit `.env` and set `OPENAI_API_KEY`.

By default, the OpenAI client ignores system proxy environment variables because
some Windows sessions set blocked local proxies such as `127.0.0.1:9`. If your
network needs a real proxy, set `OPENAI_TRUST_ENV_PROXY=true` and configure
`HTTP_PROXY`/`HTTPS_PROXY` normally.

Poppler is required for PDF rendering. If `pdftoppm` is not on `PATH`, set `POPPLER_PATH` in `.env`.

## Run

```powershell
py -m streamlit run app.py
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
