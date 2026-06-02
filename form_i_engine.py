"""
form_i_engine.py — KarSathi Day 8
Form I (MSMED Act) assessment + vendor tools.

Provides:
- assess_form_i()         : Is the user obligated to file Form I this half-year?
- calculate_msme_interest(): Compound interest under MSMED Act Section 16
- format_vendor_summary() : WhatsApp-ready vendor list with MSME + overdue flags
- format_form_i_report()  : Form I obligation report in Hindi
- format_vendor_invoices(): Overdue invoice detail for a specific vendor
"""

from datetime import date, timedelta
from zoneinfo import ZoneInfo


# ─── Constants ────────────────────────────────────────────────────────────────

# MSMED Act Section 16: 3 × RBI Bank Rate
# RBI bank rate is currently 6.5% → 3× = 19.5% p.a. compounded monthly
# risk_engine.py uses 25.5% (3×8.5%) — we use 19.5% as the updated figure.
MSMED_ANNUAL_RATE = 0.195
MSMED_MONTHLY_RATE = MSMED_ANNUAL_RATE / 12


def _today_ist() -> date:
    return date.today()


# ─── Interest calculator ──────────────────────────────────────────────────────

def calculate_msme_interest(principal: float, due_date_str: str) -> dict:
    """
    Calculates compound interest under MSMED Act Section 16.
    Interest accrues from the day AFTER the due date.

    Returns:
        principal, days_overdue, months_overdue, interest_accrued, total_payable
    """
    today = _today_ist()
    due = date.fromisoformat(due_date_str)

    if today <= due:
        return {
            "principal": principal,
            "days_overdue": 0,
            "months_overdue": 0.0,
            "interest_accrued": 0.0,
            "total_payable": principal,
            "is_overdue": False,
        }

    days_overdue = (today - due).days
    months_overdue = days_overdue / 30.44  # average month length

    # Compound interest: P × ((1 + r)^n - 1)
    interest = principal * ((1 + MSMED_MONTHLY_RATE) ** months_overdue - 1)

    return {
        "principal": round(principal, 2),
        "days_overdue": days_overdue,
        "months_overdue": round(months_overdue, 2),
        "interest_accrued": round(interest, 2),
        "total_payable": round(principal + interest, 2),
        "is_overdue": True,
    }


# ─── Form I obligation ────────────────────────────────────────────────────────

def _current_half_year() -> tuple[str, date]:
    """
    Returns (half_year_label, form_i_due_date) for the current period.
    H1 (Apr 1 – Sep 30): due Oct 31
    H2 (Oct 1 – Mar 31): due Apr 30
    """
    today = _today_ist()
    month = today.month
    year = today.year

    if 4 <= month <= 9:  # H1
        label = f"H1 (Apr–Sep {year})"
        due = date(year, 10, 31)
    else:  # H2
        # H2 of previous FY if Jan–Mar, H2 of current FY if Oct–Dec
        if month <= 3:
            label = f"H2 (Oct {year-1}–Mar {year})"
            due = date(year, 4, 30)
        else:
            label = f"H2 (Oct–Mar {year}/{year+1})"
            due = date(year + 1, 4, 30)

    return label, due


