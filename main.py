import os
import re
import json
import asyncio
import httpx
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request, Query, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from reminders import start_scheduler
from invoice_parser import parse_invoice_from_url
from pdf_parser import parse_invoice_from_pdf_url
from sms_parser import parse_sms
from match_engine import match_payment_to_invoice
from risk_engine import calculate_risk, format_risk_message
from compliance_engine import (
    get_upcoming_deadlines, detect_laws, query_kg_for_laws, query_kg_actions_only,
    format_gst_calendar_message,
)
from database import (
    get_or_create_user, save_message, get_conversation_history,
    update_user_profile, get_client,
    get_vendor, create_vendor, update_vendor, set_vendor_msme_status,
    get_vendors, get_msme_vendors, get_vendor_invoices, get_overdue_msme_invoices,
    create_invoice, get_open_invoices, mark_invoice_paid, get_all_invoices,
    save_feedback, delete_user_data,
    get_user_facts, save_user_fact,
    get_conversation_summary, save_conversation_summary, get_conversation_count,
)
from form_i_engine import (
    assess_form_i, format_form_i_report,
    format_vendor_summary, format_vendor_invoices,
)

load_dotenv()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

GROQ_DOWN_MESSAGE = (
    "Abhi thoda technical issue aa gaya hai — 1-2 minute mein dobara try karo. "
    "Agar problem continue ho toh mujhe batao."
)

SYSTEM_PROMPT = """You are KarSathi — a CA friend texting on WhatsApp. Not a chatbot. Not a formal advisor. A friend who happens to know everything about Indian business compliance.

MOST IMPORTANT RULE — HOW YOU WRITE:
- Write like a friend texting, not a report being filed
- Maximum 2-3 short sentences per reply. Never more.
- No bullet points. No numbered lists. No bold headers. No structured formatting.
- No filler: never say "Great question!", "Sure!", "Absolutely!", "Of course!"
- If something needs more explanation, break it into multiple back-and-forth messages — don't dump everything at once
- Simple factual question (date, yes/no, single fact, definition) = ONE sentence. Full stop. No follow-up. No tips. No "aur kuch poochha ho toh batao". Nothing else.
  Wrong: "GSTR-3B ki due date 20 tarikh hai. Aapko ITC bhi reconcile karna mat bhoolna. Koi sawaal ho toh poochhein."
  Right: "GSTR-3B ki due date 20 tarikh hai."
  Wrong: "Haan, GST registration mandatory hai. Iske alawa FSSAI bhi dekhna chahiye aur Udyam bhi."
  Right: "Haan, ₹40L turnover ke upar GST mandatory hai."
- Longer answer (2-3 sentences) only when user asks "how", "explain", "kya karna chahiye", or a multi-part question.

TONE:
- Frank and direct. Like a doctor who gives you the diagnosis straight.
- Say "₹50/din penalty lagega" not "there may be some penalties"
- Warm but never fluffy
- NEVER say happy birthday, good morning, or any seasonal/personal greeting unless the user said it first
- NEVER assume or invent personal details not explicitly in the conversation — no birthdays, no anniversaries, nothing
- Only reference what the user has told you: name, state, turnover, gst_status, business_type, employee count

CRITICAL — NEVER REPEAT A QUESTION:
Check conversation history before asking anything. If user has already answered, do NOT ask again.
If USER_PROFILE shows tds_on_salary = false: salary is below ₹7L, TDS is zero — conclude it and move on. Never ask again.
If USER_PROFILE shows tds_on_salary = true: TDS is applicable — tell them what to do next.
When user says "kam hai" or "zyada hai" in context of salary — treat it as a clear answer, store it, conclude immediately.

LANGUAGE — STRICT RULES, NO EXCEPTIONS:

Hindi mode (user chose Hindi OR writes in Devanagari script):
- Every word in pure Devanagari script. No romanised words at all.
- Numbers (₹500, 45 दिन), symbols (%, /) and proper nouns (GST, FSSAI, ITR) are the ONLY allowed English characters.
- Wrong: "GST return file karna padega" — this is Hinglish, NOT allowed
- Right: "जीएसटी रिटर्न दाखिल करना होगा"
- Wrong: "penalty lagegi, register karo, deadline hai"
- Right: "जुर्माना लगेगा, पंजीकरण कराएं, अंतिम तिथि है"
- Once Hindi is chosen: stay in pure Devanagari forever. Never drift back to Hinglish.

English mode (user chose English OR writes in English):
- Every sentence stays in English. Do not mix Hindi or Hinglish mid-reply.
- Wrong: "You should file your return — GST bharna zaroori hai"
- Right: "You should file your GST return."

Hinglish (user writes mixed without explicitly choosing): match their exact mix.

First message from any new user: ask "हिंदी में बात करें या English में?"
After language is chosen: never ask again, never switch.

WHAT YOU KNOW:
- GST filing deadlines, registration thresholds, ITC
- FSSAI (mandatory for any food business)
- MSMED Act — vendors paid after 45 days = penalty + Section 43B(h) tax loss
- TDS on salary, contractor payments, rent
- Advance tax, ITR deadlines
- Shops & Establishment Act (state-specific)

TDS — TEEN ALAG CHEEZEIN HAIN, KABHI MIX MAT KARO:

1. TDS DEDUCTION — salary/payment se tax kaatna
   - Sirf tab zaroori jab employee salary > ₹7 lakh/year (new regime)
   - Monthly activity
   - tds_on_salary profile field se pata chalta hai

2. TDS DEPOSIT — kaata hua TDS govt ko dena
   - Due: agle mahine ki 7 tarikh
   - TDS deduct karne ke baad zaroori

3. TDS RETURN — quarterly Form 24Q/26Q filing
   - Due dates: 31 May, 31 July, 31 Oct, 31 Jan
   - SABHI registered TDS deductors ke liye mandatory — chahe TDS kata ho ya nahi
   - NIL return bhi valid hai agar koi TDS nahi kata
   - Portal: incometax.gov.in

RULE: Agar user TDS RETURN poochhe — sirf point 3 batao, deduction mat poochho.
Agar user TDS DEDUCTION poochhe — sirf point 1 batao.
tds_on_salary = false ka matlab sirf hai ki deduction zaroori nahi — TDS RETURN filing pe koi asar nahi.

DEADLINE FORMAT — when live deadline data is injected, always present it exactly like this:
🔴 31 May — TDS Return (kal!)
🟡 11 Jun — GSTR-1 (16 din)
🟢 15 Sep — Advance Tax Q3 (112 din)
The data is already pre-formatted — just copy the bullet list as-is, then add ONE question maximum.
Never convert it into a paragraph. Never add extra commentary above the list.

Gather their profile naturally over conversation — business type, state, turnover, GST status.
When you know enough, flag the 1 biggest risk for their situation. Just 1. Not a list."""


def _build_system_prompt(extra_context: str = "") -> str:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    date_block = (
        f"TODAY (IST): {now.strftime('%A, %d %B %Y')} | "
        f"Time: {now.strftime('%I:%M %p')} IST\n"
        f"Use this for ALL deadline calculations. Never assume or guess the date."
    )
    parts = [date_block, SYSTEM_PROMPT]
    if extra_context:
        parts.append(
            "LIVE DATA FOR THIS RESPONSE (use this to answer accurately and naturally "
            "— do not mention it was injected, just answer like you already know it):\n"
            + extra_context
        )
    return "\n\n".join(parts)

