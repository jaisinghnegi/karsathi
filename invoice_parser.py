"""
invoice_parser.py — KarSathi
Parses invoice photos using the Groq vision model.
Accepts WhatsApp CDN image URLs and returns structured invoice data.
"""

import base64
import json
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

INVOICE_EXTRACTION_PROMPT = """Extract invoice data. Output ONLY a JSON object, no explanation, no markdown.

STRICT RULES — read carefully:

vendor_name:
  - The company or person who ISSUED/SENT this invoice (the SELLER, the SUPPLIER)
  - Look for: company letterhead at the top, "Bill From", "Seller", "Supplier", "From"
  - NEVER pick the buyer, customer, ship-to address, or "Bill To" party
  - If the invoice is from "Ramesh Traders" to "My Company", vendor_name = "Ramesh Traders"

amount:
  - The GRAND TOTAL or TOTAL AMOUNT DUE — the final amount to be paid
  - Look for: "Grand Total", "Total Amount", "Amount Due", "Net Payable", "Invoice Total"
  - NEVER pick subtotals, line item amounts, tax amounts, or partial amounts
  - Return as a plain number only — no commas, no currency symbols (e.g. 47200 not ₹47,200)

invoice_date:
  - The date the invoice was ISSUED — NOT the due date, NOT delivery date, NOT PO date
  - Look for: "Invoice Date", "Date of Issue", "Billing Date"
  - Format: YYYY-MM-DD

payment_days:
  - Number of days allowed for payment, if explicitly stated on the invoice
  - Look for: "Net 30", "Payment due in 45 days", "Due within 15 days", "Credit period: 60 days"
  - Return as a plain integer (e.g. 30, 45, 60)
  - If not mentioned anywhere on the invoice: use null

Output exactly this format:
{"vendor_name": "ABC Traders", "amount": 47200, "invoice_date": "2026-04-18", "payment_days": 30}

If payment_days not stated: {"vendor_name": "ABC Traders", "amount": 47200, "invoice_date": "2026-04-18", "payment_days": null}
If not an invoice: {"error": "not_an_invoice"}
If a field is unreadable: use null for that field only."""


def _extract_json(raw: str) -> dict:
    """
    Extracts the first valid JSON object from the response.
    Handles markdown fences, explanatory text, and nested structures.
    """
    if not raw:
        raise ValueError("Empty response from model")
    # Try direct parse first
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass
    # Find outermost { ... } block
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    json_str = raw[start : end + 1]  # type: ignore[index]
    return json.loads(json_str)


async def parse_invoice_from_url(image_url: str, whatsapp_token: str) -> dict:
    """
    Downloads an invoice image from a WhatsApp CDN URL, encodes it as base64,
    sends it to the Groq vision model, and returns extracted invoice fields.

    Returns a dict with keys: vendor_name, amount, invoice_date
    On failure or non-invoice image: {"error": "<reason>"}
    """
    try:
        # Step 1: Download the image from WhatsApp CDN
        async with httpx.AsyncClient(timeout=30) as client:
            img_response = await client.get(
                image_url,
                headers={"Authorization": f"Bearer {whatsapp_token}"},
            )
            img_response.raise_for_status()
            image_bytes = img_response.content

        # Step 2: Base64-encode the image
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Detect MIME type from response content-type, fallback to jpeg
        content_type = img_response.headers.get("content-type", "image/jpeg")
        # Strip parameters like "; charset=utf-8" if present
        mime_type = content_type.split(";")[0].strip()
        if mime_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            mime_type = "image/jpeg"

        data_url = f"data:{mime_type};base64,{image_b64}"

        # Step 3: Send to Groq vision model
        payload = {
            "model": VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                        {
                            "type": "text",
                            "text": INVOICE_EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
            "max_tokens": 200,
            "temperature": 0.0,
        }

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60) as client:
            groq_response = await client.post(GROQ_API_URL, json=payload, headers=headers)
            groq_response.raise_for_status()
            data = groq_response.json()

        # Step 4: Parse and return the JSON response
        raw_content = data["choices"][0]["message"]["content"].strip()
        result = _extract_json(raw_content)
        return result

    except Exception as e:
        print(f"[InvoiceParser] error: {e}")
        return {"error": str(e)}
