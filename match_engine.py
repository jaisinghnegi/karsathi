"""
match_engine.py — KarSathi
Matches a payment to open invoices using Groq for intelligent understanding.
Groq decides if "Ramesh" = "Ramesh Traders", handles nicknames, abbreviations.
"""

import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


async def match_payment_to_invoice(
    payment: dict,
    open_invoices: list[dict],
) -> tuple[str, dict | None]:
    """
    Uses Groq to intelligently match a payment to an open invoice.
    Returns ("exact" | "fuzzy" | "none", matched_invoice | None)
    """
    if not open_invoices or not payment.get("vendor_name") or not payment.get("amount"):
        return ("none", None)

    # Build a compact invoice list for the prompt
    invoice_list = "\n".join([
        f'{i+1}. id={inv["id"]} vendor="{inv["vendor_name"]}" amount={inv["amount"]} date={inv["invoice_date"]}'
        for i, inv in enumerate(open_invoices)
    ])

    prompt = f"""Match this payment to one of the open invoices below.

Payment: vendor="{payment.get('vendor_name')}" amount={payment.get('amount')}

Open invoices:
{invoice_list}

Output ONLY a JSON object, no explanation:
- "exact" if vendor clearly refers to same company (abbreviations/short names count) AND amount within 5%
- "fuzzy" if vendor possibly same OR amount close but uncertain
- "none" if no match

Example output: {{"match": "exact", "invoice_id": "abc-123"}}
If no match: {{"match": "none", "invoice_id": null}}"""

    try:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a JSON-only responder. Output only valid JSON, no explanation."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 80,
            "temperature": 0.0,
        }
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(GROQ_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        raw = data["choices"][0]["message"]["content"].strip()
        # Extract JSON
        start, end = raw.find("{"), raw.rfind("}")
        json_str = raw[start:end + 1]  # type: ignore[index]
        result = json.loads(json_str)

        match_type = result.get("match", "none")
        invoice_id = result.get("invoice_id")

        if match_type in ("exact", "fuzzy") and invoice_id:
            matched = next((inv for inv in open_invoices if inv["id"] == invoice_id), None)
            return (match_type, matched)

        return ("none", None)

    except Exception as e:
        print(f"[MatchEngine] error: {e}")
        return ("none", None)