PROFILE_EXTRACTOR_PROMPT = """You are a data extractor. Given a conversation message, extract any of these fields if clearly stated:
- language: "hindi" or "english" (only if user explicitly chose one)
- business_type: e.g. "kirana", "restaurant", "manufacturer", "trader", "service"
- state: Indian state name in English, e.g. "Rajasthan", "Maharashtra"
- city: city name if mentioned
- turnover_bracket: one of "under_40L", "40L_to_1.5Cr", "above_1.5Cr"
- gst_status: "registered" if user says they have GST/GSTIN, "not_registered" if they say they don't have GST
- qrmp_opted: "true" if user says they file quarterly / are in QRMP scheme, "false" if they say monthly filing or have not opted into QRMP
- tds_on_salary: "false" if user says employee salary is below ₹7 lakh/year or says "kam hai", "true" if above ₹7 lakh/year or says "zyada hai"

Return ONLY valid JSON with the fields found. If nothing found, return {}.
Never guess. Only extract what is explicitly stated.

Examples:
User: "Hindi mein baat karte hain" → {"language": "hindi"}
User: "Mera kirana store hai Jaipur mein" → {"business_type": "kirana", "city": "Jaipur"}
User: "Rajasthan se hoon" → {"state": "Rajasthan"}
User: "40 lakh se kam turnover hai" → {"turnover_bracket": "under_40L"}
User: "Haan GST registered hoon" → {"gst_status": "registered"}
User: "GST nahi hai mere paas" → {"gst_status": "not_registered"}
User: "Main quarterly QRMP mein hoon" → {"qrmp_opted": "true"}
User: "Monthly filing karta hoon" → {"qrmp_opted": "false"}
User: "Salary 7 lakh se kam hai" → {"tds_on_salary": "false"}
User: "Employees ko 10 lakh deta hoon" → {"tds_on_salary": "true"}
User: "kam hai" → {"tds_on_salary": "false"}
User: "just browsing" → {}"""

INTENT_CLASSIFIER_PROMPT = """Classify this WhatsApp message into exactly one category. Return ONLY the category string, nothing else.

Categories:
- sms_payment: bank SMS, UPI confirmation, payment sent/received message
- invoice_question: question about invoices, payments due, Form I, 43B
- gst_compliance: asking about ANY filing due dates or deadlines — GST, advance tax, income tax, TDS, PF, ESI. Examples: "GST kab bharna hai", "GSTR-3B ki date kya hai", "advance tax ki deadline kya hai", "ITR kab tak bharna hai", "TDS kab jama karna hai", "kitne din baaki hain", "koi deadline hai kya abhi"
- paperwork_guidance: user asking HOW to do a specific registration or paperwork — "kaise register karein", "kya documents chahiye", "steps batao", "kaise banwao", "process kya hai", "kaise apply karein" for GST, FSSAI, Udyam, Shops Act, PF, ESI, IEC, factory licence, trade licence
- general_compliance: ANY other compliance question — why GST is needed, FSSAI, Shops Act, Udyam, trade licence, penalties, what is GST, GST rates, rules, obligations
- delete_account: user wants to delete account, remove data, stop service, unsubscribe
- greeting: user is saying hi/hello/namaste/haan/hey/wassup/good morning or restarting conversation after a gap
- other: general chat, anything else that doesn't fit above

Message: """

FACT_EXTRACTION_PROMPT = """You are a silent memory extractor for karSathi.

Extract any personal or business facts the user just mentioned that are worth remembering long-term.

Only extract concrete, named facts — not opinions, questions, or vague statements.

Examples of facts to extract:
- "mera CA Prasanth hai" → {"fact_key": "ca_name", "fact_value": "Prasanth"}
- "meri dukaan ka naam Sharma Traders hai" → {"fact_key": "business_name", "fact_value": "Sharma Traders"}
- "mera partner Ramesh hai" → {"fact_key": "partner_name", "fact_value": "Ramesh"}
- "mera HDFC account hai" → {"fact_key": "bank_name", "fact_value": "HDFC"}
- "mera GST number 27AAAAA1234A1Z5 hai" → {"fact_key": "gst_number", "fact_value": "27AAAAA1234A1Z5"}
- "meri dukaan Vaishali Nagar mein hai" → {"fact_key": "shop_location", "fact_value": "Vaishali Nagar"}
- "mera accountant ka number 9876543210 hai" → {"fact_key": "accountant_phone", "fact_value": "9876543210"}
- "mera udyam number UA01A0000001 hai" → {"fact_key": "udyam_number", "fact_value": "UA01A0000001"}

If no extractable fact is found, return: {"fact_key": null}

Return JSON only. No explanation. No markdown. No extra text."""

SUMMARY_PROMPT = """Summarise this conversation between a business owner and karSathi compliance assistant.

Extract and preserve:
- Any compliance issues discussed
- Any deadlines mentioned or agreed upon
- Any decisions made by the user
- Any problems or concerns raised
- Any follow-up actions the user said they would take
- Any key facts shared (business type, location, GST status, etc.)

Write the summary in 5-8 bullet points in English. Keep it factual. No opinions."""


# ── Proactive onboarding messages ─────────────────────────────────────────────


def _udyam_guidance_msg() -> str:
    return (
        "Theek hai! Ek kaam zaroor karo — *Udyam Registration* karwa lo (bilkul free hai):\n\n"
        "udyamregistration.gov.in par register karo. Isse milega:\n"
        "• Sarkari tenders mein priority\n"
        "• Bank loans pe kam interest\n"
        "• MSMED Act protection\n"
        "• State government schemes ka fayda\n\n"
        "Kya main Udyam registration ke steps guide karoon? Haan ya Nahi batao."
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler = start_scheduler()
    yield
    scheduler.shutdown()


app = FastAPI(title="KarSathi WhatsApp Webhook", lifespan=lifespan)

# Fallback in-memory store — used only when Supabase is unreachable
_memory_fallback: dict = {}

# Pending payment confirmations — { wa_id: invoice_dict }
_pending_confirmations: dict = {}

# Delete account flow — { wa_id: "awaiting_feedback" | "awaiting_confirm" }
_pending_deletions: dict = {}
_deletion_feedback: dict = {}

# Invoice parse confirmation — { wa_id: parsed_invoice_dict }
_pending_invoice_confirmations: dict = {}


def _get_fallback(wa_id: str) -> dict:
    if wa_id not in _memory_fallback:
        _memory_fallback[wa_id] = {"messages": [], "profile": {}}
    return _memory_fallback[wa_id]


# ── Keyword-based profile extractor (zero Groq calls) ─────────────────────────
# TODO BEFORE PRODUCTION: re-enable Groq fallback for edge cases if accuracy drops

_INDIAN_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "delhi", "jammu & kashmir", "jammu and kashmir", "ladakh",
    "andaman and nicobar", "chandigarh", "dadra and nagar haveli", "daman and diu",
    "lakshadweep", "puducherry", "pondicherry",
}

_BUSINESS_TYPES = {
    "kirana": "kirana", "grocery": "grocery", "restaurant": "restaurant",
    "dhaba": "dhaba", "hotel": "hotel", "bakery": "bakery",
    "manufacturer": "manufacturer", "manufacturing": "manufacturer",
    "trader": "trader", "trading": "trader", "wholesale": "wholesaler",
    "retail": "retailer", "retailer": "retailer",
    "service": "service", "consultant": "consultant", "consulting": "consultant",
    "agency": "agency", "shop": "shop", "store": "store",
    "software": "software", "it company": "software", "tech": "software",
    "pharmacy": "pharmacy", "medical": "medical",
    "construction": "construction", "contractor": "contractor",
    "salon": "salon", "boutique": "boutique",
}

