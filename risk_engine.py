"""
risk_engine.py — KarSathi
45-day MSMED Act deadline calculator.

Computes:
- Days remaining / overdue on an invoice
- Penalty interest under MSMED Act Section 16 (3x RBI rate)
- Section 43B(h) tax deductibility loss

All monetary outputs are rounded to 2 decimal places.
"""

from datetime import date, datetime

# MSMED Act Section 16: compound interest at 3x RBI bank rate (~8.5%)
PENALTY_RATE_PER_ANNUM = 0.255  # 3 × 8.5%

TAX_SLABS = {
    "30%": 0.30,
    "25%": 0.25,
    "22%": 0.22,
    "unknown": None,
}

# Fallback range when tax slab is unknown
_TAX_MIN_RATE = 0.22
_TAX_MAX_RATE = 0.30

# "At risk" threshold: less than or equal to 10 days remaining
AT_RISK_THRESHOLD_DAYS = 10


def _parse_due_date(due_date) -> date:
    """Accepts str 'YYYY-MM-DD' or a date/datetime object."""
    if isinstance(due_date, datetime):
        return due_date.date()
    if isinstance(due_date, date):
        return due_date
    return date.fromisoformat(str(due_date))


def calculate_risk(invoice: dict, tax_slab: str = "unknown") -> dict:
    """
    Calculates compliance risk metrics for a single open invoice.

    Parameters
    ----------
    invoice  : dict with at least 'due_date' (str YYYY-MM-DD or date)
               and 'amount' (numeric)
    tax_slab : one of '30%', '25%', '22%', 'unknown'

    Returns
    -------
    {
        'days_remaining'  : int,    # negative if overdue
        'days_overdue'    : int,    # 0 if not yet overdue
        'penalty_interest': float,  # 0.0 if not overdue
        'tax_loss_min'    : float,
        'tax_loss_max'    : float,
        'is_overdue'      : bool,
        'is_at_risk'      : bool,   # True if days_remaining <= 10
    }
    """
    due_date = _parse_due_date(invoice["due_date"])
    amount = float(invoice["amount"])
    today = date.today()

    days_remaining = (due_date - today).days
    days_overdue = max(0, -days_remaining)
    is_overdue = days_overdue > 0
    is_at_risk = days_remaining <= AT_RISK_THRESHOLD_DAYS

    # Penalty interest accrues only after the due date
    if is_overdue:
        penalty_interest = amount * PENALTY_RATE_PER_ANNUM * (days_overdue / 365)
    else:
        penalty_interest = 0.0

    # Tax loss under Section 43B(h): the entire invoice amount becomes
    # non-deductible if unpaid past the due date, costing the business
    # the tax it would have saved on that expense.
    slab_rate = TAX_SLABS.get(tax_slab)
    if slab_rate is not None:
        tax_loss_min = amount * slab_rate
        tax_loss_max = amount * slab_rate
    else:
        tax_loss_min = amount * _TAX_MIN_RATE
        tax_loss_max = amount * _TAX_MAX_RATE

    return {
        "days_remaining": days_remaining,
        "days_overdue": days_overdue,
        "penalty_interest": round(penalty_interest, 2),
        "tax_loss_min": round(tax_loss_min, 2),
        "tax_loss_max": round(tax_loss_max, 2),
        "is_overdue": is_overdue,
        "is_at_risk": is_at_risk,
    }


