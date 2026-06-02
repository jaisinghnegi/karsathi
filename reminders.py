"""
reminders.py — KarSathi Day 5
Proactive daily reminders at 9AM IST via APScheduler:
- GST deadline warnings (sent once when <= 7 days to due date)
- Invoice overdue alerts (sent once per invoice)
"""

import os
import httpx
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_IST = ZoneInfo("Asia/Kolkata")

from database import (
    get_all_gst_users,
    get_all_overdue_invoices,
    get_or_create_user,
    mark_reminder_sent,
)
from compliance_engine import get_upcoming_deadlines


async def _send_wa(to: str, message: str) -> None:
    phone_number_id = os.getenv("PHONE_NUMBER_ID")
    whatsapp_token = os.getenv("WHATSAPP_TOKEN")
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {whatsapp_token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload, headers=headers)
    except Exception as e:
        print(f"[Reminder] WA send failed for {to}: {e}")


async def send_gst_reminders() -> None:
    """Send GST deadline reminders to all registered users when <= 7 days to due date."""
    users = await get_all_gst_users()
    sent_count = 0

    for user in users:
        phone = user["phone_number"]
        reminders_sent: dict = user.get("reminders_sent") or {}
        deadlines = get_upcoming_deadlines(user, law_key="GST", limit=5)

        for d in deadlines:
            days = d["days_until"]
            if days < 0 or days > 7:
                continue  # Only remind in the 7-day window; past-due handled by invoice reminders

            due_str = d["due_date"].isoformat()
            reminder_key = f"gst_{d['filing_name']}_{due_str}"

            if reminder_key in reminders_sent:
                continue  # Already sent for this specific due date

            name = d["filing_name_hi"] or d["filing_name"]
            penalty = d.get("penalty_per_day")

            if days == 0:
                urgency = "⚠️ *AAJ KI LAST DATE HAI!*"
            elif days == 1:
                urgency = "🔴 *Kal ki last date hai — aaj hi file karo!*"
            else:
                urgency = f"🔴 *Sirf {days} din baaki hain!*"

            msg = (
                f"{urgency}\n\n"
                f"📋 *{name}*\n"
                f"Due date: {d['due_date'].strftime('%d %b %Y')}"
            )
            if penalty:
                msg += f"\nLate fee: ₹{int(penalty)}/din"
            msg += "\n\nAbhi file karo: gst.gov.in"

            await _send_wa(phone, msg)
            await mark_reminder_sent(phone, reminder_key)
            sent_count += 1

    print(f"[Reminder] GST reminders sent: {sent_count}")


async def send_invoice_reminders() -> None:
    """Send one consolidated overdue-invoice alert per user (once per invoice)."""
    overdue = await get_all_overdue_invoices()
    if not overdue:
        print("[Reminder] No overdue invoices.")
        return

    # Group by phone_number
    by_user: dict[str, list] = {}
    for inv in overdue:
        by_user.setdefault(inv["phone_number"], []).append(inv)

    sent_count = 0
    for phone, invoices in by_user.items():
        user = await get_or_create_user(phone)
        reminders_sent: dict = user.get("reminders_sent") or {}

        new_invoices = [
            inv for inv in invoices
            if f"inv_{inv['id']}" not in reminders_sent
        ]
        if not new_invoices:
            continue

        total = sum(float(inv["amount"]) for inv in new_invoices)
        inv_lines = "\n".join(
            f"• {inv['vendor_name']}: ₹{float(inv['amount']):,.0f}"
            for inv in new_invoices[:5]
        )
        more = f"\n...aur {len(new_invoices) - 5} aur" if len(new_invoices) > 5 else ""

        msg = (
            f"⚠️ *Overdue Invoices — Action Required*\n\n"
            f"{inv_lines}{more}\n\n"
            f"Total overdue: ₹{total:,.0f}\n\n"
            f"MSME vendors ko 45 din se zyada late pay kiya toh Section 43B(h) ke under "
            f"yeh amount aapki taxable income se deductible nahi rahega — matlab zyada tax."
        )

        await _send_wa(phone, msg)
        for inv in new_invoices:
            await mark_reminder_sent(phone, f"inv_{inv['id']}")
        sent_count += len(new_invoices)

    print(f"[Reminder] Invoice reminders sent for {sent_count} invoices")


def start_scheduler() -> AsyncIOScheduler:
    """Creates and starts the APScheduler. Call on app startup via lifespan."""
    scheduler = AsyncIOScheduler(timezone=_IST)
    # 9:00 AM IST — GST deadline reminders
    scheduler.add_job(
        send_gst_reminders,
        CronTrigger(hour=9, minute=0),
        id="gst_reminders",
        replace_existing=True,
    )
    # 9:05 AM IST — Invoice overdue reminders
    scheduler.add_job(
        send_invoice_reminders,
        CronTrigger(hour=9, minute=5),
        id="invoice_reminders",
        replace_existing=True,
    )
    scheduler.start()
    print("[Reminder] Scheduler started — GST at 9:00 AM IST, Invoices at 9:05 AM IST")
    return scheduler
