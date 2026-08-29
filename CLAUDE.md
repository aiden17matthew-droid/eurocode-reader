# Project: Eurocode AI Reader

## Architecture & Tech Stack
- **Language:** Python 3.10+
- **Desktop UI:** `CustomTkinter` (for a modern, lightweight Python desktop interface)
- **PDF Engine:** `PyMuPDF` (fitz) for reading and chunking PDF pages.
- **AI/Search Engine:** `sentence-transformers` (using the lightweight `all-MiniLM-L6-v2` model) for 100% local, offline vector embeddings. No cloud APIs.
- **Database:** Local SQLite or ChromaDB for storing the vector embeddings locally.

## Strict Engineering Rules (NEVER VIOLATE)
1. **NO Calculations:** The app must NEVER solve equations or provide structural calculations.
2. **NO Redesigns:** The app must NEVER suggest design changes.
3. **Pointer Only:** The app acts strictly as an index/compass. It only returns the relevant Clause, Table, or Page number and a brief text snippet of what is on that page.
4. **Liability:** Engineering accountability remains with the human. Ensure the UI clearly states: "For navigation only. Verify all clauses in the official Eurocode."
5. **No Bundled PDFs:** The user must upload their own PDF. Do not download or include copyrighted Eurocode documents.
6. **100% Offline:** The app must not require an internet connection, API keys, or external cloud services to function once installed.

## Working Process
- Always read `SPEC.md` before starting a new major feature.
- Write clean, modular Python code.
- If a user lacks a dependency, provide the exact `pip install` command to fix it.