# Receipt Scanner App — Project Plan

## Overview
A simple Streamlit web app that lets a non-technical user (accessing from an
iPhone via Safari) photograph expense receipts, extract structured data from
each using the Claude API, review/edit the results, and export everything as
a CSV formatted for a company claims portal.

No login, no database, no persistence across sessions. Each visit is a
self-contained batch: take photos → review table → download CSV → done.

## Tech Stack
- **Framework:** Streamlit (Python) — handles UI, camera capture, and CSV
  export all in one framework, no separate frontend needed.
- **Extraction:** Claude API (vision) — send the receipt image, get back
  structured JSON. Chosen over Tesseract/traditional OCR because it handles
  messy, varied receipt layouts far more reliably.
- **Data handling:** pandas — assemble extracted records into a DataFrame,
  export to CSV.
- **Hosting:** Streamlit Community Cloud (free tier, deploys from GitHub).

## Fields to Extract
Exactly four columns, matching the claims portal template:
- `date`
- `merchant`
- `amount`
- `currency`

## Explicitly Out of Scope
- No persistence — nothing is stored server-side between sessions or after
  the tab is closed. All data lives in `st.session_state` for the duration
  of the browser session only.
- No login/auth.
- No "append to last week's CSV" feature.
- No image storage — photos are sent for extraction and then discarded.

## User Flow
1. User opens the app link (bookmarked to iPhone home screen for app-like
   feel).
2. Taps camera input → snaps a photo of a receipt (`st.camera_input`).
3. Image is sent to the extraction function → Claude API returns
   `{date, merchant, amount, currency}` as JSON.
4. New row appends to an editable table on screen (`st.data_editor`) so the
   user can correct any misread fields before finalizing.
5. Repeats for each receipt in the batch.
6. Taps "Download CSV" (`st.download_button`) → pandas DataFrame is
   converted to CSV and downloaded directly to the phone.

## File Structure
```
receipt-app/
├── streamlit_app.py     # Main app: camera input, session state, table, CSV export
├── extractor.py         # Function that calls Claude API with the image, returns parsed JSON
├── requirements.txt     # streamlit, anthropic, pandas
└── .streamlit/
    └── secrets.toml      # Claude API key (gitignored, not committed)
```

## Key Implementation Notes

### extractor.py
- Takes the raw image bytes from `st.camera_input`.
- Sends to Claude API (vision) with a prompt instructing it to return
  **only** a JSON object with keys `date`, `merchant`, `amount`, `currency`
  — no preamble, no markdown fences.
- Should handle/flag cases where a field can't be confidently read (e.g.
  return `null` for that field) rather than guessing, so the user notices
  it in the review table and can fill it in manually.
- Wrap the API call in try/except — network hiccups or a bad photo shouldn't
  crash the app; show an inline error and let the user retry.

### streamlit_app.py
- Use `st.session_state` to hold the growing list of receipt records for
  the current session only.
- `st.camera_input` — note it returns a new object each time it's used, so
  the "add another receipt" loop needs a way to reset/re-trigger it (e.g.
  clear the widget via a changing `key`, or process-then-rerun pattern).
- `st.data_editor` on the session-state DataFrame so the user can fix any
  field before export.
- `st.download_button` with `df.to_csv(index=False)` for the final export.
- Basic mobile-friendly layout — Streamlit is responsive by default, but
  keep the interface to one clear action at a time (avoid sidebars/columns
  that get cramped on a phone screen).

### Secrets
- Claude API key goes in `.streamlit/secrets.toml` locally (gitignored) and
  in the Streamlit Community Cloud dashboard's "Secrets" section for the
  deployed version. Never hardcode the key.

## Deployment Steps (for later)
1. Push repo to GitHub (public or private).
2. Connect repo on share.streamlit.io, set main file to `streamlit_app.py`.
3. Add `ANTHROPIC_API_KEY` under app secrets in the dashboard.
4. Deploy — get a live URL, bookmark it on the iPhone home screen.

## Build Order
1. `extractor.py` — get single-image extraction working and tested first,
   independent of any UI (test with a sample receipt photo via a plain
   script).
2. Basic `streamlit_app.py` — camera input → call extractor → display raw
   JSON result, to confirm the pipeline works end to end.
3. Add session-state list + `st.data_editor` table for multiple receipts.
4. Add CSV export via `st.download_button`.
5. Polish: error handling, loading states, mobile layout check.
