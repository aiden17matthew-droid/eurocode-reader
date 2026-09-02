# EuroCode Compass

A 100% offline desktop app that points structural engineers to the right
**page, clause and table** in Eurocode PDFs they already own.

> **For navigation only. Verify all clauses in the official Eurocode.**
> The app never calculates, interprets or suggests design changes. It is an
> index and compass, nothing more. Engineering accountability remains with
> the engineer.

---

## Quick start

```bash
# 1. Create an isolated environment (recommended)
python -m venv .venv
.venv\Scripts\activate

# 2. CPU-only PyTorch first - avoids a ~2.5 GB CUDA download
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 3. Everything else
pip install -r requirements.txt

# 4. One-time model download (~90 MB). Needs internet ONCE.
python download_model.py

# 5. Run
python app.py
```

After step 4 the app never touches the internet again. No API keys, no cloud
services, no telemetry.

On Windows you can also just double-click **`run.bat`**, which prefers `.venv`
and launches without a console window.

---

## Using it

1. **Load PDF** - pick a Eurocode part you own. Indexing is one-time and
   offline (~20 s for 50 pages, ~90 s for 200).
2. **Search** in plain English: *"imposed loads on floors for office areas"*.
3. **Click a result** to open a read-only render of that exact page. The
   preview has prev/next, zoom, and an **Open in system viewer** button.

Results below the relevance floor (see `MIN_RELEVANCE` in
`backend/indexer.py`) are hidden, and the app says so rather than pointing
you at an unrelated page.

### Command line

```bash
python -m backend.indexer index "C:\path\to\EN1997-1.pdf"
python -m backend.indexer search "shear resistance of bored piles"
python -m backend.indexer search "..." --min-score 0   # show weak matches too
python -m backend.indexer list
python -m backend.indexer remove 1
```

---

## Showing it off (demo checklist)

- **Pre-index everything beforehand.** Indexing is one-time; don't spend the
  demo watching a progress bar. Load each PDF once before you present.
- **Run one search before the audience arrives.** The first search loads the
  model (~10 s); every search after that is instant.
- **Prove the offline claim: turn off Wi-Fi.** It keeps working. This is the
  whole point versus a cloud tool, and it lands better as a demo than as a
  sentence.
- **Prepare one off-topic query** (e.g. "shear resistance of bored piles"
  against EN 1991-1-1) to show it declines to guess rather than inventing a
  plausible-looking wrong page.
- Use `--theme dark` or `--theme light` to match the room's projector.

---

## Packaging as a standalone .exe

Honest assessment: possible, but heavy. `sentence-transformers` pulls in
PyTorch, so a one-file build lands around **1.5-2.5 GB** and takes minutes to
start. A zipped folder with `.venv` + `run.bat` is usually the better way to
hand this to a colleague.

If you do want an installer-free executable:

```bash
pip install pyinstaller

pyinstaller --noconfirm --windowed --name "EurocodeReader" ^
  --collect-all sentence_transformers ^
  --collect-all transformers ^
  --collect-all tokenizers ^
  --collect-all torch ^
  --collect-all customtkinter ^
  app.py
```

Then copy the cached model next to the executable and point `HF_HOME` at it,
so the packaged app stays offline:

- Model cache lives at `%USERPROFILE%\.cache\huggingface`
- Copy it into `dist\EurocodeReader\model_cache\`
- Set `HF_HOME` to that folder before launching (a small `.bat` wrapper is the
  easiest way)

Use `--onedir` (the default above) rather than `--onefile`: one-file builds
unpack ~2 GB to a temp folder on every launch.

---

## Project layout

```
app.py                 entry point (--db, --theme, --online)
run.bat                Windows one-click launcher
download_model.py      one-time model fetch
backend/
  pdf_loader.py        PyMuPDF text extraction, page chunking, clause/table refs
  embedder.py          all-MiniLM-L6-v2, CPU, offline by default
  database.py          SQLite storage; vectors as float32 BLOBs
  indexer.py           orchestration, cosine search, CLI
ui/
  main_window.py       load / progress / search / results
  result_card.py       one result: page + clause + snippet
  preview_window.py    read-only page render
data/                  local index (git-ignored, rebuildable)
```

## Requirements

Python 3.10+, Windows/macOS/Linux. Text-based PDFs only - scanned images need
OCR, which is out of scope for Phase 1.

## Notes

Your PDFs are never copied, modified or uploaded. Only extracted text and its
vectors are stored, in a local SQLite file under `data/`. Both `*.pdf` and
`data/` are git-ignored so copyrighted standards can never be committed.