def assess_form_i(overdue_msme_invoices: list[dict]) -> dict:
    """
    Determines if the user must file Form I this half-year.

    Returns:
        must_file, half_year_label, due_date, days_until_due,
        overdue_vendors (list of {vendor, amount, days_overdue, interest}),
        total_overdue_amount, total_interest
    """
    half_year, due_date = _current_half_year()
    today = _today_ist()
    days_until_due = (due_date - today).days

    if not overdue_msme_invoices:
        return {
            "must_file": False,
            "half_year": half_year,
            "due_date": due_date,
            "days_until_due": days_until_due,
            "overdue_vendors": [],
            "total_overdue_amount": 0.0,
            "total_interest": 0.0,
        }

    overdue_vendors = []
    total_amount = 0.0
    total_interest = 0.0

    for inv in overdue_msme_invoices:
        calc = calculate_msme_interest(float(inv["amount"]), inv["due_date"])
        overdue_vendors.append({
            "vendor": inv["vendor_name"],
            "invoice_date": inv["invoice_date"],
            "amount": float(inv["amount"]),
            "days_overdue": calc["days_overdue"],
            "interest_accrued": calc["interest_accrued"],
            "total_payable": calc["total_payable"],
        })
        total_amount += float(inv["amount"])
        total_interest += calc["interest_accrued"]

    return {
        "must_file": True,
        "half_year": half_year,
        "due_date": due_date,
        "days_until_due": days_until_due,
        "overdue_vendors": overdue_vendors,
        "total_overdue_amount": round(total_amount, 2),
        "total_interest": round(total_interest, 2),
    }


# ─── WhatsApp formatters ──────────────────────────────────────────────────────

def format_form_i_report(assessment: dict) -> str:
    """Returns a Hindi WhatsApp message about Form I obligation."""
    due_str = assessment["due_date"].strftime("%d %b %Y")
    days = assessment["days_until_due"]

    if not assessment["must_file"]:
        return (
            f"*Form I Assessment — {assessment['half_year']}*\n\n"
            "✅ Aapko abhi Form I file nahi karni — koi overdue MSME invoice nahi hai.\n\n"
            f"Form I ki due date: {due_str} ({days} din baaki)\n"
            "Portal: msme.gov.in/form-i\n\n"
            "Agar koi MSME vendor ka payment delay hua toh mujhe batao — main assess karunga."
        )

    # Urgency level
    if days <= 0:
        urgency = "⛔ *FORM I KI LAST DATE NIKAL GAYI — ABHI FILE KARO!*"
    elif days <= 7:
        urgency = f"🔴 *Sirf {days} din baaki — abhi file karo!*"
    elif days <= 30:
        urgency = f"🟡 {days} din baaki — is mahine zaroor karein"
    else:
        urgency = f"🟢 {days} din baaki"

    lines = [
        f"*MSMD Form I Assessment — {assessment['half_year']}*\n",
        f"📅 Due Date: {due_str} — {urgency}\n",
        f"⚠️ Aapko Form I file karni HOGI kyunki {len(assessment['overdue_vendors'])} "
        f"MSME vendor{'s' if len(assessment['overdue_vendors']) > 1 else ''} "
        f"ka payment 45 din se overdue hai.\n",
    ]

    lines.append("*Overdue MSME Invoices:*")
    for v in assessment["overdue_vendors"]:
        lines.append(
            f"• {v['vendor']}: ₹{v['amount']:,.2f} — "
            f"{v['days_overdue']} din overdue — "
            f"Interest: ₹{v['interest_accrued']:,.2f}"
        )

    lines.append(
        f"\n💰 Total Outstanding: ₹{assessment['total_overdue_amount']:,.2f}"
        f"\n💸 Total Interest (MSMED S.16): ₹{assessment['total_interest']:,.2f}"
        f"\n📊 Total Payable: ₹{assessment['total_overdue_amount'] + assessment['total_interest']:,.2f}"
    )

    lines.append(
        "\n*Form I kaise file karein?*\n"
        "1. msme.gov.in/form-i par jao\n"
        "2. Company PAN se login karo\n"
        "3. Saare overdue MSME vendors aur amount fill karo\n"
        "4. Delay ka reason daalo\n"
        "5. Submit — no fee\n\n"
        "Note: Form I file karna compulsory hai. Na file karne par ₹10,000–₹10,00,000 penalty."
    )

    return "\n".join(lines)