def format_risk_message(
    vendor_name: str,
    amount: float,
    invoice_date: str,
    risk: dict,
) -> str:
    """
    Returns a detailed, educational WhatsApp-ready Hinglish message
    explaining the invoice risk, the laws involved, and what action to take.
    """
    from datetime import date as _date
    try:
        display_date = _date.fromisoformat(invoice_date).strftime("%d %b %Y")
    except Exception:
        display_date = invoice_date

    lines = []

    # ── Header ──────────────────────────────────────────────────────────
    lines.append(f"✅ *Invoice Save Ho Gayi*")
    lines.append(f"🏢 Supplier: {vendor_name}")
    lines.append(f"💰 Amount: ₹{amount:,.2f}")
    lines.append(f"📅 Invoice Date: {display_date}")
    lines.append("")

    # ── MSMED Act status ─────────────────────────────────────────────────
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    if risk["is_overdue"]:
        lines.append(f"⚠️ *MSMED Act Status — {risk['days_overdue']} Din Overdue!*")
        lines.append("")
        lines.append(
            "MSMED Act (2006) kehta hai ki agar aapka supplier MSME registered hai, "
            "toh aapko invoice date se 45 din ke andar payment karni hogi. "
            f"Yeh invoice {risk['days_overdue']} din se overdue hai — "
            "yani aap technically law ke against hain agar yeh supplier MSME registered hai."
        )
    elif risk["is_at_risk"]:
        lines.append(f"🔔 *MSMED Act Status — Sirf {risk['days_remaining']} Din Baaki!*")
        lines.append("")
        lines.append(
            "MSMED Act ke under, MSME suppliers ko 45 din ke andar payment karni hoti hai. "
            f"Aapke paas sirf {risk['days_remaining']} din baaki hain. "
            "Abhi payment karo — deadline miss hone par penalty aur tax loss dono honge."
        )
    else:
        lines.append(f"📅 *MSMED Act Status — {risk['days_remaining']} Din Baaki*")
        lines.append("")
        lines.append(
            "MSMED Act ke under, MSME suppliers ko 45 din ke andar payment karni hoti hai. "
            f"Abhi {risk['days_remaining']} din baaki hain — aap safe zone mein ho. "
            "Lekin payment plan karke chalo taki deadline miss na ho."
        )

    lines.append("")

    # ── Penalty interest ─────────────────────────────────────────────────
    if risk["is_overdue"]:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("💸 *Penalty Interest (Section 16, MSMED Act)*")
        lines.append("")
        lines.append(
            "MSMED Act Section 16 ke under, overdue payment par 3 guna RBI bank rate "
            "ka compound interest lagta hai — jo abhi *25.5% per annum* hai. "
            f"Yeh interest invoice ki due date se shuru hota hai aur roz badhta rehta hai."
        )
        lines.append("")
        lines.append(
            f"Abhi tak ban chuki penalty: *₹{risk['penalty_interest']:,.2f}*"
        )
        lines.append(
            "Agar aaj bhi payment nahi ki toh yeh amount aur badhegi — "
            "aur supplier court mein claim kar sakta hai."
        )
        lines.append("")

    # ── 43B(h) tax risk ──────────────────────────────────────────────────
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("📌 *Section 43B(h) — Aapka Tax Khatre Mein Hai*")
    lines.append("")
    lines.append(
        "Income Tax Act ka Section 43B(h) kehta hai ki agar aapne MSME supplier ko "
        "45 din ke andar payment nahi ki, toh yeh poora invoice amount aapki "
        "*taxable income se deductible nahi hoga* us financial year mein."
    )
    lines.append("")
    tax_min = risk["tax_loss_min"]
    tax_max = risk["tax_loss_max"]
    if tax_min == tax_max:
        lines.append(
            f"Matlab: ₹{amount:,.2f} ka kharcha expense nahi maana jaayega, "
            f"aur aapko *₹{tax_min:,.2f} zyada tax* bharna padega."
        )
    else:
        lines.append(
            f"Matlab: ₹{amount:,.2f} ka kharcha expense nahi maana jaayega, "
            f"aur aapko *₹{tax_min:,.2f} se ₹{tax_max:,.2f} zyada tax* bharna padega "
            "(exact amount aapke tax slab par depend karta hai)."
        )

    lines.append("")

    # ── Recommended action ───────────────────────────────────────────────
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("🎯 *Abhi Kya Karein?*")
    lines.append("")
    if risk["is_overdue"]:
        lines.append(
            "Jitna jaldi ho sake payment karo. Agar cash flow tight hai, "
            "supplier se partial payment ya written settlement karo aur record rakho. "
            "Agar aaj payment ki toh penalty aur tax risk dono stop ho jaayenge."
        )
    elif risk["is_at_risk"]:
        lines.append(
            f"Sirf {risk['days_remaining']} din hain — is hafte mein payment plan karo. "
            "Deadline miss hone se pehle action lo."
        )
    else:
        lines.append(
            "Abhi safe ho, lekin payment schedule mein rakho taki bhool na jao. "
            "KarSathi aapko deadline se 10 din pehle remind karega."
        )

    return "\n".join(lines)
