"""Receipt Scanner — Streamlit web app.

Photograph or upload expense receipts, extract structured data with Claude
vision, review/correct it in an editable table, and download a CSV for the
claims portal. No login, no database — everything lives in the browser session
and is gone when the tab closes.

Run locally:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from extractor import extract_receipt

# --- Configuration ---------------------------------------------------------

# Streamlit exposes secrets.toml / dashboard secrets as env vars, but set it
# explicitly so anthropic.Anthropic() always finds the key on both local and
# Community Cloud deployments.
if "ANTHROPIC_API_KEY" in st.secrets:
    os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]

# Display columns, in the order the claims portal expects them. The CSV headers
# are Title Case for readability — this is a staging file to copy-paste from,
# not a strict portal template.
COLUMNS = {
    "date": "Date",
    "merchant": "Merchant",
    "amount": "Amount",
    "currency": "Currency",
}

st.set_page_config(page_title="Receipt Scanner", page_icon="🧾")

# --- Session state ---------------------------------------------------------

# The growing list of extracted receipt dicts for this session only.
st.session_state.setdefault("records", [])
# Counters bump the widget keys after each capture/upload so the widgets reset
# and the same image isn't reprocessed on the next rerun.
st.session_state.setdefault("camera_key", 0)
st.session_state.setdefault("uploader_key", 0)


def _process(image_bytes: bytes, media_type: str) -> None:
    """Extract one receipt and append it to the table, or show an error."""
    with st.spinner("Reading receipt…"):
        result = extract_receipt(image_bytes, media_type=media_type)
    if "error" in result:
        st.error(result["error"])
    else:
        st.session_state["records"].append(result)


# --- Header ----------------------------------------------------------------

st.title("🧾 Receipt Scanner")
st.write(
    "Add a receipt below — take a photo or upload one. The details are read "
    "automatically. Check the table, fix anything wrong, then download the CSV."
)

# --- Input: take a photo OR upload -----------------------------------------

mode = st.radio(
    "How do you want to add a receipt?",
    ["Take a photo", "Upload photo(s)"],
    horizontal=True,
)

if mode == "Take a photo":
    photo = st.camera_input(
        "Photograph a receipt",
        key=f"camera_{st.session_state['camera_key']}",
    )
    if photo is not None:
        _process(photo.getvalue(), photo.type or "image/jpeg")
        # Bump the key so the camera clears and is ready for the next receipt.
        st.session_state["camera_key"] += 1
        st.rerun()
else:
    uploads = st.file_uploader(
        "Choose receipt image(s)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state['uploader_key']}",
    )
    if uploads:
        for f in uploads:
            _process(f.getvalue(), f.type or "image/jpeg")
        # Bump the key so these files aren't reprocessed on the next rerun.
        st.session_state["uploader_key"] += 1
        st.rerun()

# --- Review table + export -------------------------------------------------

st.divider()

records = st.session_state["records"]
if not records:
    st.info("No receipts yet. Add one above to get started.")
else:
    df = pd.DataFrame(records, columns=list(COLUMNS.keys())).rename(columns=COLUMNS)

    st.subheader(f"Receipts ({len(records)})")
    edited = st.data_editor(
        df,
        use_container_width=True,
        num_rows="dynamic",  # lets the user delete rows too
        key="editor",
    )

    # Persist any edits/deletions back into session state (keyed by internal
    # field names so the next extraction appends consistently).
    st.session_state["records"] = (
        edited.rename(columns={v: k for k, v in COLUMNS.items()})
        .to_dict(orient="records")
    )

    csv = edited.to_csv(index=False).encode("utf-8")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Download CSV",
            data=csv,
            file_name="receipts.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col2:
        if st.button("🗑️ Clear all", use_container_width=True):
            st.session_state["records"] = []
            st.rerun()