_RE_TURNOVER = re.compile(
    r'(\d+(?:\.\d+)?)\s*(?:lakh|lac|l\b|crore|cr\b)',
    re.IGNORECASE,
)
_RE_GST_YES = re.compile(
    r'\b(gst registered|gst hai|gstin hai|gst le rakha|have gst|gst liya|registered for gst|haan gst)\b',
    re.IGNORECASE,
)
_RE_GST_NO = re.compile(
    r'\b(gst nahi|no gst|gst nahi hai|gst nahi liya|not registered|gst register nahi)\b',
    re.IGNORECASE,
)
_RE_QRMP_YES = re.compile(
    r'\b(qrmp|quarterly filing|quarterly return|teen mahine mein ek baar)\b',
    re.IGNORECASE,
)
_RE_QRMP_NO = re.compile(
    r'\b(monthly filing|har mahine|monthly return|monthly gst)\b',
    re.IGNORECASE,
)
_RE_TDS_LOW = re.compile(
    r'\b(kam hai|salary kam|7 lakh se kam|below 7|less than 7|nahi katna|zero tds)\b',
    re.IGNORECASE,
)
_RE_TDS_HIGH = re.compile(
    r'\b(zyada hai|salary zyada|7 lakh se zyada|above 7|more than 7|tds katna|tds applicable)\b',
    re.IGNORECASE,
)
_RE_LANG_HINDI = re.compile(
    r'\b(hindi mein|hindi me|hindi bol|hindi chahiye|hindi)\b',
    re.IGNORECASE,
)
_RE_LANG_ENG = re.compile(
    r'\b(english mein|english me|in english|speak english|english please)\b',
    re.IGNORECASE,
)


def _fast_extract_profile(text: str) -> dict:
    """Zero-Groq keyword extraction. Covers ~90% of real messages."""
    result = {}
    lower = text.lower()

    # Language
    if _RE_LANG_HINDI.search(text):
        result["language"] = "hindi"
    elif _RE_LANG_ENG.search(text):
        result["language"] = "english"

    # State
    for state in _INDIAN_STATES:
        if state in lower:
            result["state"] = state.title()
            break

    # Business type
    for keyword, btype in _BUSINESS_TYPES.items():
        if keyword in lower:
            result["business_type"] = btype
            break

    # Turnover bracket
    m = _RE_TURNOVER.search(lower)
    if m:
        val = float(m.group(1))
        unit = m.group(0).lower()
        if "crore" in unit or "cr" in unit:
            val_lakh = val * 100
        else:
            val_lakh = val
        if val_lakh < 40:
            result["turnover_bracket"] = "under_40L"
        elif val_lakh <= 150:
            result["turnover_bracket"] = "40L_to_1.5Cr"
        else:
            result["turnover_bracket"] = "above_1.5Cr"

    # GST status
    if _RE_GST_YES.search(text):
        result["gst_status"] = "registered"
    elif _RE_GST_NO.search(text):
        result["gst_status"] = "not_registered"

    # QRMP
    if _RE_QRMP_YES.search(text):
        result["qrmp_opted"] = "true"
    elif _RE_QRMP_NO.search(text):
        result["qrmp_opted"] = "false"

    # TDS on salary
    if _RE_TDS_LOW.search(text):
        result["tds_on_salary"] = "false"
    elif _RE_TDS_HIGH.search(text):
        result["tds_on_salary"] = "true"

    return result


async def extract_and_update_profile(phone_number: str, user_message: str) -> dict:
    """Keyword-based profile extraction — zero Groq calls, instant."""
    try:
        extracted = _fast_extract_profile(user_message)
        for field, value in extracted.items():
            if value:
                await update_user_profile(phone_number, field, str(value))
        return extracted
    except Exception:
        return {}


_RE_DATE_QUERY = re.compile(
    r'\b(aaj date|date kya|aaj kya|time kya|kya din|kaun sa din|kaun si date|'
    r'aaj ka din|today date|what.*date|what.*time|aaj.*time)\b',
    re.IGNORECASE,
)

_RE_SMS = re.compile(
    r'\b(credited|debited|upi ref|neft|imps|a/c.*cr|a/c.*dr|'
    r'rs\.?\s*\d.*credited|inr.*credited|payment received|transferred to|'
    r'transaction id|txn id|ref no)\b',
    re.IGNORECASE,
)
_RE_DEADLINE = re.compile(
    r'\b(deadlines?|due date|last date|kab bharna|kitne din|date kya hai|kab tak|'
    r'gstr-?1|gstr-?3b|gstr-?9|gstr-?\d|advance tax|itr kab|tds kab|pf kab|'
    r'esi kab|filing kab|return kab|kab jama|return bharna|koi deadline|'
    r'tds return|24q|26q|tds file|tds bharna|tds deposit kab|'
    r'calendar|calender|saari deadlines|sab deadlines|all deadlines|sari deadlines)\b',
    re.IGNORECASE,
)
_RE_DELETE = re.compile(
    r'\b(delete account|delete my account|remove data|band karo|data delete|'
    r'unsubscribe|stop service)\b',
    re.IGNORECASE,
)
# Matches "how to register / get / apply for" paperwork queries
_RE_PAPERWORK = re.compile(
    r'\b(kaise register|registration kaise|kaise le|kaise milega|kaise banwao|kaise banao|'
    r'kaise apply|apply kaise|kaise karta|kaise karein|kaise kare|'
    r'registration process|documents chahiye|kya documents|kaun se documents|'
    r'steps batao|step by step|kaise shuru|kaise start|'
    r'kaise loon|kaise lu|kaise lena|kaise milegi|kaise milta|'
    r'how to register|how to get|how to apply|registration karo|'
    r'iec kaise|iec lena|iec banwana|iec update|iec renew|iec kab|iec activate|'
    r'factory licence kaise|udyam kaise|fssai kaise|gst registration kaise|'
    r'shops act kaise|pf registration|esi registration|epf kaise)\b',
    re.IGNORECASE,
)


_RE_VENDOR_LIST = re.compile(
    r'\b(vendor list|vendors dikhao|vendors dikha|mere vendors|mera vendor|apne vendors|'
    r'sabhi vendors|all vendors|supplier list|suppliers dikhao|'
    r'kitna dena hai|kitna baaki hai|outstanding kya hai|unpaid invoices|'
    r'open invoices|pending invoices|invoice list|invoices dikhao)\b',
    re.IGNORECASE,
)
_RE_MSME_STATUS = re.compile(
    r'\b(\w[\w\s]{1,30}?)\s+(msme hai|msme registered hai|msme nahi hai|msme nahi|'
    r'msme register hai|msme h|not msme|non msme)\b',
    re.IGNORECASE,
)
_RE_FORM_I = re.compile(
    r'\b(form[\s\-]?i\b|form[\s\-]?1\b|form i filing|form i bharna|form i file|'
    r'msmed filing|msme form|half[\s\-]?yearly filing|half yearly msme|'
    r'form i check|form i assess|form i kab|form i due)\b',
    re.IGNORECASE,
)


def _fast_classify(text: str) -> str | None:
    """Keyword-based intent — O(1), no Groq call. Returns None if ambiguous.
    Deadline check runs before date_query so "due date kya hai" isn't misclassified.
    Paperwork check runs before general_compliance to give it a focused handler.
    """
    if _RE_DELETE.search(text):
        return "delete_account"
    if _RE_SMS.search(text):
        return "sms_payment"
    if _RE_FORM_I.search(text):
        return "form_i"
    if _RE_VENDOR_LIST.search(text):
        return "vendor_list"
    if _RE_MSME_STATUS.search(text):
        return "msme_status_update"
    if _RE_DEADLINE.search(text):
        return "gst_compliance"
    if _RE_DATE_QUERY.search(text):
        return "date_query"
    if _RE_PAPERWORK.search(text):
        return "paperwork_guidance"
    return None  # fall back to Groq


