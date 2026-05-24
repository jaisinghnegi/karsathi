import os
import json
import httpx
from fastapi import FastAPI, Request, Query, HTTPException
from dotenv import load_dotenv
from invoice_parser import parse_invoice_from_url
from pdf_parser import parse_invoice_from_pdf_url
from sms_parser import parse_sms
from match_engine import match_payment_to_invoice
from risk_engine import calculate_risk, format_risk_message
from database import (
    get_or_create_user, save_message, get_conversation_history,
    update_user_profile, get_client,
    get_vendor, create_vendor, update_vendor,
    create_invoice, get_open_invoices, mark_invoice_paid, get_all_invoices,
    get_vendors, save_feedback, delete_user_data
)

load_dotenv()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """You are KarSathi — a senior CA with 15 years of experience, now a trusted advisor to small Indian business owners.

You are not a chatbot. You are the CA friend they never had — someone who tells them the truth directly,
flags risks before they become problems, and always has a specific answer, never a vague one.

Your tone:
- Confident and direct, like a doctor giving a diagnosis — not "you might want to check" but "this is a risk, here's what to do"
- Warm but never fluffy. No filler phrases like "Great question!" or "Sure, I'd be happy to help"
- You speak like a trusted friend who happens to be a CA — frank, specific, caring
- When something is a real risk, say it plainly: "Yeh miss kiya toh ₹X ka penalty lagega"
- When they're doing something right, acknowledge it briefly and move forward

Never show menus or numbered lists. Have a natural flowing conversation.

LANGUAGE RULE — this is the very first thing you do:
When a user says anything for the first time (like "Hi", "Hello", "Haan", "Namaste"), respond warmly and
casually ask which language they're comfortable in — Hindi or English. Make it feel like a friend asking,
not a form. Example: "Arey, swagat hai! Baat karte hain — Hindi mein easy lagta hai ya English mein?"
Once they answer, switch fully to that language for the rest of the conversation and never ask again.
If they reply in Hindi, speak Hindi. If English, speak English. If Hinglish, match their vibe.

After language is set, your first job is to understand their business. Gather these naturally, one at a time:
1. Business type (kirana, restaurant, manufacturer, trader, service provider, etc.)
2. State they operate in
3. Annual turnover (approximate band: under 40L, 40L–1.5Cr, above 1.5Cr)

Once you know their profile, proactively flag the 1-2 biggest compliance risks for their specific situation.
Don't wait for them to ask — a good advisor spots problems before the client does.

You advise on:
- GST registration thresholds, filing deadlines, and ITC risks
- FSSAI license requirements (mandatory for any food business)
- MSMED Act / Form I — vendors must be paid within 45 days, Section 43B(h) means unpaid MSME invoices are not tax-deductible
- Shop & Establishment Act (rules vary by state)
- TDS obligations, advance tax, and other direct tax triggers

Keep responses to 3 sentences max. Lead with the most important point.
Always give rupee amounts when talking about penalties or risks — never be vague about money."""

PROFILE_EXTRACTOR_PROMPT = """You are a data extractor. Given a conversation message, extract any of these fields if clearly stated:
- language: "hindi" or "english" (only if user explicitly chose one)
- business_type: e.g. "kirana", "restaurant", "manufacturer", "trader", "service"
- state: Indian state name in English, e.g. "Rajasthan", "Maharashtra"
- city: city name if mentioned
- turnover_bracket: one of "under_40L", "40L_to_1.5Cr", "above_1.5Cr"

Return ONLY valid JSON with the fields found. If nothing found, return {}.
Never guess. Only extract what is explicitly stated.

Examples:
User: "Hindi mein baat karte hain" → {"language": "hindi"}
User: "Mera kirana store hai Jaipur mein" → {"business_type": "kirana", "city": "Jaipur"}
User: "Rajasthan se hoon" → {"state": "Rajasthan"}
User: "40 lakh se kam turnover hai" → {"turnover_bracket": "under_40L"}
User: "just browsing" → {}"""

