# Eurocode Reader - Phase 1 Specification

## App Purpose
A local desktop app for Civil/Structural Engineers to rapidly search multi-part Eurocodes (e.g., EN 1997, EN 1992) using natural language. It saves engineers 5-15 minutes per query by pointing them to the exact location in their PDF without the friction of cloud APIs.

## User Flow
1. **Startup:** The app opens a clean desktop window (CustomTkinter).
2. **Upload:** User clicks "Load PDF" and selects a local Eurocode PDF.
3. **Processing (One-time & Offline):** 
   - The app reads the PDF using PyMuPDF.
   - It chunks the text by page/clause.
   - It uses a local `sentence-transformers` model (`all-MiniLM-L6-v2`) to create vector embeddings of these chunks and saves them locally.
4. **Search:** The user types a query in a search bar (e.g., "shear resistance of bored piles").
5. **Results:** The app displays the top 3-5 matches showing:
   - Page Number
   - Estimated Clause/Table (if extractable)
   - A short preview snippet of the text.
6. **View:** User clicks a result, and the app opens the PDF to that exact page (either in a built-in viewer or the system default PDF viewer).

## Out of Scope for Phase 1
- Flowcharts and custom user notes (Save for Phase 2).
- Advanced OCR for scanned images (Assume text-based PDFs for now).

## Phase 2: Design Workflow & Flowchart Builder

### Purpose
Allow engineers to build visual, custom calculation flowcharts where each step/node references a specific Eurocode page or clause. The user designs their own logic (If/Else, step sequences) while retaining human accountability.

### Core Requirements
1. **Flowchart View / Tab:** Add a secondary tab or view in the UI: "Search" and "Flowchart Builder".
2. **Node Creation:**
   - Add nodes (e.g., "Step / Process", "Decision (If/Else)").
   - Each node allows: a Title, user notes/instructions, and an attached Eurocode Page/Clause tag.
3. **Interactive Navigation:** Clicking the Eurocode reference on any node immediately opens the built-in PyMuPDF preview directly to that page.
4. **Save & Export:** Save flowcharts locally as JSON files so engineers can load, share, and reuse standard office workflows (e.g., `pile_design_workflow.json`).
5. **Strict Constraint:** The flowchart tool remains purely organizational; it does not execute formulas or calculate values automatically.

## Phase 3: Ergonomics & Snippet Transfer

### Purpose
Make the flowchart canvas easier to navigate and eliminate manual typing by allowing engineers to send search results directly to the flowchart.

### Core Requirements
1. **Canvas Ergonomics:**
   - Users must be able to click and drag nodes to reposition them on the canvas.
   - Add canvas Zoom In / Zoom Out capabilities (via `Ctrl + MouseWheel` and/or UI buttons).
2. **One-Click Snippet Transfer ("Add to Flowchart"):**
   - In the Search view, add an "Add to Flowchart" button to every result card.
   - Clicking this button must NOT open the PDF preview. Instead, it should switch the app to the Flowchart tab and automatically instantiate a new Process Node.
   - This new node must be pre-populated with: Document Title, Clause Reference, Page Number, and the exact result snippet text inside the "Notes" field.
3. **Constraint:** The new features must strictly adhere to the liability rules. The transferred notes are purely textual reference data.

## Phase 4: Workspace Deck & Session Persistence

### Purpose
Engineers use multiple Eurocodes simultaneously. The app must allow users to save and load complete "Workspaces" so they can safely version-control their design process and quickly resume complex multi-document setups.

### Core Requirements
1. **Workspace Save & Load:**
   - Create a "Workspace" concept that bundles together:
     1. The specific Eurocode PDFs currently loaded in the index.
     2. The state/file of the currently active flowchart.
   - Provide UI buttons (e.g., "Save Workspace As..." and "Load Workspace") so users can save explicit project states and revert to them if they make a mistake.
2. **Session Auto-Resume:**
   - On launch, the app should automatically reload the last active Workspace so the engineer doesn't have to manually remount PDFs every morning.
3. **Multi-Document Search Toggle:**
   - The document dropdown in the Search tab must allow the user to filter by a single loaded Eurocode (e.g., EN 1991) or search across "All Loaded Documents" simultaneously.