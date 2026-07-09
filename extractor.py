"""Receipt data extraction using the Claude vision API.

Takes raw image bytes from a receipt photo and returns a structured dict with
the four fields the claims portal needs: date, merchant, amount, currency.

Designed to be tested in isolation (see the __main__ block at the bottom) before
being wired into the Streamlit UI.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime

import anthropic

MODEL = "claude-sonnet-5"

# The four fields the claims portal needs. Every field is nullable so the model
# returns null for anything it can't read confidently, rather than guessing —
# the user then notices the blank in the review table and fills it in by hand.
_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {
            "type": ["string", "null"],
            "description": "Transaction date in ISO format YYYY-MM-DD, or null if not legible.",
        },
        "merchant": {
            "type": ["string", "null"],
            "description": "Merchant / shop name, or null if not legible.",
        },
        "amount": {
            "type": ["number", "null"],
            "description": "Total amount paid as a plain number (no currency symbol), or null if not legible.",
        },
        "currency": {
            "type": ["string", "null"],
            "description": "3-letter ISO currency code, e.g. GBP, USD, EUR, or null if not determinable.",
        },
    },
    "required": ["date", "merchant", "amount", "currency"],
    "additionalProperties": False,
}

_PROMPT = (
    "You are reading a photo of an expense receipt. Extract exactly four fields:\n"
    "- date: the transaction date, formatted as ISO YYYY-MM-DD.\n"
    "- merchant: the name of the shop or business.\n"
    "- amount: the TOTAL amount paid (the grand total including tax/service), "
    "as a plain number with no currency symbol.\n"
    "- currency: the 3-letter ISO currency code (e.g. GBP, USD, EUR). Infer it "
    "from the currency symbol or country if no code is printed.\n\n"
    "If any field cannot be read confidently from the image, return null for "
    "that field rather than guessing."
)

# Column keys used throughout the app. Kept here so the UI and extractor agree.
FIELDS = ["date", "merchant", "amount", "currency"]


def _to_ddmmyyyy(iso_date: str | None) -> str:
    """Convert an ISO YYYY-MM-DD string to DD/MM/YYYY.

    Returns "" (blank) if the input is missing or unparseable, so the user can
    fill it in manually in the review table.
    """
    if not iso_date:
        return ""
    try:
        return datetime.strptime(iso_date.strip(), "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, AttributeError):
        # Model returned something that isn't a clean ISO date — leave it blank.
        return ""


def extract_receipt(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """Extract receipt fields from image bytes using Claude vision.

    Args:
        image_bytes: Raw bytes of the receipt image.
        media_type: MIME type of the image, e.g. "image/jpeg" or "image/png".

    Returns:
        On success: {"date", "merchant", "amount", "currency"} — date as
        DD/MM/YYYY (or blank), amount as a number (or None), others as strings
        (or blank/None). On failure: {"error": "<message>"} so the caller can
        show an inline error and let the user retry, instead of the app crashing.
    """
    client = anthropic.Anthropic()
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
    except anthropic.APIError as e:
        # Network hiccup, bad image, auth problem, etc. — don't crash the app.
        return {"error": f"Could not read receipt: {e}"}
    except Exception as e:  # noqa: BLE001 - last-resort guard so the UI never dies
        return {"error": f"Unexpected error: {e}"}

    # Structured outputs guarantee the first text block is valid JSON matching
    # the schema. Parse it rather than string-matching.
    try:
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
    except (StopIteration, json.JSONDecodeError, AttributeError) as e:
        return {"error": f"Could not parse extraction result: {e}"}

    return {
        "date": _to_ddmmyyyy(data.get("date")),
        "merchant": data.get("merchant") or "",
        "amount": data.get("amount"),
        "currency": data.get("currency") or "",
    }


def _load_key_from_secrets() -> None:
    """For standalone CLI testing, load the API key from .streamlit/secrets.toml
    into the environment if it isn't already set.

    The Streamlit app reads that file automatically via st.secrets; this lets
    `python extractor.py <image>` use the same key source without a separate
    setup step. Silently does nothing if the file/key is absent.
    """
    import os
    import pathlib
    import tomllib

    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    secrets_path = pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml"
    try:
        with open(secrets_path, "rb") as f:
            key = tomllib.load(f).get("ANTHROPIC_API_KEY")
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        pass


if __name__ == "__main__":
    # Standalone test: python extractor.py path/to/receipt.jpg
    import mimetypes
    import sys

    if len(sys.argv) != 2:
        print("Usage: python extractor.py <path-to-receipt-image>")
        sys.exit(1)

    # Windows terminals often default to a legacy codepage (e.g. cp1252) that
    # can't encode non-Latin scripts (Thai, Japanese, etc.), which would crash
    # print() below. Force UTF-8 so any merchant name displays instead of
    # erroring out. errors="replace" is a last-resort safety net, not the
    # normal path.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    _load_key_from_secrets()

    path = sys.argv[1]
    guessed_type = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        result = extract_receipt(f.read(), media_type=guessed_type)

    # ensure_ascii=False so non-Latin merchant names (Thai, Japanese, etc.)
    # print as readable text instead of \uXXXX escapes. The extracted data was
    # correct either way — this only affects how it's displayed here.
    print(json.dumps(result, indent=2, ensure_ascii=False))