INTENT_CLASSIFIER_PROMPT = """Classify this WhatsApp message into exactly one category. Return ONLY the category string, nothing else.

Categories:
- sms_payment: bank SMS, UPI confirmation, payment sent/received message
- invoice_question: question about invoices, payments due, Form I, 43B
- general_compliance: GST, tax, FSSAI, registration, compliance question
- delete_account: user wants to delete account, remove data, stop service, unsubscribe
- other: greeting, general chat, anything else

Message: """


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
        valid = {"sms_payment", "invoice_question", "general_compliance", "delete_account", "other"}
        return intent if intent in valid else "other"
    except Exception as e:
        print(f"[IntentClassifier] error: {e}")
        return "other"


app = FastAPI(title="KarSathi WhatsApp Webhook")

# Fallback in-memory store — used only when Supabase is unreachable
_memory_fallback: dict = {}

# Pending payment confirmations — { wa_id: invoice_dict }
_pending_confirmations: dict = {}

# Delete account flow — { wa_id: "awaiting_feedback" | "awaiting_confirm" }
_pending_deletions: dict = {}
# Stores the feedback text while waiting for CONFIRM — { wa_id: feedback_text }
_deletion_feedback: dict = {}


def _get_fallback(wa_id: str) -> dict:
    if wa_id not in _memory_fallback:
        _memory_fallback[wa_id] = {"messages": [], "profile": {}}
    return _memory_fallback[wa_id]


async def extract_and_update_profile(phone_number: str, user_message: str) -> None:
    """Runs profile extraction silently — never blocks the main reply."""
    try:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": PROFILE_EXTRACTOR_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 100,
            "temperature": 0.0,
        }
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(GROQ_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        raw = data["choices"][0]["message"]["content"].strip()
        extracted = json.loads(raw)
        for field, value in extracted.items():
            if value:
                await update_user_profile(phone_number, field, str(value))
    except Exception as e:
        print(f"[Profile extractor] silently failed: {e}")


async def get_groq_response(wa_id: str, user_message: str) -> str:
    # Ensure user exists in DB
    await get_or_create_user(wa_id)

    # Fetch history from DB — falls back to [] if DB is down
    history = await get_conversation_history(wa_id, limit=20)

    # If DB returned nothing, use in-memory fallback
    if not history:
        fallback = _get_fallback(wa_id)
        fallback["messages"].append({"role": "user", "content": user_message})
        history_for_groq = fallback["messages"][-20:]
    else:
        # Keep fallback in sync for resilience
        fallback = _get_fallback(wa_id)
        fallback["messages"] = history.copy()
        fallback["messages"].append({"role": "user", "content": user_message})
        history_for_groq = history

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}]
                     + history_for_groq
                     + [{"role": "user", "content": user_message}],
        "max_tokens": 300,
        "temperature": 0.7,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GROQ_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    reply = data["choices"][0]["message"]["content"].strip()

    # Persist both turns to DB
    await save_message(wa_id, "user", user_message)
    await save_message(wa_id, "assistant", reply)

    # Extract and save any profile fields mentioned
    await extract_and_update_profile(wa_id, user_message)

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
        response.raise_for_status()
    print(f"[WhatsApp -> {to}]: {message}")


