# EuroCode Compass

**An offline, AI-assisted visual workflow builder for structural engineers.**

Find the clause. Record the route you took. Never let the software do your sums.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](#installation)
[![Runs offline](https://img.shields.io/badge/Network-None%20required-brightgreen.svg)](#privacy-by-architecture)

---

## The problem

Designing to the Eurocodes means living inside PDFs that were never built to be
searched. A single part runs to hundreds of pages of cross-referenced clauses,
national annexes and tables. In practice that produces three daily frustrations:

**Navigation is slow and repetitive.** Finding the imposed-load category for an
office floor means remembering which part it lives in, opening it, and scrolling.
Ctrl+F only helps if you already know the wording the drafting committee chose 
and "how much load on an office floor" appears nowhere in the clause heading.
Five to fifteen minutes disappear per lookup, several times a day.

**Design decisions leave no trail.** The reasoning behind a check which clause,
which category, which branch was taken and why lives in the engineer's head and
maybe a margin note. When a checker, a client or a future colleague asks *why*
six months later, it has to be reconstructed from scratch. Copy-pasting clause
text into a QA document is manual, error-prone, and drifts out of date.

**General-purpose AI is not usable for this work.** A chatbot will confidently
invent a clause number that does not exist, and cannot tell you it is guessing.
Worse, using one means uploading a client's design basis and copyrighted
standards your firm has licensed, not bought to a third-party server. For most
consultancies that is a straightforward breach of the client agreement.

Engineers do not need a machine that answers structural questions. They need one
that gets them to the right page faster, and keeps a record of where they went.

---

## The solution

EuroCode Compass is a desktop application that indexes the Eurocode PDFs you
already own, searches them by meaning rather than keyword, and lets you build an
auditable diagram of your design process on top of the results  entirely on your
own machine.

### Local semantic search

Ask in plain English. The app converts your question and every passage of your
PDFs into 384-dimensional vectors using a local `all-MiniLM-L6-v2` model, then
ranks by cosine similarity. *"How much load do I put on an office floor"* finds
the imposed-load categories even though none of those words appear in the clause
heading.

Results point at a page, a clause and a table, with a verbatim snippet — never a
paraphrase. Clicking one opens that exact page in a read-only viewer.

**The relevance threshold is calibrated, not guessed.** Matches below 45% are
hidden by default, because a weak match is a false pointer and being sent to an
unrelated page is worse than being told there is nothing. That figure came from
measurement against BS EN 1991-1-1: genuine on-topic queries scored **59.7–67.8%**,
while off-topic queries drawn from other Eurocode parts peaked at **43.7%** by
matching shared vocabulary. The threshold sits in the empty gap between those two
bands. Engineers hunting for awkward wording can tick *Include weak matches*, and
every result below the line is labelled as such.

### Flowchart builder — auditable logic trails

Draw the sequence you actually follow: Step nodes for actions, Decision nodes for
the forks you write in your own words, and labelled arrows for the branches. Each
node carries free-text notes, a link to a specific page in your PDFs, and
optionally an equation.

The result is the reasoning that would otherwise live in your head, in a form a
checker can read and a colleague can reuse. Clicking a node's page reference opens
that clause immediately, so a reviewer can verify every step against the source.
Charts save as JSON diff-able, emailable, and reusable as an office standard.

### One-click snippet transfer

The bridge between the two halves of the app. Found the clause you need? Click
**+ Add to Flowchart** on the result and the app creates a step already carrying
the document title, page number, clause reference and the snippet copied **word
for word** into the notes.

No retyping, no transcription errors, and nothing summarised on the way across.
The QA documentation writes itself as you work.

### Global equation library

Type an expression once and reuse it everywhere. The editor offers a palette of
64 symbols across Greek letters, operators, relations and common subscripts, so
you never have to remember LaTeX syntax, with a live preview rendered through
matplotlib's mathtext engine as you type.

Named equations are saved to a global library shared by every workflow — an
office's standard set of expressions gets typed once, not once per project. The
library opens standalone from the menu bar, so you can build it before loading a
single PDF. Nodes keep their own copy of the expression, so a chart sent to a
colleague still renders correctly on a machine that has never seen your library.

### Workspace session management

A workspace bundles which Eurocodes are loaded with the flowchart you were
building, saved as an explicit, named project state you can return to.

The safety model is deliberate and was the driving design constraint:

| | Written when | Purpose |
|---|---|---|
| **Workspace file** | Only when you click Save | Your rollback points. Nothing in the app ever writes to one on its own. |
| **Session file** | Automatically, on exit | Reopens yesterday's work at launch. App-private — never one of your saved workspaces. |

A bad afternoon can therefore never overwrite a good save. The distinction is
enforced by tests that assert a saved workspace is **byte-identical** after an
automatic session write.

---

## The liability boundary

**This application will never solve an equation, substitute a value, or tell you
whether a section passes.**

That is the central design constraint, not an unimplemented feature. A tool that
silently did the arithmetic would insert its answer between the engineer and the
code, and the engineering responsibility is not transferable. The software's job
is to get you to the right page faster and to record the route — the judgement
stays with the human who signs the drawing.

This is enforced structurally rather than promised in documentation:

- **There is nowhere to put a number.** No data model in the codebase has a field
  for a variable's value, a unit, a substitution or a result. Automated tests
  assert this against the node, edge, equation and workspace schemas — if someone
  later adds a `value` field, the test suite fails.
- **Equations are typeset, never parsed.** A stored expression is only ever handed
  to a renderer to be drawn. A test feeds in `1 = 2` and asserts it renders as
  happily as `1 = 1`, proving nothing evaluates it.
- **Decisions are prose.** A Decision node holds *"Is the pile slender?"* as text.
  Arrow captions like *Yes* and *No* are written for whoever reads the chart; the
  app never tests them or decides which branch applies.
- **No `eval`, `exec` or symbolic maths anywhere.** The test suite greps the
  source to keep it that way.
- **Retrieval scores are labelled as retrieval scores** — a match percentage says
  how closely wording matched a question, and the UI says so explicitly rather
  than letting it be read as engineering confidence.

Every screen carries the same notice: *"For navigation only. Verify all clauses in
the official Eurocode."*

---

## Privacy by architecture

Not a policy — a property of how the software is built.

- **No network calls.** No API keys, no accounts, no telemetry. The AI model is
  packaged inside the executable, so search works on a machine that has never
  been online.
- **No bundled standards.** You supply the PDFs you have licensed. The app ships
  none and downloads none, and the build script explicitly refuses to package
  your documents or your index so a copy of the `.exe` cannot leak a colleague's
  licensed standards.
- **Your data stays yours.** The index, workspaces, equation library and settings
  live in `%LOCALAPPDATA%\EuroCode Compass` on your machine and nowhere else.

A design basis never leaves the laptop, which makes the tool usable on client work
that a cloud service could not touch.

---

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| Language | **Python 3.12** | Fast iteration; strong scientific ecosystem |
| Interface | **CustomTkinter 6.0** | Native-feeling themed desktop UI with no web runtime |
| PDF engine | **PyMuPDF 1.28** | Page rendering, text extraction and bounding-box geometry |
| AI / NLP | **Sentence-Transformers 5.7** (`all-MiniLM-L6-v2`, 384-dim) on **PyTorch** CPU | Semantic retrieval that runs locally on any office laptop |
| Storage | **SQLite** | Zero-configuration local index; vectors stored as `float32` BLOBs |
| Typesetting | **Matplotlib 3.11** mathtext | LaTeX rendering without a LaTeX installation |
| Packaging | **PyInstaller 6.22** | Single-file Windows executable |

**Architecture.** ~9,400 lines across 32 modules, split into a `backend/` package
with no UI dependency — data models, PDF chunking, embedding, retrieval and JSON
persistence, all testable headlessly — and a `ui/` package holding the
CustomTkinter views. Long operations run on a worker thread and marshal results
back through a queue, because Tkinter is not thread-safe; the interface stays
responsive while a 50-page standard is indexed.

**Verification.** ~770 automated checks across 20 suites, driving the real widgets
with synthetic events: search relevance, canvas geometry and hit-testing at
multiple zoom levels, file round-trips, corrupted-file handling, render
performance, and the packaged executable itself.

---

## Installation

### For engineers — the standalone build

1. Download `EuroCodeCompass.exe` from the [Releases](../../releases) page.
2. Double-click it.

No Python, no installer, no administrator rights and no internet connection. The
first launch takes 40–60 seconds while the single-file build unpacks itself;
subsequent launches are quicker.

Load a Eurocode PDF you own, wait for the one-time indexing, and search. A
built-in guide (**Help → How to Use EuroCode Compass**) explains each feature.

### From source

```bash
git clone <repository-url>
cd "Eurocode Reader"

# CPU-only PyTorch first — avoids a ~2.5 GB CUDA download
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

python download_model.py    # one-time, ~92 MB; the only step needing a network
python app.py
```

### Building the executable

```bash
python build_exe.py          # or double-click build_exe.bat
```

Produces `dist/EuroCodeCompass.exe` (~435 MB, model included). `--onedir` builds
a folder instead, which starts instantly.

---

## Roadmap

- OCR for scanned standards — currently text-based PDFs only
- Export a flowchart to PDF for inclusion in a design report
- macOS and Linux builds

---

## Licence

Released under the **GNU General Public License v3.0** — see [LICENSE](LICENSE).

Anyone may use, study, modify and share this software. Anyone distributing a
modified version must release their source under the same terms. It cannot be
taken closed-source and sold on.

> **Note on PyMuPDF.** This project depends on PyMuPDF, which is dual-licensed
> **AGPL-3.0 or commercial**. Distributing a build that includes it means the
> combined work must satisfy AGPL terms for that component. For a desktop
> application with no network service the practical obligation — offering the
> source — is already met by this repository. A firm wanting to build a
> closed-source product on this code would need a commercial PyMuPDF licence
> *and* permission that the GPL does not grant.

Copyright © 2026 Aiden Matthew

---

## Disclaimer

EuroCode Compass is a local workflow tool. **Not affiliated with CEN or BSI.**

It is a navigation and documentation aid. It does not perform structural
calculations, does not interpret code provisions, and does not constitute
engineering advice. All clauses must be verified against the official published
Eurocode, and all engineering judgement and responsibility remain with the
qualified engineer.

No Eurocode content is distributed with this software. Users must supply PDFs
they are licensed to hold.
