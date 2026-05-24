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
    Returns a WhatsApp-ready Hinglish message summarising the invoice risk.
    Kept under 6 lines so it's scannable on mobile.

    Parameters
    ----------
    vendor_name  : str
    amount       : float  (raw rupee amount)
    invoice_date : str    (display string, e.g. '15 Mar 2026')
    risk         : dict   (output of calculate_risk)
    """
    lines = []

    # Line 1: confirmation header
    lines.append(f"{vendor_name} ₹{amount:,.0f} — {invoice_date} ka invoice save ho gaya ✅")

    # Line 2: overdue / at-risk / safe status
    if risk["is_overdue"]:
        lines.append(
            f"⚠️ {risk['days_overdue']} din overdue! "
            f"Penalty interest abhi tak: ₹{risk['penalty_interest']:,.2f}"
        )
    elif risk["is_at_risk"]:
        lines.append(f"🔔 Sirf {risk['days_remaining']} din baaki hain! Jaldi payment karo.")
    else:
        lines.append(f"📅 {risk['days_remaining']} din baaki hain payment ke liye.")

    # Line 3: 43B(h) tax deductibility risk
    tax_min = risk["tax_loss_min"]
    tax_max = risk["tax_loss_max"]
    if tax_min == tax_max:
        lines.append(
            f"📌 43B(h): Agar payment miss hui toh ₹{tax_min:,.0f} ka tax deduction jaayega."
        )
    else:
        lines.append(
            f"📌 43B(h): Payment miss hui toh ₹{tax_min:,.0f}–₹{tax_max:,.0f} ka "
            f"tax deduction jaayega (slab ke hisaab se)."
        )

    return "\n".join(lines)
