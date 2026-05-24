"""
pdf_parser.py — KarSathi
Parses invoice PDFs using pdfplumber for text extraction + Groq for structuring.
Same output contract as invoice_parser.py: {vendor_name, amount, invoice_date} or {error}.
"""

import io
import json
import os

import httpx
import pdfplumber
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

PDF_EXTRACTION_PROMPT = """Extract invoice data from the text below. Output ONLY a JSON object, no explanation, no markdown.

STRICT RULES — read carefully:

vendor_name:
  - The company or person who ISSUED/SENT this invoice (the SELLER, the SUPPLIER)
  - Look for: company letterhead at the top, "Bill From", "Seller", "Supplier", "From"
  - NEVER pick the buyer, customer, ship-to address, or "Bill To" party

amount:
  - The GRAND TOTAL or TOTAL AMOUNT DUE — the final amount to be paid
  - Look for: "Grand Total", "Total Amount", "Amount Due", "Net Payable", "Invoice Total"
  - NEVER pick subtotals, line item amounts, or tax-only amounts
  - Return as a plain number only — no commas, no currency symbols (e.g. 47200 not ₹47,200)

invoice_date:
  - The date the invoice was ISSUED — NOT the due date, NOT delivery date, NOT PO date
  - Look for: "Invoice Date", "Date of Issue", "Billing Date"
  - Format: YYYY-MM-DD

Output exactly this format:
{"vendor_name": "ABC Traders", "amount": 47200, "invoice_date": "2026-04-18"}

If not an invoice: {"error": "not_an_invoice"}
If a field is unreadable: use null for that field only.

Invoice text:
"""


def _extract_json(raw: str) -> dict:
    if not raw:
        raise ValueError("Empty response from model")
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    return json.loads(raw[start:end + 1])  # type: ignore[index]


async def parse_invoice_from_pdf_url(pdf_url: str, whatsapp_token: str) -> dict:
    """
    Downloads a PDF from a WhatsApp CDN URL, extracts text with pdfplumber,
    sends it to Groq, and returns structured invoice fields.

    Returns a dict with keys: vendor_name, amount, invoice_date
    On failure: {"error": "<reason>"}
    """
    try:
        # Step 1: Download PDF from WhatsApp CDN
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                pdf_url,
                headers={"Authorization": f"Bearer {whatsapp_token}"},
            )
            resp.raise_for_status()
            pdf_bytes = resp.content

        # Step 2: Extract text with pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
        text = "\n".join(pages_text).strip()

        if not text:
            return {"error": "pdf_no_text"}

        # Truncate to 2000 chars to stay within token limits
        text = text[:2000]

        # Step 3: Send to Groq text model
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a JSON-only responder. Output only valid JSON, no explanation.",
                },
                {
                    "role": "user",
                    "content": PDF_EXTRACTION_PROMPT + text,
                },
            ],
            "max_tokens": 200,
            "temperature": 0.0,
        }
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            groq_resp = await client.post(GROQ_API_URL, json=payload, headers=headers)
            groq_resp.raise_for_status()
            data = groq_resp.json()

        raw_content = data["choices"][0]["message"]["content"].strip()
        return _extract_json(raw_content)

    except Exception as e:
        print(f"[PDFParser] error: {e}")
        return {"error": str(e)}