async def handle_invoice_image(from_number: str, image_url: str) -> str:
    whatsapp_token = os.getenv("WHATSAPP_TOKEN")
    parsed = await parse_invoice_from_url(image_url, whatsapp_token)

    if "error" in parsed:
        return "Yeh invoice nahi lag raha, ya photo thodi blur hai. Ek clear photo bhejo ya details type kar do: vendor name, amount, aur date."

    vendor_name = parsed.get("vendor_name")
    amount = parsed.get("amount")
    invoice_date = parsed.get("invoice_date")

    if not all([vendor_name, amount, invoice_date]):
        missing = [f for f, v in [("vendor name", vendor_name), ("amount", amount), ("date", invoice_date)] if not v]
        return f"Invoice mein {', '.join(missing)} clearly nahi dikh raha. Please type kar do."

    user = await get_or_create_user(from_number)
    vendor = await get_vendor(from_number, vendor_name)

    # Determine deadline: default 45 days unless verbal agreement stored
    deadline_days = 15 if (vendor and vendor.get("agreement_type") == "verbal") else 45

    # Save invoice
    await create_invoice(from_number, vendor_name, float(amount), invoice_date, deadline_days)

    # Calculate risk
    from datetime import date, timedelta
    inv_date = date.fromisoformat(invoice_date)
    due_date = inv_date + timedelta(days=deadline_days)
    risk = calculate_risk({"due_date": due_date.isoformat(), "amount": amount}, user.get("tax_slab", "unknown"))
    risk_msg = format_risk_message(vendor_name, float(amount), invoice_date, risk)

    if not vendor:
        # New vendor — create and ask MSME status
        await create_vendor(from_number, vendor_name)
        return (
            f"{risk_msg}\n\n"
            f"Ek sawal: {vendor_name} — kya yeh MSME registered supplier hai?\n"
            f"Haan / Nahi / Pata nahi — reply karo"
        )
    else:
        return risk_msg


async def handle_sms_payment(from_number: str, text: str) -> str:
    parsed = await parse_sms(text)

    if "error" in parsed:
        # Not a payment SMS — fall through to normal conversation
        return await get_groq_response(from_number, text)

    open_invoices = await get_open_invoices(from_number)
    match_type, matched_invoice = await match_payment_to_invoice(parsed, open_invoices)

    vendor = parsed.get("vendor_name", "vendor")
    amount = parsed.get("amount", 0)

    if match_type == "exact":
        await mark_invoice_paid(matched_invoice["id"])
        return (
            f"{matched_invoice['vendor_name']} "
            f"Rs.{int(float(matched_invoice['amount'])):,} — paid!\n"
            f"45-day risk cleared."
        )
    elif match_type == "fuzzy":
        inv = matched_invoice
        _pending_confirmations[from_number] = inv
        return (
            f"Yeh payment {inv['vendor_name']} wale "
            f"Rs.{int(float(inv['amount'])):,} ({inv['invoice_date']}) invoice ke liye hai?\n"
            f"Haan / Nahi"
        )
    else:
        return (
            f"Rs.{int(float(amount)):,} payment record ho gayi, lekin koi matching invoice nahi mila.\n"
            f"Kya iske liye koi invoice aane wala hai? Forward karo jab mile."
        )


@app.get("/health")
async def health():
    db_status = "connected" if get_client() else "fallback (in-memory)"
    return {"status": "KarSathi webhook is running", "db": db_status}


