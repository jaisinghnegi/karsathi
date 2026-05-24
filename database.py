import os
from datetime import date, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

_client: Client | None = None


def get_client() -> Client | None:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if url and key:
            try:
                _client = create_client(url, key)
            except Exception as e:
                print(f"[DB] Failed to connect to Supabase: {e}")
    return _client


async def get_or_create_user(phone_number: str) -> dict:
    db = get_client()
    if not db:
        return {"phone_number": phone_number}
    try:
        result = db.table("users").select("*").eq("phone_number", phone_number).execute()
        if result.data:
            return result.data[0]
        new_user = {"phone_number": phone_number}
        insert_result = db.table("users").insert(new_user).execute()
        return insert_result.data[0] if insert_result.data else new_user
    except Exception as e:
        print(f"[DB] get_or_create_user error: {e}")
        return {"phone_number": phone_number}


async def save_message(phone_number: str, role: str, message: str) -> None:
    db = get_client()
    if not db:
        return
    try:
        db.table("conversations").insert({
            "phone_number": phone_number,
            "role": role,
            "message": message,
        }).execute()
    except Exception as e:
        print(f"[DB] save_message error: {e}")


async def get_conversation_history(phone_number: str, limit: int = 20) -> list[dict]:
    db = get_client()
    if not db:
        return []
    try:
        result = (
            db.table("conversations")
            .select("role, message")
            .eq("phone_number", phone_number)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return [{"role": row["role"], "content": row["message"]} for row in result.data]
    except Exception as e:
        print(f"[DB] get_conversation_history error: {e}")
        return []


async def update_user_profile(phone_number: str, field: str, value: str) -> None:
    allowed_fields = {"language", "business_type", "state", "city", "turnover_bracket"}
    if field not in allowed_fields:
        return
    db = get_client()
    if not db:
        return
    try:
        db.table("users").update({field: value}).eq("phone_number", phone_number).execute()
        print(f"[DB] Profile updated: {phone_number} -> {field}={value}")
    except Exception as e:
        print(f"[DB] update_user_profile error: {e}")


# ─────────────────────────────────────────────
# Vendor functions
# ─────────────────────────────────────────────

async def get_vendor(phone_number: str, vendor_name: str) -> dict | None:
    db = get_client()
    if not db:
        return None
    try:
        result = (
            db.table("vendors")
            .select("*")
            .eq("phone_number", phone_number)
            .ilike("vendor_name", f"%{vendor_name}%")
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[DB] get_vendor error: {e}")
        return None


async def create_vendor(phone_number: str, vendor_name: str) -> dict:
    db = get_client()
    if not db:
        return {}
    try:
        new_vendor = {
            "phone_number": phone_number,
            "vendor_name": vendor_name,
        }
        result = db.table("vendors").insert(new_vendor).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        print(f"[DB] create_vendor error: {e}")
        return {}


async def update_vendor(phone_number: str, vendor_name: str, fields: dict) -> None:
    db = get_client()
    if not db:
        return
    try:
        db.table("vendors").update(fields).eq("phone_number", phone_number).ilike(
            "vendor_name", f"%{vendor_name}%"
        ).execute()
        print(f"[DB] Vendor updated: {phone_number} -> {vendor_name} fields={list(fields.keys())}")
    except Exception as e:
        print(f"[DB] update_vendor error: {e}")


async def get_vendors(phone_number: str) -> list[dict]:
    db = get_client()
    if not db:
        return []
    try:
        result = (
            db.table("vendors")
            .select("*")
            .eq("phone_number", phone_number)
            .execute()
        )
        return result.data if result.data else []
    except Exception as e:
        print(f"[DB] get_vendors error: {e}")
        return []


# ─────────────────────────────────────────────
# Invoice functions
# ─────────────────────────────────────────────

async def create_invoice(
    phone_number: str,
    vendor_name: str,
    amount: float,
    invoice_date,  # accepts str "YYYY-MM-DD" or date object
    payment_deadline_days: int = 45,
) -> dict:
    db = get_client()
    if not db:
        return {}
    try:
        if isinstance(invoice_date, str):
            invoice_date = date.fromisoformat(invoice_date)
        due_date = invoice_date + timedelta(days=payment_deadline_days)
        new_invoice = {
            "phone_number": phone_number,
            "vendor_name": vendor_name,
            "amount": amount,
            "invoice_date": invoice_date.isoformat(),
            "payment_deadline_days": payment_deadline_days,
            "due_date": due_date.isoformat(),
        }
        result = db.table("invoices").insert(new_invoice).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        print(f"[DB] create_invoice error: {e}")
        return {}


async def get_open_invoices(phone_number: str) -> list[dict]:
    db = get_client()
    if not db:
        return []
    try:
        result = (
            db.table("invoices")
            .select("*")
            .eq("phone_number", phone_number)
            .eq("status", "open")
            .order("due_date", desc=False)
            .execute()
        )
        return result.data if result.data else []
    except Exception as e:
        print(f"[DB] get_open_invoices error: {e}")
        return []


async def get_all_invoices(phone_number: str) -> list[dict]:
    db = get_client()
    if not db:
        return []
    try:
        result = (
            db.table("invoices")
            .select("*")
            .eq("phone_number", phone_number)
            .order("invoice_date", desc=True)
            .execute()
        )
        return result.data if result.data else []
    except Exception as e:
        print(f"[DB] get_all_invoices error: {e}")
        return []


async def mark_invoice_paid(invoice_id: str) -> None:
    db = get_client()
    if not db:
        return
    try:
        db.table("invoices").update({"status": "paid"}).eq("id", invoice_id).execute()
        print(f"[DB] Invoice marked paid: {invoice_id}")
    except Exception as e:
        print(f"[DB] mark_invoice_paid error: {e}")
