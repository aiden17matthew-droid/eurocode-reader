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