@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def receive_message(request: Request):
    data = await request.json()
    print("Incoming:", data)

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return {"status": "ok"}

        message = value["messages"][0]
        from_number = message["from"]
        msg_type = message["type"]

        if msg_type == "image":
            image_id = message["image"]["id"]
            whatsapp_token = os.getenv("WHATSAPP_TOKEN")
            async with httpx.AsyncClient(timeout=15) as client:
                media_resp = await client.get(
                    f"https://graph.facebook.com/v19.0/{image_id}",
                    headers={"Authorization": f"Bearer {whatsapp_token}"}
                )
                media_resp.raise_for_status()
                image_url = media_resp.json()["url"]

            reply = await handle_invoice_image(from_number, image_url)
            await send_whatsapp_message(from_number, reply)
            await save_message(from_number, "assistant", reply)
            return {"status": "ok", "reply": reply}

        elif msg_type == "document":
            doc = message["document"]
            mime = doc.get("mime_type", "")
            if mime != "application/pdf":
                reply = "Abhi sirf PDF invoices support hain. Image ya PDF bhejo."
                await send_whatsapp_message(from_number, reply)
                return {"status": "ok", "reply": reply}

            doc_id = doc["id"]
            whatsapp_token = os.getenv("WHATSAPP_TOKEN")
            async with httpx.AsyncClient(timeout=15) as client:
                media_resp = await client.get(
                    f"https://graph.facebook.com/v19.0/{doc_id}",
                    headers={"Authorization": f"Bearer {whatsapp_token}"}
                )
                media_resp.raise_for_status()
                pdf_url = media_resp.json()["url"]

            parsed = await parse_invoice_from_pdf_url(pdf_url, whatsapp_token)

            if "error" in parsed:
                reply = "Yeh invoice nahi lag raha, ya PDF mein text readable nahi hai. Details type kar do: vendor name, amount, aur date."
            else:
                vendor_name = parsed.get("vendor_name")
                amount = parsed.get("amount")
                invoice_date = parsed.get("invoice_date")

                if not all([vendor_name, amount, invoice_date]):
                    missing = [f for f, v in [("vendor name", vendor_name), ("amount", amount), ("date", invoice_date)] if not v]
                    reply = f"PDF mein {', '.join(missing)} clearly nahi mila. Please type kar do."
                else:
                    user = await get_or_create_user(from_number)
                    vendor = await get_vendor(from_number, vendor_name)
                    deadline_days = 15 if (vendor and vendor.get("agreement_type") == "verbal") else 45
                    await create_invoice(from_number, vendor_name, float(amount), invoice_date, deadline_days)

                    from datetime import date as _date, timedelta
                    inv_date = _date.fromisoformat(invoice_date)
                    due_date = inv_date + timedelta(days=deadline_days)
                    risk = calculate_risk({"due_date": due_date.isoformat(), "amount": amount}, user.get("tax_slab", "unknown"))
                    risk_msg = format_risk_message(vendor_name, float(amount), invoice_date, risk)

                    if not vendor:
                        await create_vendor(from_number, vendor_name)
                        reply = (
                            f"{risk_msg}\n\n"
                            f"Ek sawal: {vendor_name} — kya yeh MSME registered supplier hai?\n"
                            f"Haan / Nahi / Pata nahi — reply karo"
                        )
                    else:
                        reply = risk_msg

            await send_whatsapp_message(from_number, reply)
            await save_message(from_number, "assistant", reply)
            return {"status": "ok", "reply": reply}

        elif msg_type == "text":
            user_text = message["text"]["body"]
            print(f"Message from {from_number}: {user_text}")

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

            # ── Delete account flow (highest priority) ──────────────────
            if from_number in _pending_deletions:
                stage = _pending_deletions[from_number]

                if stage == "awaiting_feedback":
                    # User just gave their reason — store it, ask to confirm
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
                        # Also clear in-memory state
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
                        f"Rs.{int(float(pending_inv['amount'])):,} — paid!\n"
                        f"45-day risk cleared."
                    )
                else:
                    reply = "Theek hai, payment record nahi ki. Koi aur sawaal?"
            else:
                intent = await classify_intent(user_text)
                print(f"Intent: {intent}")

                if intent == "sms_payment":
                    reply = await handle_sms_payment(from_number, user_text)
                elif intent == "delete_account":
                    _pending_deletions[from_number] = "awaiting_feedback"
                    reply = (
                        "Samajh gaye. Account delete karne se pehle ek sawal — "
                        "kyun delete karna chahte ho? Koi bhi reason likh do, "
                        "isse hume improve karne mein help milegi."
                    )
                else:
                    reply = await get_groq_response(from_number, user_text)

            print(f"Reply: {reply}")
            await send_whatsapp_message(from_number, reply)
            return {"status": "ok", "reply": reply}

    except Exception as e:
        print("Error:", e)
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