def format_vendor_summary(vendors: list[dict], open_invoices: list[dict]) -> str:
    """
    Returns a WhatsApp-ready vendor list with MSME status and outstanding amounts.
    """
    if not vendors:
        return (
            "Abhi koi vendor save nahi hai.\n\n"
            "Invoice photo ya PDF bhejo — main vendor automatically track karunga.\n"
            "Ya type karo: 'Sharma Traders se ₹50,000 ka invoice mila'"
        )

    today = _today_ist()

    # Build invoice map: vendor_name -> list of open invoices
    inv_map: dict[str, list] = {}
    for inv in open_invoices:
        key = inv["vendor_name"].lower()
        inv_map.setdefault(key, []).append(inv)

    lines = [f"*Aapke Vendors ({len(vendors)})*\n"]

    for v in vendors:
        name = v["vendor_name"]
        is_msme = v.get("is_msme")
        msme_tag = "🏭 MSME" if is_msme is True else ("❓ MSME?" if is_msme is None else "🏢 Non-MSME")

        vendor_invs = inv_map.get(name.lower(), [])
        if vendor_invs:
            total = sum(float(i["amount"]) for i in vendor_invs)
            overdue_invs = [i for i in vendor_invs if date.fromisoformat(i["due_date"]) < today]
            overdue_total = sum(float(i["amount"]) for i in overdue_invs)

            if overdue_invs and is_msme:
                status = f"⚠️ ₹{overdue_total:,.0f} overdue ({len(overdue_invs)} inv)"
            elif overdue_invs:
                status = f"🔴 ₹{overdue_total:,.0f} overdue"
            else:
                oldest_due = min(date.fromisoformat(i["due_date"]) for i in vendor_invs)
                days_left = (oldest_due - today).days
                status = f"₹{total:,.0f} due — {days_left}d left"

            lines.append(f"• *{name}* ({msme_tag}) — {status}")
        else:
            lines.append(f"• *{name}* ({msme_tag}) — no open invoices")

    unconfirmed = [v for v in vendors if v.get("is_msme") is None]
    if unconfirmed:
        lines.append(
            f"\n❓ {len(unconfirmed)} vendor{'s' if len(unconfirmed) > 1 else ''} ka MSME status confirm nahi hai.\n"
            "Reply karo: 'Sharma Traders MSME hai' ya 'Sharma Traders MSME nahi hai'"
        )

    lines.append("\nForm I status ke liye: 'form i check karo'")
    return "\n".join(lines)


def format_vendor_invoices(vendor_name: str, invoices: list[dict], is_msme: bool | None) -> str:
    """Returns overdue invoice detail for a specific vendor."""
    if not invoices:
        return f"{vendor_name} ka koi open invoice nahi hai abhi."

    today = _today_ist()
    msme_tag = "MSME registered" if is_msme else ("MSME status unknown" if is_msme is None else "non-MSME")
    lines = [f"*{vendor_name}* ({msme_tag})\n"]

    total = 0.0
    total_interest = 0.0

    for inv in invoices:
        amount = float(inv["amount"])
        due = date.fromisoformat(inv["due_date"])
        days_left = (due - today).days
        total += amount

        if days_left < 0:
            calc = calculate_msme_interest(amount, inv["due_date"])
            interest_str = f" — Interest: ₹{calc['interest_accrued']:,.2f}" if is_msme else ""
            lines.append(
                f"🔴 ₹{amount:,.2f} — {abs(days_left)} din overdue"
                f" (due: {due.strftime('%d %b')}){interest_str}"
            )
            total_interest += calc["interest_accrued"] if is_msme else 0
        elif days_left <= 7:
            lines.append(f"🟡 ₹{amount:,.2f} — {days_left} din left (due: {due.strftime('%d %b')})")
        else:
            lines.append(f"🟢 ₹{amount:,.2f} — {days_left} din left (due: {due.strftime('%d %b')})")

    lines.append(f"\nTotal outstanding: ₹{total:,.2f}")
    if is_msme and total_interest > 0:
        lines.append(f"Interest accrued (MSMED S.16): ₹{total_interest:,.2f}")
        lines.append(f"Total payable: ₹{total + total_interest:,.2f}")

    return "\n".join(lines)
