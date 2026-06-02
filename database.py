import os
import random
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


def _generate_user_code(db) -> str:
    """Generate a unique 6-digit user code."""
    for _ in range(10):  # retry up to 10 times on collision
        code = str(random.randint(100000, 999999))
        try:
            result = db.table("users").select("phone_number").eq("user_code", code).execute()
            if not result.data:
                return code
        except Exception:
            return code
    return str(random.randint(100000, 999999))


async def get_or_create_user(phone_number: str) -> dict:
    db = get_client()
    if not db:
        return {"phone_number": phone_number}
    try:
        result = db.table("users").select("*").eq("phone_number", phone_number).execute()
        if result.data:
            return result.data[0]
        user_code = _generate_user_code(db)
        new_user = {"phone_number": phone_number, "user_code": user_code}
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
        # Fetch NEWEST `limit` messages (desc), then reverse to chronological order
        result = (
            db.table("conversations")
            .select("role, message")
            .eq("phone_number", phone_number)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = list(reversed(result.data))
        # Strip any error/fallback messages that leaked into DB before this fix
        _error_prefix = "Abhi thoda technical issue"
        return [
            {"role": row["role"], "content": row["message"]}
            for row in rows
            if row["message"] != _error_prefix and not row["message"].startswith(_error_prefix)
        ]
    except Exception as e:
        print(f"[DB] get_conversation_history error: {e}")
        return []


async def update_user_profile(phone_number: str, field: str, value: str) -> None:
    allowed_fields = {"language", "business_type", "state", "city", "turnover_bracket", "gst_status", "qrmp_opted", "tds_on_salary"}
    if field not in allowed_fields:
        return
    db = get_client()
    if not db:
        return
    try:
        # Boolean columns — cast string to bool before storing
        stored_value: str | bool = value
        if field in ("qrmp_opted", "tds_on_salary"):
            stored_value = value.lower() in ("true", "yes", "haan", "opted", "quarterly", "zyada")
        db.table("users").update({field: stored_value}).eq("phone_number", phone_number).execute()
        print(f"[DB] Profile updated: {phone_number} -> {field}={stored_value}")
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


# ─────────────────────────────────────────────
# Feedback + Account deletion
# ─────────────────────────────────────────────

async def save_feedback(phone_number: str, feedback_text: str) -> None:
    db = get_client()
    if not db:
        return
    try:
        user = await get_or_create_user(phone_number)
        db.table("feedback").insert({
            "phone_number": phone_number,
            "user_code": user.get("user_code"),
            "feedback": feedback_text,
        }).execute()
    except Exception as e:
        print(f"[DB] save_feedback error: {e}")


async def delete_user_data(phone_number: str) -> None:
    """Permanently deletes all data for a user across all tables."""
    db = get_client()
    if not db:
        return
    try:
        db.table("conversations").delete().eq("phone_number", phone_number).execute()
        db.table("invoices").delete().eq("phone_number", phone_number).execute()
        db.table("vendors").delete().eq("phone_number", phone_number).execute()
        db.table("users").delete().eq("phone_number", phone_number).execute()
    except Exception as e:
        print(f"[DB] delete_user_data error: {e}")


# ─────────────────────────────────────────────
# Reminder functions (Day 5)
# ─────────────────────────────────────────────

async def get_all_gst_users() -> list[dict]:
    """Returns all users with gst_status = 'registered' for proactive reminders."""
    db = get_client()
    if not db:
        return []
    try:
        result = (
            db.table("users")
            .select("*")
            .eq("gst_status", "registered")
            .execute()
        )
        return result.data or []
    except Exception as e:
        print(f"[DB] get_all_gst_users error: {e}")
        return []


async def get_all_overdue_invoices() -> list[dict]:
    """Returns all unpaid invoices past their due date across all users."""
    db = get_client()
    if not db:
        return []
    try:
        today = date.today().isoformat()
        result = (
            db.table("invoices")
            .select("*")
            .neq("status", "paid")
            .lt("due_date", today)
            .order("due_date", desc=False)
            .execute()
        )
        return result.data or []
    except Exception as e:
        print(f"[DB] get_all_overdue_invoices error: {e}")
        return []


# ─────────────────────────────────────────────
# Day 8: Vendor MSME tools
# ─────────────────────────────────────────────

async def set_vendor_msme_status(phone_number: str, vendor_name: str, is_msme: bool) -> bool:
    """Marks a vendor as MSME registered or not. Returns True if vendor was found."""
    db = get_client()
    if not db:
        return False
    try:
        result = (
            db.table("vendors")
            .update({"is_msme": is_msme})
            .eq("phone_number", phone_number)
            .ilike("vendor_name", f"%{vendor_name}%")
            .execute()
        )
        return bool(result.data)
    except Exception as e:
        print(f"[DB] set_vendor_msme_status error: {e}")
        return False


async def get_msme_vendors(phone_number: str) -> list[dict]:
    """Returns all vendors marked as MSME registered."""
    db = get_client()
    if not db:
        return []
    try:
        result = (
            db.table("vendors")
            .select("*")
            .eq("phone_number", phone_number)
            .eq("is_msme", True)
            .execute()
        )
        return result.data or []
    except Exception as e:
        print(f"[DB] get_msme_vendors error: {e}")
        return []


async def get_vendor_invoices(phone_number: str, vendor_name: str) -> list[dict]:
    """Returns all open invoices for a specific vendor (partial name match)."""
    db = get_client()
    if not db:
        return []
    try:
        result = (
            db.table("invoices")
            .select("*")
            .eq("phone_number", phone_number)
            .eq("status", "open")
            .ilike("vendor_name", f"%{vendor_name}%")
            .order("due_date", desc=False)
            .execute()
        )
        return result.data or []
    except Exception as e:
        print(f"[DB] get_vendor_invoices error: {e}")
        return []


async def get_overdue_msme_invoices(phone_number: str) -> list[dict]:
    """
    Returns open invoices for MSME vendors that are past their due date.
    Joins vendors (is_msme=True) with invoices (status=open, due_date < today).
    """
    db = get_client()
    if not db:
        return []
    try:
        msme_vendors = await get_msme_vendors(phone_number)
        if not msme_vendors:
            return []
        msme_names = [v["vendor_name"] for v in msme_vendors]
        today = date.today().isoformat()
        overdue = []
        for name in msme_names:
            result = (
                db.table("invoices")
                .select("*")
                .eq("phone_number", phone_number)
                .eq("status", "open")
                .ilike("vendor_name", f"%{name}%")
                .lt("due_date", today)
                .execute()
            )
            overdue.extend(result.data or [])
        return sorted(overdue, key=lambda x: x["due_date"])
    except Exception as e:
        print(f"[DB] get_overdue_msme_invoices error: {e}")
        return []


# ─────────────────────────────────────────────
# User facts memory (Migration 010)
# ─────────────────────────────────────────────

async def get_user_facts(wa_id: str) -> dict:
    """Returns all saved facts for a user as {fact_key: fact_value}."""
    db = get_client()
    if not db:
        return {}
    try:
        result = db.table("user_facts").select("fact_key, fact_value").eq("wa_id", wa_id).execute()
        return {row["fact_key"]: row["fact_value"] for row in (result.data or [])}
    except Exception as e:
        print(f"[DB] get_user_facts error: {e}")
        return {}


async def save_user_fact(wa_id: str, fact_key: str, fact_value: str) -> None:
    """Upserts a single fact. Updates updated_at if the fact already exists."""
    db = get_client()
    if not db:
        return
    try:
        db.table("user_facts").upsert(
            {"wa_id": wa_id, "fact_key": fact_key, "fact_value": fact_value, "updated_at": "now()"},
            on_conflict="wa_id,fact_key",
        ).execute()
    except Exception as e:
        print(f"[DB] save_user_fact error: {e}")


async def delete_user_fact(wa_id: str, fact_key: str) -> None:
    """Deletes a specific fact for a user."""
    db = get_client()
    if not db:
        return
    try:
        db.table("user_facts").delete().eq("wa_id", wa_id).eq("fact_key", fact_key).execute()
    except Exception as e:
        print(f"[DB] delete_user_fact error: {e}")


# ─────────────────────────────────────────────
# Conversation summaries (Migration 011)
# ─────────────────────────────────────────────

async def get_conversation_summary(wa_id: str) -> str:
    """Returns the latest conversation summary for a user, or empty string if none."""
    db = get_client()
    if not db:
        return ""
    try:
        result = db.table("conversation_summaries").select("summary").eq("wa_id", wa_id).execute()
        return result.data[0]["summary"] if result.data else ""
    except Exception as e:
        print(f"[DB] get_conversation_summary error: {e}")
        return ""


async def save_conversation_summary(wa_id: str, summary: str, message_count: int = 0) -> None:
    """Upserts the conversation summary for a user."""
    db = get_client()
    if not db:
        return
    try:
        db.table("conversation_summaries").upsert(
            {
                "wa_id": wa_id,
                "summary": summary,
                "message_count_at_summary": message_count,
                "updated_at": "now()",
            },
            on_conflict="wa_id",
        ).execute()
    except Exception as e:
        print(f"[DB] save_conversation_summary error: {e}")


async def get_conversation_count(wa_id: str) -> int:
    """Returns total number of messages stored for a user."""
    db = get_client()
    if not db:
        return 0
    try:
        result = (
            db.table("conversations")
            .select("id", count="exact")
            .eq("phone_number", wa_id)
            .execute()
        )
        return result.count or 0
    except Exception as e:
        print(f"[DB] get_conversation_count error: {e}")
        return 0


async def mark_reminder_sent(phone_number: str, reminder_key: str) -> None:
    """Records that a reminder was sent so it won't be sent again."""
    db = get_client()
    if not db:
        return
    try:
        row = db.table("users").select("reminders_sent").eq("phone_number", phone_number).execute()
        current: dict = (row.data[0].get("reminders_sent") or {}) if row.data else {}
        current[reminder_key] = date.today().isoformat()
        db.table("users").update({"reminders_sent": current}).eq("phone_number", phone_number).execute()
    except Exception as e:
        print(f"[DB] mark_reminder_sent error: {e}")