async def classify_intent(text: str) -> str:
    try:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": INTENT_CLASSIFIER_PROMPT + text}],
            "max_tokens": 5,
            "temperature": 0.0,
        }
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(GROQ_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        intent = data["choices"][0]["message"]["content"].strip().lower()
        valid = {"sms_payment", "invoice_question", "gst_compliance", "paperwork_guidance", "general_compliance", "delete_account", "greeting", "other"}
        return intent if intent in valid else "other"
    except Exception:
        return "other"


_TRIVIAL_MESSAGES = {
    "haan", "nahi", "yes", "no", "ok", "okay", "theek hai", "confirm",
    "ha", "han", "haa", "nai", "naa", "thik hai",
}


async def _extract_and_save_facts(wa_id: str, user_text: str) -> None:
    """Silently extracts and saves named facts from user message. Skips short/trivial inputs."""
    if len(user_text.strip()) < 15:
        return
    if user_text.strip().lower() in _TRIVIAL_MESSAGES:
        return
    try:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": FACT_EXTRACTION_PROMPT},
                {"role": "user", "content": user_text},
            ],
            "max_tokens": 60,
            "temperature": 0.0,
        }
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(GROQ_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
        data = json.loads(resp.json()["choices"][0]["message"]["content"].strip())
        if data.get("fact_key") and data.get("fact_value"):
            await save_user_fact(wa_id, data["fact_key"], str(data["fact_value"]))
            print(f"[Facts] Saved for {wa_id}: {data['fact_key']} = {data['fact_value']}")
    except Exception as e:
        print(f"[Facts] Extraction failed for {wa_id}: {e}")


async def generate_and_save_summary(wa_id: str) -> None:
    """Generates a rolling summary of the last 20 messages and saves it."""
    try:
        history = await get_conversation_history(wa_id, limit=20)
        if not history:
            return
        conv_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'KarSathi'}: {m['content']}"
            for m in history
        )
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": conv_text},
            ],
            "max_tokens": 300,
            "temperature": 0.3,
        }
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(GROQ_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
        summary = resp.json()["choices"][0]["message"]["content"].strip()
        count = await get_conversation_count(wa_id)
        await save_conversation_summary(wa_id, summary, count)
        print(f"[Summary] Saved for {wa_id} at {count} messages")
    except Exception as e:
        print(f"[Summary] Failed for {wa_id}: {e}")


async def _maybe_summarize(wa_id: str) -> None:
    """Triggers summary generation every 20 messages."""
    try:
        count = await get_conversation_count(wa_id)
        if count > 0 and count % 20 == 0:
            await generate_and_save_summary(wa_id)
    except Exception as e:
        print(f"[Summary] Count check failed for {wa_id}: {e}")


async def get_groq_response(wa_id: str, user_message: str, extra_context: str = "") -> str:
    user, history, user_facts_dict, conv_summary = await asyncio.gather(
        get_or_create_user(wa_id),
        get_conversation_history(wa_id, limit=20),
        get_user_facts(wa_id),
        get_conversation_summary(wa_id),
    )

    # Build layered context: summary → facts → profile overrides → KG/deadline data
    context_blocks = []

    if conv_summary:
        context_blocks.append(f"Previous conversation summary:\n{conv_summary}")

    if user_facts_dict:
        facts_lines = "\n".join(f"- {k}: {v}" for k, v in user_facts_dict.items())
        context_blocks.append(f"User facts you know:\n{facts_lines}")

    # Inject known profile flags so Groq never asks about them again
    profile_facts = []
    tds = user.get("tds_on_salary")
    if tds is False:
        profile_facts.append(
            "tds_on_salary = false — employee salary is below ₹7L/year. "
            "TDS DEDUCTION is not required (zero tax to cut from salary). "
            "IMPORTANT: This does NOT exempt from TDS Return filing — if registered as TDS deductor, "
            "NIL return (Form 24Q/26Q) must still be filed quarterly. "
            "Do not ask about salary again."
        )
    elif tds is True:
        profile_facts.append(
            "tds_on_salary = true — employee salary exceeds ₹7L/year. TDS IS applicable under Section 192."
        )
    if profile_facts:
        context_blocks.append("USER_PROFILE (already known):\n" + "\n".join(profile_facts))

    if extra_context:
        context_blocks.append(extra_context)

    combined_context = "\n\n".join(context_blocks)

    if not history:
        fallback = _get_fallback(wa_id)
        fallback["messages"].append({"role": "user", "content": user_message})
        history_for_groq = fallback["messages"][-20:]
    else:
        fallback = _get_fallback(wa_id)
        fallback["messages"] = history.copy()
        fallback["messages"].append({"role": "user", "content": user_message})
        history_for_groq = history

    system = _build_system_prompt(combined_context)

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": system}]
                     + history_for_groq
                     + [{"role": "user", "content": user_message}],
        "max_tokens": 160,
        "temperature": 0.7,
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
        reply = data["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            print(f"[Groq] Rate limited for {wa_id} — retrying in 12s")
            await asyncio.sleep(12)
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.post(GROQ_API_URL, json=payload, headers=headers)
                    response.raise_for_status()
                    reply = response.json()["choices"][0]["message"]["content"].strip()
            except Exception as retry_e:
                print(f"[Groq] Retry failed for {wa_id}: {retry_e}")
                reply = GROQ_DOWN_MESSAGE
        else:
            print(f"[Groq] HTTP error for {wa_id}: {e}")
            reply = GROQ_DOWN_MESSAGE
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        print(f"[Groq] Connection error for {wa_id}: {type(e).__name__}")
        reply = GROQ_DOWN_MESSAGE

    await save_message(wa_id, "user", user_message)
    # Never save error/fallback replies — they corrupt future conversation context
    if reply != GROQ_DOWN_MESSAGE:
        await save_message(wa_id, "assistant", reply)

    return reply


async def send_whatsapp_message(to: str, message: str):
    phone_number_id = os.getenv("PHONE_NUMBER_ID")
    whatsapp_token = os.getenv("WHATSAPP_TOKEN")
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        if not response.is_success:
            print(f"[WA] Send failed {response.status_code}: {response.text}")
        response.raise_for_status()


def _format_confirmation_prompt(parsed: dict) -> str:
    """Formats parsed invoice details for user confirmation before saving."""
    from datetime import date as _d
    vendor_name = parsed.get("vendor_name", "Unknown")
    amount = parsed.get("amount", 0)
    invoice_date = parsed.get("invoice_date", "")
    try:
        display_date = _d.fromisoformat(invoice_date).strftime("%d %b %Y")
    except Exception:
        display_date = invoice_date
    payment_days = parsed.get("payment_days")
    payment_line = (
        f"📆 Payment Terms: {payment_days} days (invoice se liya gaya)\n"
        if payment_days else
        f"📆 Payment Terms: 45 days (default — invoice mein nahi tha)\n"
    )
    return (
        f"Invoice mein yeh details mili hain:\n\n"
        f"🏢 Supplier: {vendor_name}\n"
        f"💰 Total Amount: ₹{float(amount):,.2f}\n"
        f"📅 Invoice Date: {display_date}\n"
        f"{payment_line}\n"
        f"Kya yeh sahi hai?\n"
        f"✅ Haan — yahi save karo\n"
        f"❌ Nahi — cancel karo, main dobara bhejunga"
    )


async def _save_confirmed_invoice(from_number: str, parsed: dict) -> str:
    """Saves a confirmed invoice and returns the full risk + MSME message."""
    from datetime import date as _d, timedelta
    vendor_name = parsed["vendor_name"]
    amount = float(parsed["amount"])
    invoice_date = parsed["invoice_date"]

    user = await get_or_create_user(from_number)
    vendor = await get_vendor(from_number, vendor_name)

    if vendor and vendor.get("agreement_type") == "verbal":
        deadline_days = 15
    elif parsed.get("payment_days"):
        deadline_days = int(parsed["payment_days"])
    else:
        deadline_days = 45

    await create_invoice(from_number, vendor_name, amount, invoice_date, deadline_days)

    inv_date = _d.fromisoformat(invoice_date)
    due_date = inv_date + timedelta(days=deadline_days)
    risk = calculate_risk(
        {"due_date": due_date.isoformat(), "amount": amount},
        user.get("tax_slab", "unknown"),
    )
    risk_msg = format_risk_message(vendor_name, amount, invoice_date, risk)

    if not vendor:
        await create_vendor(from_number, vendor_name)
        msme_question = (
            f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🏢 Ek Zaroori Sawaal\n\n"
            f"Kya *{vendor_name}* ek MSME (Micro, Small or Medium Enterprise) "
            f"registered supplier hai?\n\n"
            f"Yeh isliye pooch raha hoon kyunki:\n"
            f"• Agar yeh MSME registered hai toh MSMED Act ke under aapki *legal "
            f"obligation* hai ki invoice date se 45 din ke andar payment karni hogi\n"
            f"• 45 din ke baad 25.5% annual penalty interest shuru ho jaata hai "
            f"(Section 16, MSMED Act)\n"
            f"• Aur agar payment miss hui toh yeh poora invoice amount aapki "
            f"taxable income se deductible nahi rahega — matlab zyada tax bharoge "
            f"(Section 43B(h), Income Tax Act)\n\n"
            f"Isliye confirm karna zaroori hai. Reply karo:\n"
            f"✅ Haan — MSME registered hai\n"
            f"❌ Nahi — MSME nahi hai\n"
            f"🤷 Pata nahi — main check karunga"
        )
        return risk_msg + msme_question
    else:
        return risk_msg


async def handle_invoice_image(from_number: str, image_url: str) -> str:
    whatsapp_token = os.getenv("WHATSAPP_TOKEN")
    parsed = await parse_invoice_from_url(image_url, whatsapp_token)

    if "error" in parsed:
        return (
            "Yeh invoice nahi lag raha, ya photo thodi blur hai.\n"
            "Ek clear photo bhejo ya details type kar do: vendor name, amount, aur date."
        )

    vendor_name = parsed.get("vendor_name")
    amount = parsed.get("amount")
    invoice_date = parsed.get("invoice_date")

    if not all([vendor_name, amount, invoice_date]):
        missing = [f for f, v in [("vendor name", vendor_name), ("amount", amount), ("date", invoice_date)] if not v]
        return f"Invoice mein {', '.join(missing)} clearly nahi dikh raha. Please type kar do."

    _pending_invoice_confirmations[from_number] = parsed
    return _format_confirmation_prompt(parsed)


_GREETING_WORDS = {
    "hi", "hello", "hey", "hii", "hiii", "namaste", "namaskar",
    "haan", "han", "ha", "helo", "salam", "adaab",
    "good morning", "good afternoon", "good evening", "good night",
    "yo", "sup", "wassup", "start", "menu",
}

def _is_greeting(text: str) -> bool:
    return text.strip().lower() in _GREETING_WORDS


def handle_greeting() -> str:
    return "Welcome back! Aaj kya karna chahenge?"


async def handle_form_i_assessment(from_number: str) -> str:
    """Checks if user has overdue MSME invoices and formats Form I obligation report."""
    overdue = await get_overdue_msme_invoices(from_number)
    assessment = assess_form_i(overdue)
    return format_form_i_report(assessment)


async def handle_vendor_list(from_number: str, user_text: str) -> str:
    """
    Shows vendor list with MSME status + outstanding invoices.
    If a specific vendor name is mentioned, shows their invoices only.
    """
    vendors = await get_vendors(from_number)
    open_invs = await get_open_invoices(from_number)

    # Check if a specific vendor is mentioned
    text_lower = user_text.lower()
    matched_vendor = None
    for v in vendors:
        if v["vendor_name"].lower() in text_lower:
            matched_vendor = v
            break

    if matched_vendor:
        vendor_invs = await get_vendor_invoices(from_number, matched_vendor["vendor_name"])
        return format_vendor_invoices(
            matched_vendor["vendor_name"],
            vendor_invs,
            matched_vendor.get("is_msme"),
        )

    return format_vendor_summary(vendors, open_invs)


async def handle_msme_status_update(from_number: str, user_text: str) -> str:
    """
    Detects 'VendorName MSME hai / MSME nahi hai' and updates the vendor record.
    """
    text_lower = user_text.lower()

    # Determine is_msme from the message
    if any(p in text_lower for p in ("nahi hai", "nahi h", "nahi", "not msme", "non msme")):
        is_msme = False
        label = "non-MSME mark kar diya"
        consequence = "45-day rule apply nahi hoga is vendor ke liye."
    else:
        is_msme = True
        label = "MSME registered mark kar diya"
        consequence = (
            "45-day payment rule ab apply hoga — "
            "deadline miss hone par 19.5% compund interest + Section 43B(h) tax loss."
        )

    # Find which vendor from their existing list
    vendors = await get_vendors(from_number)
    matched = None
    for v in vendors:
        if v["vendor_name"].lower() in text_lower:
            matched = v
            break

    if not matched:
        # Extract vendor name heuristically — everything before "msme"
        m = _RE_MSME_STATUS.search(user_text)
        if m:
            vendor_name_guess = m.group(1).strip()
            return (
                f"'{vendor_name_guess}' mere paas saved nahi hai abhi.\n"
                "Pehle unka invoice add karo — photo/PDF bhejo ya type karo.\n"
                "Phir MSME status set kar sakते ho."
            )
        return "Kaunsa vendor? Vendor ka naam clearly batao."

    success = await set_vendor_msme_status(from_number, matched["vendor_name"], is_msme)
    if not success:
        return f"{matched['vendor_name']} ka status update nahi hua — dobara try karo."

    return f"✅ *{matched['vendor_name']}* ko {label}.\n{consequence}"


async def handle_general_compliance(from_number: str, user_text: str) -> str:
    """Queries KG for relevant law data, injects as context, lets Groq answer in Hindi."""
    law_keys = detect_laws(user_text)
    kg_context = query_kg_for_laws(law_keys) if law_keys else ""
    return await get_groq_response(from_number, user_text, extra_context=kg_context)


async def handle_paperwork_guidance(from_number: str, user_text: str) -> str:
    """
    Handles 'how to register / apply / get paperwork done' queries.
    Injects kg_compliance_actions (step-by-step) + upcoming deadlines for the law.
    Cleaner context = more accurate step-by-step replies from Groq.
    """
    law_keys = detect_laws(user_text)
    if not law_keys:
        return await handle_general_compliance(from_number, user_text)

    kg_context = query_kg_actions_only(law_keys)
    if not kg_context:
        kg_context = query_kg_for_laws(law_keys)

    # Also inject upcoming deadline for this law key (e.g. IEC June 30 update)
    user = await get_or_create_user(from_number)
    deadline_parts = []
    for lk in law_keys:
        deadlines = get_upcoming_deadlines(user, law_key=lk, limit=2)
        for d in deadlines:
            days = d["days_until"]
            deadline_parts.append(
                f"{lk} deadline: {d['filing_name']} — {d['due_date'].strftime('%d %b %Y')} "
                f"({days} din baaki)"
            )
    if deadline_parts:
        kg_context = "\n".join(deadline_parts) + "\n\n" + kg_context

    return await get_groq_response(from_number, user_text, extra_context=kg_context)


_RE_CALENDAR_VIEW = re.compile(
    r"(sab|saari|sari|all|poori|puri|list|calendar|calender|dikhao|dikha|show|batao)\s*(deadlines?|dates?|filings?|returns?)?|"
    r"(deadline|filing|return)\s*(list|sab|saari|sari|all|calendar)",
    re.IGNORECASE,
)

async def handle_gst_compliance(from_number: str, user_text: str) -> str:
    """Injects live GST + Income Tax deadline data as context and lets Groq answer naturally."""
    user = await get_or_create_user(from_number)

    # Fast path: user wants to see the full calendar — return structured message directly
    if _RE_CALENDAR_VIEW.search(user_text):
        return format_gst_calendar_message(user)

    def _urgency(days: int) -> str:
        if days < 0:
            return f"{abs(days)} din pehle nikal gayi ⚠️"
        if days == 0:
            return "aaj!"
        if days == 1:
            return "kal!"
        if days <= 7:
            return f"{days} din"
        if days <= 30:
            return f"{days} din"
        return f"{days} din"

    def _emoji(days: int) -> str:
        return "🔴" if days <= 7 else ("🟡" if days <= 30 else "🟢")

    def _fmt_deadlines(deadlines: list, label: str) -> str:
        if not deadlines:
            return ""
        lines = []
        for d in deadlines:
            days = d["days_until"]
            penalty = d.get("penalty_per_day")
            p_str = f" — late fee ₹{int(penalty)}/din" if penalty else ""
            lines.append(
                f"{_emoji(days)} {d['due_date'].strftime('%d %b')} — "
                f"{d['filing_name']} ({_urgency(days)}){p_str}"
            )
        return (
            f"{label} (COPY THESE LINES VERBATIM — do not rewrite, do not change dates or urgency):\n"
            + "\n".join(lines)
        )

    gst_deadlines = get_upcoming_deadlines(user, law_key="GST", limit=5)

    # If QRMP status is unknown, both GSTR-1 Monthly (11th) and GSTR-1 QRMP (13th)
    # may be present. Groq must NOT assume QRMP — default is monthly.
    gst_names = [d["filing_name"] for d in gst_deadlines]
    has_monthly = any("Monthly" in n and "GSTR-1" in n for n in gst_names)
    has_qrmp    = any("QRMP" in n and "GSTR-1" in n for n in gst_names)
    qrmp_unknown = user.get("qrmp_opted") is None

    gst_part = _fmt_deadlines(gst_deadlines, "User's upcoming GST deadlines")

    if qrmp_unknown and has_monthly and has_qrmp:
        gst_part += (
            "\n\nIMPORTANT: User's QRMP status is unknown. "
            "QRMP is OPTIONAL — default for all GST filers is monthly. "
            "Do NOT assume the user is on QRMP. "
            "Say both options: GSTR-1 11th (monthly, default) OR 13th (only if QRMP opted). "
            "Then ask: 'Aap monthly filing karte hain ya QRMP quarterly scheme mein opt-in kiya hai? "
            "Default monthly hota hai jab tak aap QRMP choose na karo.'"
        )
    it_part = _fmt_deadlines(
        get_upcoming_deadlines(user, law_key="INCOME_TAX", limit=5),
        "User's upcoming Income Tax / Advance Tax deadlines"
    )

    context_parts = [p for p in [gst_part, it_part] if p]
    if context_parts:
        context = "\n\n".join(context_parts)
    else:
        gst_status = user.get("gst_status", "unknown")
        context = f"User's GST status: {gst_status}. No upcoming compliance deadlines in the near term."

    return await get_groq_response(from_number, user_text, extra_context=context)


async def handle_sms_payment(from_number: str, text: str) -> str:
    parsed = await parse_sms(text)

    if "error" in parsed:
        return await get_groq_response(from_number, text)

    open_invoices = await get_open_invoices(from_number)
    match_type, matched_invoice = await match_payment_to_invoice(parsed, open_invoices)

    amount = parsed.get("amount", 0)

    if match_type == "exact":
        await mark_invoice_paid(matched_invoice["id"])
        return (
            f"{matched_invoice['vendor_name']} "
            f"Rs.{float(matched_invoice['amount']):,.2f} — paid!\n"
            f"45-day risk cleared."
        )
    elif match_type == "fuzzy":
        inv = matched_invoice
        _pending_confirmations[from_number] = inv
        return (
            f"Yeh payment {inv['vendor_name']} wale "
            f"Rs.{float(inv['amount']):,.2f} ({inv['invoice_date']}) invoice ke liye hai?\n"
            f"Haan / Nahi"
        )
    else:
        return (
            f"Rs.{float(amount):,.2f} payment record ho gayi, lekin koi matching invoice nahi mila.\n"
            f"Kya iske liye koi invoice aane wala hai? Forward karo jab mile."
        )


@app.get("/health")
async def health():
    db_status = "connected" if get_client() else "fallback (in-memory)"
    return {"status": "KarSathi webhook is running", "db": db_status}


@app.post("/test/reminders")
async def test_reminders():
    """
    Test endpoint — triggers reminder functions in dry-run mode.
    Returns what would be sent without actually delivering to WhatsApp.
    """
    from reminders import send_gst_reminders, send_invoice_reminders
    from database import get_all_gst_users, get_all_overdue_invoices
    from compliance_engine import get_upcoming_deadlines

    # Dry-run: count what would be sent
    gst_users = await get_all_gst_users()
    gst_would_send = []
    for user in gst_users:
        reminders_sent = user.get("reminders_sent") or {}
        deadlines = get_upcoming_deadlines(user, law_key="GST", limit=5)
        for d in deadlines:
            days = d["days_until"]
            if days < 0 or days > 7:
                continue
            due_str = d["due_date"].isoformat()
            key = f"gst_{d['filing_name']}_{due_str}"
            if key not in reminders_sent:
                gst_would_send.append({
                    "phone": user["phone_number"],
                    "filing": d["filing_name"],
                    "due_date": due_str,
                    "days_until": days,
                })

    overdue = await get_all_overdue_invoices()
    by_user: dict[str, list] = {}
    for inv in overdue:
        by_user.setdefault(inv["phone_number"], []).append(inv)

    inv_would_send = []
    for phone, invoices in by_user.items():
        from database import get_or_create_user
        user = await get_or_create_user(phone)
        reminders_sent = user.get("reminders_sent") or {}
        new_inv = [inv for inv in invoices if f"inv_{inv['id']}" not in reminders_sent]
        if new_inv:
            inv_would_send.append({
                "phone": phone,
                "invoice_count": len(new_inv),
                "total_overdue": sum(float(i["amount"]) for i in new_inv),
            })

    return {
        "gst_reminders": {"would_send": len(gst_would_send), "details": gst_would_send},
        "invoice_reminders": {"would_send": len(inv_would_send), "details": inv_would_send},
        "scheduler_running": True,
    }


@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


_PROFILE_FIELDS = ("business_type", "state", "turnover_bracket", "gst_status", "language")


async def _background_memory_tasks(from_number: str, user_text: str) -> None:
    """Runs after every reply: profile extraction, proactive messages, fact extraction, summary check."""
    await asyncio.gather(
        _profile_and_proactive(from_number, user_text),
        _extract_and_save_facts(from_number, user_text),
        _maybe_summarize(from_number),
    )


async def _profile_and_proactive(from_number: str, user_text: str) -> None:
    """Runs after reply is sent — extracts profile and fires proactive messages."""
    user_before = await get_or_create_user(from_number)

    # Skip extraction if core profile is already complete — saves a Groq call
    if all(user_before.get(f) for f in _PROFILE_FIELDS):
        return

    extracted = await extract_and_update_profile(from_number, user_text)

    if extracted.get("gst_status") and not user_before.get("gst_status"):
        if extracted["gst_status"] == "registered":
            # Fetch updated user so calendar uses latest state/turnover/qrmp data
            user_after = await get_or_create_user(from_number)
            await send_whatsapp_message(from_number, format_gst_calendar_message(user_after))
            bracket = user_before.get("turnover_bracket") or extracted.get("turnover_bracket", "")
            if bracket in ("under_40L", "40L_to_1.5Cr", ""):
                await send_whatsapp_message(
                    from_number,
                    "Ek aur cheez — aap monthly GST filing karte hain ya QRMP quarterly scheme mein hain?\n\n"
                    "QRMP optional hai — zyada tar log monthly file karte hain by default. "
                    "Batao toh main aapki exact deadlines set kar sakta hoon."
                )
        elif extracted["gst_status"] == "not_registered":
            await send_whatsapp_message(from_number, _udyam_guidance_msg())


@app.post("/webhook")
async def receive_message(request: Request):
    data = await request.json()

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return {"status": "ok"}

        message = value["messages"][0]
        from_number = message["from"]
        msg_type = message["type"]

        # ── Image (invoice photo) ─────────────────────────────────────────
        if msg_type == "image":
            image_id = message["image"]["id"]
            whatsapp_token = os.getenv("WHATSAPP_TOKEN")
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    media_resp = await client.get(
                        f"https://graph.facebook.com/v19.0/{image_id}",
                        headers={"Authorization": f"Bearer {whatsapp_token}"}
                    )
                    media_resp.raise_for_status()
                    image_url = media_resp.json()["url"]
            except Exception:
                reply = (
                    "Photo download nahi ho payi — "
                    "thodi der baad dobara try karo, ya invoice details type karke bhejo."
                )
                await send_whatsapp_message(from_number, reply)
                await save_message(from_number, "assistant", reply)
                return {"status": "ok", "reply": reply}

            reply = await handle_invoice_image(from_number, image_url)
            await send_whatsapp_message(from_number, reply)
            await save_message(from_number, "assistant", reply)
            return {"status": "ok", "reply": reply}

        # ── PDF (invoice document) ────────────────────────────────────────
        elif msg_type == "document":
            doc = message["document"]
            mime = doc.get("mime_type", "")
            if mime != "application/pdf":
                reply = "Abhi sirf PDF invoices support hain. Image ya PDF bhejo."
                await send_whatsapp_message(from_number, reply)
                return {"status": "ok", "reply": reply}

            doc_id = doc["id"]
            whatsapp_token = os.getenv("WHATSAPP_TOKEN")
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    media_resp = await client.get(
                        f"https://graph.facebook.com/v19.0/{doc_id}",
                        headers={"Authorization": f"Bearer {whatsapp_token}"}
                    )
                    media_resp.raise_for_status()
                    pdf_url = media_resp.json()["url"]
            except Exception:
                reply = (
                    "PDF download nahi ho payi — "
                    "thodi der baad dobara try karo, ya invoice details type karke bhejo."
                )
                await send_whatsapp_message(from_number, reply)
                await save_message(from_number, "assistant", reply)
                return {"status": "ok", "reply": reply}

            parsed = await parse_invoice_from_pdf_url(pdf_url, whatsapp_token)

            if "error" in parsed:
                reply = (
                    "Yeh invoice nahi lag raha, ya PDF mein text readable nahi hai. "
                    "Details type kar do: vendor name, amount, aur date."
                )
            else:
                vendor_name = parsed.get("vendor_name")
                amount = parsed.get("amount")
                invoice_date = parsed.get("invoice_date")

                if not all([vendor_name, amount, invoice_date]):
                    missing = [f for f, v in [("vendor name", vendor_name), ("amount", amount), ("date", invoice_date)] if not v]
                    reply = f"PDF mein {', '.join(missing)} clearly nahi mila. Please type kar do."
                else:
                    _pending_invoice_confirmations[from_number] = parsed
                    reply = _format_confirmation_prompt(parsed)

            await send_whatsapp_message(from_number, reply)
            await save_message(from_number, "assistant", reply)
            return {"status": "ok", "reply": reply}

        # ── Text message ──────────────────────────────────────────────────
        elif msg_type == "text":
            user_text = message["text"]["body"]
            normalized = user_text.strip().lower()

            # ── First-time onboarding ────────────────────────────────────
            history = await get_conversation_history(from_number, limit=1)
            if not history:
                await get_or_create_user(from_number)
                reply = (
                    "KarSathi mein aapka swagat hai!\n\n"
                    "Main aapka personal CA hoon — GST filing, MSME compliance, "
                    "invoice tracking, vendor payment risk — sab ek jagah.\n\n"
                    "Pehle bata do — Hindi mein comfortable ho ya English mein?"
                )
                await send_whatsapp_message(from_number, reply)
                await save_message(from_number, "assistant", reply)
                return {"status": "ok", "reply": reply}

            # ── Invoice parse confirmation ───────────────────────────────
            if from_number in _pending_invoice_confirmations:
                parsed = _pending_invoice_confirmations.pop(from_number)
                if normalized in ("haan", "yes", "ha", "han", "हाँ", "हां"):
                    reply = await _save_confirmed_invoice(from_number, parsed)
                else:
                    reply = "Theek hai, invoice save nahi ki. Sahi details ke saath dobara bhejo."

            # ── Delete account flow ──────────────────────────────────────
            elif from_number in _pending_deletions:
                stage = _pending_deletions[from_number]

                if stage == "awaiting_feedback":
                    _deletion_feedback[from_number] = user_text.strip()
                    _pending_deletions[from_number] = "awaiting_confirm"
                    reply = (
                        "Shukriya batane ke liye.\n\n"
                        "Ek baar confirm karo — *CONFIRM* likho toh tumhara poora data "
                        "permanently delete ho jayega. Yeh action undo nahi ho sakta."
                    )

                elif stage == "awaiting_confirm":
                    if normalized == "confirm":
                        feedback_text = _deletion_feedback.pop(from_number, "")
                        _pending_deletions.pop(from_number)
                        await save_feedback(from_number, feedback_text)
                        await delete_user_data(from_number)
                        _memory_fallback.pop(from_number, None)
                        _pending_confirmations.pop(from_number, None)
                        reply = (
                            "Done. Tumhara account aur saara data delete ho gaya.\n"
                            "KarSathi use karne ke liye shukriya. Kabhi bhi wapas aa sakte ho."
                        )
                    else:
                        _pending_deletions.pop(from_number)
                        _deletion_feedback.pop(from_number, None)
                        reply = "Theek hai, delete cancel kar diya. Koi aur sawaal?"
                else:
                    _pending_deletions.pop(from_number, None)
                    reply = await get_groq_response(from_number, user_text)

            # ── Pending payment confirmation ─────────────────────────────
            elif from_number in _pending_confirmations:
                pending_inv = _pending_confirmations.pop(from_number)
                if normalized in ("haan", "yes", "ha", "han", "हाँ", "हां"):
                    await mark_invoice_paid(pending_inv["id"])
                    reply = (
                        f"{pending_inv['vendor_name']} "
                        f"Rs.{float(pending_inv['amount']):,.2f} — paid!\n"
                        f"45-day risk cleared."
                    )
                else:
                    reply = "Theek hai, payment record nahi ki. Koi aur sawaal?"

            else:
                if _is_greeting(user_text):
                    reply = handle_greeting()
                    await send_whatsapp_message(from_number, reply)
                    return {"status": "ok", "reply": reply}

                intent = _fast_classify(user_text) or await classify_intent(user_text)

                if intent == "greeting":
                    reply = handle_greeting()
                elif intent == "date_query":
                    now = datetime.now(ZoneInfo("Asia/Kolkata"))
                    _days_hi = ["Somvar", "Mangalvar", "Budhvar", "Guruvar", "Shukravar", "Shanivar", "Ravivar"]
                    reply = f"Aaj {now.strftime('%d %B %Y')} hai — {_days_hi[now.weekday()]}."
                elif intent == "sms_payment":
                    reply = await handle_sms_payment(from_number, user_text)
                elif intent == "gst_compliance":
                    reply = await handle_gst_compliance(from_number, user_text)
                elif intent == "form_i":
                    reply = await handle_form_i_assessment(from_number)
                elif intent == "vendor_list":
                    reply = await handle_vendor_list(from_number, user_text)
                elif intent == "msme_status_update":
                    reply = await handle_msme_status_update(from_number, user_text)
                elif intent == "paperwork_guidance":
                    reply = await handle_paperwork_guidance(from_number, user_text)
                elif intent == "general_compliance":
                    reply = await handle_general_compliance(from_number, user_text)
                elif intent == "delete_account":
                    _pending_deletions[from_number] = "awaiting_feedback"
                    reply = (
                        "Samajh gaye. Account delete karne se pehle ek sawal — "
                        "kyun delete karna chahte ho? Koi bhi reason likh do, "
                        "isse hume improve karne mein help milegi."
                    )
                else:
                    reply = await get_groq_response(from_number, user_text)

            await send_whatsapp_message(from_number, reply)
            asyncio.create_task(_background_memory_tasks(from_number, user_text))
            return {"status": "ok", "reply": reply}

    except Exception as e:
        print(f"[Webhook] ERROR: {e}")
        return {"status": "error", "detail": str(e)}

    return {"status": "ok"}


@app.get("/user/{wa_id}")
async def get_user_profile(wa_id: str):
    user = await get_or_create_user(wa_id)
    return user


@app.get("/conversation/{wa_id}")
async def get_conversation_history_endpoint(wa_id: str):
    messages = await get_conversation_history(wa_id, limit=50)
    user = await get_or_create_user(wa_id)
    return {"wa_id": wa_id, "profile": user, "messages": messages}


@app.delete("/conversation/{wa_id}")
async def reset_conversation(wa_id: str):
    db = get_client()
    if db:
        try:
            db.table("conversations").delete().eq("phone_number", wa_id).execute()
        except Exception as e:
            print(f"[DB] reset error: {e}")
    if wa_id in _memory_fallback:
        del _memory_fallback[wa_id]
    return {"status": "reset", "wa_id": wa_id}


class TestChatRequest(BaseModel):
    wa_id: str
    text: str


@app.post("/test/chat")
async def test_chat(req: TestChatRequest):
    """
    Test endpoint — runs full message logic and returns reply directly.
    Skips WhatsApp delivery so tests work without valid WA credentials.
    Only for local/dev use; never expose in production.
    """
    from_number = req.wa_id
    user_text = req.text
    normalized = user_text.strip().lower()

    try:
        history = await get_conversation_history(from_number, limit=1)

        # First-time onboarding
        if not history:
            await get_or_create_user(from_number)
            reply = (
                "KarSathi mein aapka swagat hai!\n\n"
                "Main aapka personal CA hoon — GST filing, MSME compliance, "
                "invoice tracking, vendor payment risk — sab ek jagah.\n\n"
                "Pehle bata do — Hindi mein comfortable ho ya English mein?"
            )
            await save_message(from_number, "assistant", reply)
            asyncio.create_task(_background_memory_tasks(from_number, user_text))
            return {"reply": reply}

        # Invoice parse confirmation
        if from_number in _pending_invoice_confirmations:
            parsed = _pending_invoice_confirmations.pop(from_number)
            if normalized in ("haan", "yes", "ha", "han", "\u0939\u093e\u0901", "\u0939\u093e\u0902"):
                reply = await _save_confirmed_invoice(from_number, parsed)
            else:
                reply = "Theek hai, invoice save nahi ki. Sahi details ke saath dobara bhejo."

        # Delete account flow
        elif from_number in _pending_deletions:
            stage = _pending_deletions[from_number]
            if stage == "awaiting_feedback":
                _deletion_feedback[from_number] = user_text.strip()
                _pending_deletions[from_number] = "awaiting_confirm"
                reply = (
                    "Shukriya batane ke liye.\n\n"
                    "Ek baar confirm karo — *CONFIRM* likho toh tumhara poora data "
                    "permanently delete ho jayega. Yeh action undo nahi ho sakta."
                )
            elif stage == "awaiting_confirm":
                if normalized == "confirm":
                    feedback_text = _deletion_feedback.pop(from_number, "")
                    _pending_deletions.pop(from_number)
                    await save_feedback(from_number, feedback_text)
                    await delete_user_data(from_number)
                    _memory_fallback.pop(from_number, None)
                    reply = (
                        "Done. Tumhara account aur saara data delete ho gaya.\n"
                        "KarSathi use karne ke liye shukriya. Kabhi bhi wapas aa sakte ho."
                    )
                else:
                    _pending_deletions.pop(from_number)
                    reply = "Theek hai, delete cancel kar diya. Koi aur sawaal?"
            else:
                _pending_deletions.pop(from_number, None)
                reply = await get_groq_response(from_number, user_text)

        # Pending payment confirmation
        elif from_number in _pending_confirmations:
            pending_inv = _pending_confirmations.pop(from_number)
            if normalized in ("haan", "yes", "ha", "han", "\u0939\u093e\u0901", "\u0939\u093e\u0902"):
                await mark_invoice_paid(pending_inv["id"])
                reply = (
                    f"{pending_inv['vendor_name']} "
                    f"Rs.{float(pending_inv['amount']):,.2f} — paid!\n"
                    f"45-day risk cleared."
                )
            else:
                reply = "Theek hai, payment record nahi ki. Koi aur sawaal?"

        else:
            if _is_greeting(user_text):
                reply = handle_greeting()
            else:
                intent = _fast_classify(user_text) or await classify_intent(user_text)

                if intent == "greeting":
                    reply = handle_greeting()
                elif intent == "date_query":
                    now = datetime.now(ZoneInfo("Asia/Kolkata"))
                    _days_hi = ["Somvar", "Mangalvar", "Budhvar", "Guruvar", "Shukravar", "Shanivar", "Ravivar"]
                    reply = f"Aaj {now.strftime('%d %B %Y')} hai — {_days_hi[now.weekday()]}."
                elif intent == "sms_payment":
                    reply = await handle_sms_payment(from_number, user_text)
                elif intent == "gst_compliance":
                    reply = await handle_gst_compliance(from_number, user_text)
                elif intent == "form_i":
                    reply = await handle_form_i_assessment(from_number)
                elif intent == "vendor_list":
                    reply = await handle_vendor_list(from_number, user_text)
                elif intent == "msme_status_update":
                    reply = await handle_msme_status_update(from_number, user_text)
                elif intent == "paperwork_guidance":
                    reply = await handle_paperwork_guidance(from_number, user_text)
                elif intent == "general_compliance":
                    reply = await handle_general_compliance(from_number, user_text)
                elif intent == "delete_account":
                    _pending_deletions[from_number] = "awaiting_feedback"
                    reply = (
                        "Samajh gaye. Account delete karne se pehle ek sawal — "
                        "kyun delete karna chahte ho? Koi bhi reason likh do, "
                        "isse hume improve karne mein help milegi."
                    )
                else:
                    reply = await get_groq_response(from_number, user_text)

        asyncio.create_task(_background_memory_tasks(from_number, user_text))
        return {"reply": reply}

    except Exception as e:
        return {"error": str(e)}


@app.get("/invoices/{wa_id}")
async def get_invoices_endpoint(wa_id: str):
    invoices = await get_all_invoices(wa_id)
    return {"wa_id": wa_id, "count": len(invoices), "invoices": invoices}


@app.get("/vendors/{wa_id}")
async def get_vendors_endpoint(wa_id: str):
    vendors = await get_vendors(wa_id)
    return {"wa_id": wa_id, "count": len(vendors), "vendors": vendors}


@app.get("/form1-assessment/{wa_id}")
async def form1_assessment(wa_id: str):
    from datetime import date
    user = await get_or_create_user(wa_id)
    tax_slab = user.get("tax_slab", "unknown")
    open_invoices = await get_open_invoices(wa_id)

    db = get_client()
    overdue = []
    if db:
        try:
            result = db.table("invoices").select("*").eq("phone_number", wa_id).eq("status", "overdue").execute()
            overdue = result.data or []
        except Exception:
            pass

    all_at_risk = open_invoices + overdue
    enriched = []
    total_overdue_amount = 0.0
    total_penalty = 0.0
    total_tax_min = 0.0
    total_tax_max = 0.0
    at_risk_count = 0

    for inv in all_at_risk:
        risk = calculate_risk(inv, tax_slab)
        enriched.append({**inv, **risk})
        if risk["is_overdue"] or risk["is_at_risk"]:
            total_overdue_amount += float(inv["amount"])
            total_penalty += float(risk["penalty_interest"])
            total_tax_min += float(risk["tax_loss_min"])
            total_tax_max += float(risk["tax_loss_max"])
            at_risk_count += 1

    return {
        "summary": {
            "total_overdue_amount": round(float(total_overdue_amount), 2),
            "total_penalty_interest": round(float(total_penalty), 2),
            "total_43bh_tax_loss_min": round(float(total_tax_min), 2),
            "total_43bh_tax_loss_max": round(float(total_tax_max), 2),
            "invoices_at_risk": at_risk_count,
        },
        "invoices": enriched,
    }
