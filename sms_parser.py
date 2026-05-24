"""
sms_parser.py — KarSathi
Extracts payment information from bank SMS / UPI notification text
using the Groq text model.
"""

import json
import os
import re
from datetime import date

import httpx
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
TEXT_MODEL = "llama-3.3-70b-versatile"

_TODAY = None  # Overridable in tests


def _today_str() -> str:
    """Returns today's date as YYYY-MM-DD. Isolated for easy test mocking."""
    return date.today().isoformat()


SMS_EXTRACTION_PROMPT = (
    "Extract payment information from this bank SMS or UPI message.\n"
    "Return ONLY valid JSON:\n"
    "- vendor_name: who was paid (string or null)\n"
    "- amount: amount paid as number only (number or null)\n"
    f"- payment_date: date in YYYY-MM-DD format (use today's date if not specified)\n"
    "\n"
    'Example: {"vendor_name": "Ramesh Traders", "amount": 45000, "payment_date": "2026-03-15"}\n'
    'If not a payment message, return: {"error": "not_a_payment"}'
)


def _extract_json(raw: str) -> dict:
    """
    Strips markdown code fences if present, then parses JSON.
    """
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned.strip())


async def parse_sms(text: str) -> dict:
    """
    Extracts vendor_name, amount, and payment_date from a bank SMS string.

    Returns a dict:
    - {"vendor_name": str|None, "amount": float|None, "payment_date": "YYYY-MM-DD"}
    - {"error": "not_a_payment"} if the message is not a payment notification
    - {"error": "<exception message>"} on any failure
    """
    # Inject today's date into the prompt so the model uses it as fallback
    prompt_with_date = (
        f"Today's date is {_today_str()}.\n\n"
        + SMS_EXTRACTION_PROMPT
    )

    payload = {
        "model": TEXT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": prompt_with_date,
            },
            {
                "role": "user",
                "content": text,
            },
        ],
        "max_tokens": 100,
        "temperature": 0.0,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(GROQ_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        raw_content = data["choices"][0]["message"]["content"].strip()
        result = _extract_json(raw_content)
        return result

    except Exception as e:
        return {"error": str(e)}
