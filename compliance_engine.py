"""
compliance_engine.py — KarSathi
Queries kg_compliance_calendar from Supabase and computes upcoming deadlines.
Personalised per user profile (turnover, taxpayer type, state).
Falls back to hardcoded GST deadlines if DB is unavailable.
"""

from calendar import monthrange
from datetime import date, datetime
from zoneinfo import ZoneInfo
from database import get_client


def _today_ist() -> date:
    """Always use IST date — servers run in UTC, _today_ist() would be wrong."""
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()

# ── Threshold helper ────────────────────────────────────────────────────────────
# Reads from kg_thresholds table so Budget/GST Council changes only need a DB update.
# Falls back to hardcoded safe defaults if DB is unavailable.

_THRESHOLD_FALLBACK: dict[str, float] = {
    "GST_REG_GOODS":          4_000_000,
    "GST_REG_SERVICES":       2_000_000,
    "GST_COMPOSITION_MAX":   15_000_000,
    "TDS_SALARY_NEW_REGIME":    700_000,
    "TDS_SALARY_OLD_REGIME":    250_000,
    "ADVANCE_TAX_MIN":           10_000,
    "ITR_AUDIT_BUSINESS":    10_000_000,
    "ITR_AUDIT_PROFESSION":   5_000_000,
    "PF_EMPLOYEE_COUNT":             20,
    "ESI_EMPLOYEE_COUNT":            10,
    "ESI_WAGE_CEILING":          21_000,
}


def get_threshold(key: str) -> float:
    """Returns threshold value from kg_thresholds (DB) with hardcoded fallback."""
    db = get_client()
    if db:
        try:
            result = db.table("kg_thresholds").select("value_inr").eq("threshold_key", key).single().execute()
            if result.data:
                return float(result.data["value_inr"])
        except Exception:
            pass
    return _THRESHOLD_FALLBACK.get(key, 0.0)


# ── State categories for GSTR-3B due date personalisation ─────────────────────
# Category 2 states: GSTR-3B due 24th (for 1.5Cr–5Cr turnover bracket)
# Category 1 states (all others): GSTR-3B due 22nd
#
# INTENTIONALLY HARDCODED — GST state categories were fixed at rollout (July 2017)
# and have not changed since. Moving to DB would add latency with zero flexibility gain.
# Source: CBIC Notification No. 35/2020-Central Tax, Annexure-II
# If CBIC ever revises categories, update this set and _CATEGORY_2_STATES below.
_CATEGORY_2_STATES = {
    "himachal pradesh", "uttarakhand", "punjab", "rajasthan", "uttar pradesh",
    "haryana", "delhi", "jammu & kashmir", "jammu and kashmir", "ladakh",
    "dadra & nagar haveli", "dadra and nagar haveli", "daman & diu", "daman and diu",
    "chandigarh", "lakshadweep", "puducherry", "pondicherry",
    "andaman & nicobar", "andaman and nicobar",
}


def _is_cat2_state(state: str) -> bool:
    return state.lower().strip() in _CATEGORY_2_STATES


# ── Taxpayer type resolution ───────────────────────────────────────────────────

def _get_taxpayer_types(user: dict) -> list[str]:
    """
    Returns eligible taxpayer_type values for filtering kg_compliance_calendar.

    Priority:
    1. qrmp_opted (explicit user answer) — most precise
    2. turnover_bracket — used as fallback when qrmp_opted is unknown
    3. Unknown everything — show all types, let Groq ask
    """
    gst_status = user.get("gst_status", "")
    qrmp_opted = user.get("qrmp_opted")   # True / False / None (not yet asked)
    bracket    = user.get("turnover_bracket", "")

    if gst_status == "not_registered":
        return []

    # Explicit QRMP answer — most precise, ignore bracket
    if qrmp_opted is True:
        return ["qrmp", "all"]
    if qrmp_opted is False:
        return ["regular", "all"]

    # qrmp_opted unknown — fall back to turnover bracket
    if bracket == "above_1.5Cr":
        # Turnover > ₹5Cr cannot use QRMP — must be monthly
        return ["regular", "all"]
    elif bracket in ("40L_to_1.5Cr", "under_40L"):
        # QRMP eligible but not confirmed — show both, Groq will ask
        return ["regular", "qrmp", "composition", "all"]
    else:
        # No profile at all — show everything
        return ["regular", "qrmp", "composition", "all"]


# ── Date calculators ───────────────────────────────────────────────────────────

def _next_monthly(due_day: int) -> date:
    """Returns the next occurrence of due_day (this month if not passed, else next month)."""
    today = _today_ist()
    max_day_this_month = monthrange(today.year, today.month)[1]
    actual_day = min(due_day, max_day_this_month)
    candidate = today.replace(day=actual_day)

    if candidate >= today:
        return candidate

    # Move to next month
    if today.month == 12:
        year, month = today.year + 1, 1
    else:
        year, month = today.year, today.month + 1
    max_day_next = monthrange(year, month)[1]
    return date(year, month, min(due_day, max_day_next))


def _next_annual(due_day: int, due_month: int) -> date:
    """Returns the next occurrence of due_day/due_month (this year or next).
    Clamps due_day to the actual max days in the target month for both paths.
    """
    today = _today_ist()

    max_this = monthrange(today.year, due_month)[1]
    candidate = date(today.year, due_month, min(due_day, max_this))

    if candidate >= today:
        return candidate

    next_year = today.year + 1
    max_next = monthrange(next_year, due_month)[1]
    return date(next_year, due_month, min(due_day, max_next))


def _next_quarterly(due_day: int, quarter_offset_month: int) -> date:
    """
    Quarters end: Mar(3), Jun(6), Sep(9), Dec(12).
    Due date = quarter_end_month + offset months, on due_day.
    E.g. offset=1, due_day=13 → Jul 13, Oct 13, Jan 13, Apr 13.
    """
    today = _today_ist()
    candidates = []

    for qe_month in [3, 6, 9, 12]:
        raw_month = qe_month + quarter_offset_month
        year = today.year
        if raw_month > 12:
            raw_month -= 12
            year += 1
        try:
            d = date(year, raw_month, due_day)
            candidates.append(d)
            # Also add previous year to catch very recent past dates
            prev = date(year - 1, raw_month, due_day)
            candidates.append(prev)
        except ValueError:
            pass

    future = sorted(d for d in candidates if d >= today)
    return future[0] if future else sorted(candidates)[-1]


def _next_half_yearly(due_day: int, due_month: int) -> date:
    """Half-yearly filings: two fixed dates per year (e.g. Apr 30, Oct 31)."""
    today = _today_ist()
    # The two due months are: due_month, and due_month + 6
    second_month = due_month + 6 if due_month + 6 <= 12 else due_month - 6
    candidates = []
    for m in [due_month, second_month]:
        for yr in [today.year, today.year + 1]:
            try:
                candidates.append(date(yr, m, due_day))
            except ValueError:
                last = monthrange(yr, m)[1]
                candidates.append(date(yr, m, last))
    future = sorted(d for d in candidates if d >= today)
    return future[0] if future else sorted(candidates)[-1]


def _compute_due_date(row: dict) -> date | None:
    freq = row.get("frequency")
    due_day = row.get("due_day")
    due_month = row.get("due_month")
    quarter_offset = row.get("quarter_offset_month")

    if not due_day:
        return None

    if freq == "monthly":
        return _next_monthly(due_day)
    elif freq == "annual" and due_month:
        return _next_annual(due_day, due_month)
    elif freq == "quarterly" and quarter_offset:
        return _next_quarterly(due_day, quarter_offset)
    elif freq == "half_yearly" and due_month:
        return _next_half_yearly(due_day, due_month)
    return None


# ── Fallback hardcoded deadlines (used when DB is unavailable) ─────────────────
# INTENTIONALLY HARDCODED — this is the offline safety net when Supabase is down.
# Dates here are structural (always 11th, 20th, 31 Dec) not calendar-year-specific,
# so they stay correct year-over-year without updates.
# Exception: if GST Council changes filing dates (e.g. post-COVID extensions),
# update the due_day values below manually.

def _hardcoded_gst_deadlines() -> list[dict]:
    """Minimal set of GST deadlines when kg_compliance_calendar is unavailable."""
    today = _today_ist()
    return [
        {
            "filing_name": "GSTR-1 (Monthly)",
            "filing_name_hi": "GSTR-1 (मासिक)",
            "due_date": _next_monthly(11),
            "days_until": (_next_monthly(11) - today).days,
            "penalty_per_day": 50,
            "portal_url": "https://www.gst.gov.in",
        },
        {
            "filing_name": "GSTR-3B (Monthly)",
            "filing_name_hi": "GSTR-3B (मासिक)",
            "due_date": _next_monthly(20),
            "days_until": (_next_monthly(20) - today).days,
            "penalty_per_day": 50,
            "portal_url": "https://www.gst.gov.in",
        },
        {
            "filing_name": "GSTR-9 (Annual Return)",
            "filing_name_hi": "GSTR-9 (वार्षिक रिटर्न)",
            "due_date": _next_annual(31, 12),
            "days_until": (_next_annual(31, 12) - today).days,
            "penalty_per_day": 200,
            "notes_hi": "Maximum penalty ₹10,000 tak limited hai",
            "portal_url": "https://www.gst.gov.in",
        },
    ]


# ── Main query function ────────────────────────────────────────────────────────

def get_upcoming_deadlines(user: dict, law_key: str = "GST", limit: int = 5) -> list[dict]:
    """
    Returns upcoming compliance deadlines for a user, sorted by due date.
    Queries kg_compliance_calendar; falls back to hardcoded if DB is down.

    Each item: {filing_name, filing_name_hi, due_date (date), days_until (int),
                penalty_per_day, portal_url}
    """
    taxpayer_types = _get_taxpayer_types(user)

    if law_key == "GST" and not taxpayer_types:
        return []  # User is not GST registered

    db = get_client()
    if not db:
        return _hardcoded_gst_deadlines()[:limit] if law_key == "GST" else []

    try:
        result = (
            db.table("kg_compliance_calendar")
            .select("*")
            .eq("law_key", law_key)
            .execute()
        )
        rows = result.data or []
    except Exception:
        return _hardcoded_gst_deadlines()[:limit] if law_key == "GST" else []

    if not rows:
        return _hardcoded_gst_deadlines()[:limit] if law_key == "GST" else []

    today = _today_ist()
    deadlines = []

    user_state = (user.get("state") or "").strip()

    for row in rows:
        # Filter by taxpayer type
        row_type = row.get("taxpayer_type", "all")
        if taxpayer_types and row_type not in taxpayer_types:
            continue

        # State-based filter for GSTR-3B Cat 1 / Cat 2 variants
        fname = row.get("filing_name", "")
        if "Cat 1 States" in fname or "Cat 2 States" in fname:
            if not user_state:
                # State unknown: skip state-specific rows entirely to avoid showing wrong date
                continue
            is_cat2 = _is_cat2_state(user_state)
            if "Cat 2 States" in fname and not is_cat2:
                continue  # User is in Cat 1 state — skip Cat 2 row
            if "Cat 1 States" in fname and is_cat2:
                continue  # User is in Cat 2 state — skip Cat 1 row

        due_date = _compute_due_date(row)
        if due_date is None:
            continue

        days_until = (due_date - today).days

        # Annual/half-yearly filings: always include so Groq has context regardless of date
        # Monthly/quarterly: only show within 60 days to avoid noise
        freq = row.get("frequency")
        if freq not in ("annual", "half_yearly") and days_until > 60:
            continue

        deadlines.append({
            "filing_name": row["filing_name"],
            "filing_name_hi": row.get("filing_name_hi") or row["filing_name"],
            "due_date": due_date,
            "days_until": days_until,
            "penalty_per_day": row.get("penalty_per_day_inr"),
            "portal_url": row.get("portal_url", "https://www.gst.gov.in"),
            "notes_hi": row.get("notes_hi"),
        })

    # If a state-specific GSTR-3B row is present, drop the generic (20th) row
    # so Groq never sees both and picks the wrong one
    has_state_specific_gstr3b = any(
        "GSTR-3B" in d["filing_name"] and ("Cat 1" in d["filing_name"] or "Cat 2" in d["filing_name"])
        for d in deadlines
    )
    if has_state_specific_gstr3b:
        deadlines = [
            d for d in deadlines
            if not (d["filing_name"] == "GSTR-3B (Monthly)")
        ]

    # Sort by due date, deduplicate by filing_name (keep earliest)
    seen = set()
    unique = []
    for d in sorted(deadlines, key=lambda x: x["due_date"]):
        key = d["filing_name"]
        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique[:limit]


# ── Day 6: Compliance Q&A Engine ──────────────────────────────────────────────

_LAW_KEYWORDS: dict[str, list[str]] = {
    "GST": [
        "gst", "gstin", "gstr", "input tax credit", "itc", "composition scheme",
        "cgst", "sgst", "igst", "e-way bill", "reverse charge", "gst registration",
        "gst rate", "gst kya", "gst kyun", "gst kab", "gst kaise",
    ],
    "INCOME_TAX": [
        "income tax", "itr", "income tax return", "advance tax", "section 44",
        "tax audit", "it return", "form 16", "it department",
    ],
    "FSSAI": [
        "fssai", "food licence", "food license", "food safety", "food registration",
        "food business", "restaurant", "bakery", "catering", "khana", "food act",
    ],
    "MSMED": [
        "msme", "msmed", "form i", "form-i", "45 day", "45 din", "45 dino",
        "micro enterprise", "small enterprise", "medium enterprise",
        "vendor payment", "supplier payment", "udyam",
    ],
    "SS_CODE": [
        "pf", "epf", "provident fund", "esi", "employee state insurance",
        "labour law", "labor law", "karmchari", "employee benefit",
    ],
    "SHOPS_ACT": [
        "shops act", "shop registration", "trade licence", "trade license",
        "establishment registration", "dukaan register", "commercial establishment",
    ],
    "LEGAL_METROLOGY": [
        "legal metrology", "weights and measures", "weight measurement", "packaged commodity",
        "packaged commodities", "pre-packaged", "mrp label", "net weight label",
        "tola", "legal metrology act", "verification stamp", "weighing machine",
        "measuring instrument", "legalmet", "wam act",
    ],
    "DPDP": [
        "dpdp", "data protection", "personal data", "data privacy", "privacy law",
        "digital personal data", "data fiduciary", "consent manager", "data breach",
        "data localisation", "pdp bill", "data principal", "data processor",
        "privacy policy", "user data protection",
    ],
    "FACTORIES_ACT": [
        "factories act", "factory registration", "factory licence", "factory license",
        "factory act", "manufacturing unit", "factory inspector", "factory compliance",
        "occupier", "hazardous process", "factory workers", "factory safety",
        "boiler", "annual return factory", "factory renewal", "factory ka licence",
        "manufacturing licence", "udyog licence", "factory registration kaise",
    ],
    "IEC": [
        "iec", "import export code", "import export", "export karna", "import karna",
        "dgft", "export licence", "export license", "import licence", "shipping overseas",
        "foreign trade", "customs code", "export registration", "niryat", "aayat",
        "iec kaise", "iec lena", "iec banwana", "export business",
    ],
}


def detect_laws(text: str) -> list[str]:
    """Returns up to 3 law keys matched by keyword in user's text."""
    text_lower = text.lower()
    detected = []
    for law_key, keywords in _LAW_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            detected.append(law_key)
    return detected[:3]


def query_kg_for_laws(law_keys: list[str]) -> str:
    """
    Queries kg_penalties + kg_compliance_actions for the detected law keys.
    Returns a compact Hindi context string (max ~500 tokens) for Groq injection.
    """
    if not law_keys:
        return ""
    db = get_client()
    if not db:
        return ""

    parts = []

    for law_key in law_keys:
        section = []

        # Penalties for this law
        try:
            result = (
                db.table("kg_penalties")
                .select("description_hi,penalty_type,penalty_amount_inr,penalty_percentage,penalty_min_inr,penalty_max_inr,notes_hi")
                .eq("law_key", law_key)
                .execute()
            )
            rows = result.data or []
            if rows:
                pen_lines = []
                for p in rows[:3]:
                    line = p.get("description_hi") or ""
                    if p.get("penalty_amount_inr"):
                        line += f" — ₹{int(p['penalty_amount_inr'])}"
                    if p.get("penalty_percentage"):
                        line += f" — {p['penalty_percentage']}%"
                    if p.get("penalty_min_inr") and p.get("penalty_max_inr"):
                        line += f" (₹{int(p['penalty_min_inr'])}–₹{int(p['penalty_max_inr'])})"
                    if p.get("notes_hi"):
                        line += f". {p['notes_hi']}"
                    if line.strip():
                        pen_lines.append(f"• {line}")
                if pen_lines:
                    section.append("Penalties:\n" + "\n".join(pen_lines))
        except Exception:
            pass

        # How-to actions for this law
        try:
            result = (
                db.table("kg_compliance_actions")
                .select("action_title_hi,steps_hi,fee_inr,portal_url,documents_hi,processing_days")
                .eq("law_key", law_key)
                .execute()
            )
            rows = result.data or []
            for action in rows[:2]:
                action_lines = []
                title = action.get("action_title_hi") or action.get("law_key", "")
                action_lines.append(f"Action: {title}")
                fee = action.get("fee_inr")
                if fee is not None:
                    action_lines.append(f"Fee: {'Free' if fee == 0 else f'₹{int(fee)}'}")
                if action.get("portal_url"):
                    action_lines.append(f"Portal: {action['portal_url']}")
                if action.get("steps_hi"):
                    steps = action["steps_hi"][:500]
                    action_lines.append(f"Steps: {steps}")
                section.append("\n".join(action_lines))
        except Exception:
            pass

        if section:
            parts.append(f"[{law_key}]\n" + "\n\n".join(section))

    return "\n\n---\n\n".join(parts)


def query_kg_actions_only(law_keys: list[str]) -> str:
    """
    Queries ONLY kg_compliance_actions for the detected law keys.
    Used for "how to register / kaise karte hain" queries — no penalties injected.
    Returns compact Hindi how-to context (max ~400 tokens) for Groq injection.
    """
    if not law_keys:
        return ""
    db = get_client()
    if not db:
        return ""

    parts = []
    for law_key in law_keys:
        try:
            result = (
                db.table("kg_compliance_actions")
                .select("action_title_hi,steps_hi,fee_inr,portal_url,documents_hi,processing_days,notes_hi")
                .eq("law_key", law_key)
                .execute()
            )
            rows = result.data or []
            for action in rows[:2]:
                lines = []
                title = action.get("action_title_hi") or law_key
                lines.append(f"[{law_key}] {title}")
                fee = action.get("fee_inr")
                if fee is not None:
                    lines.append(f"Fee: {'Free' if fee == 0 else f'Rs.{int(fee)}'}")
                if action.get("portal_url"):
                    lines.append(f"Portal: {action['portal_url']}")
                if action.get("processing_days"):
                    lines.append(f"Time: {action['processing_days']} din")
                if action.get("documents_hi"):
                    lines.append(f"Documents: {action['documents_hi'][:200]}")
                if action.get("steps_hi"):
                    lines.append(f"Steps: {action['steps_hi'][:400]}")
                if action.get("notes_hi"):
                    lines.append(f"Note: {action['notes_hi'][:150]}")
                parts.append("\n".join(lines))
        except Exception:
            pass

    return "\n\n---\n\n".join(parts)


# ── Response formatters ────────────────────────────────────────────────────────

def format_gst_calendar_message(user: dict) -> str:
    """
    Returns a Hindi WhatsApp message with upcoming GST deadlines for the user.
    """
    gst_status = user.get("gst_status", "")

    if gst_status == "not_registered":
        return (
            "Aap abhi GST registered nahi ho, isliye koi filing deadline nahi hai.\n\n"
            "Agar aapka turnover ₹20 lakh (services) ya ₹40 lakh (goods) se zyada ho jaaye "
            "toh GST registration mandatory ho jaati hai — ₹10,000 se ₹1 lakh tak penalty lag sakti hai.\n\n"
            "Kya aap Udyam ya GST registration ke baare mein jaanna chahte ho?"
        )

    deadlines = get_upcoming_deadlines(user, law_key="GST", limit=5)

    if not deadlines:
        return (
            "Agle 60 dinon mein koi GST deadline nahi hai. Aap safe zone mein ho.\n\n"
            "Yaad rakhna:\n"
            "• GSTR-1: Har mahine ki 11 tarikh\n"
            "• GSTR-3B: Har mahine ki 20 tarikh\n"
            "• GSTR-9 (Annual): 31 December\n\n"
            "Koi specific filing ke baare mein jaanna chahte ho?"
        )

    lines = ["*Aapke Upcoming GST Deadlines*\n"]

    for d in deadlines:
        days = d["days_until"]
        name_hi = d["filing_name_hi"]
        due_str = d["due_date"].strftime("%d %b %Y")
        penalty = d.get("penalty_per_day")

        if days == 0:
            urgency = "⚠️ *AAJ KI LAST DATE!*"
        elif days <= 3:
            urgency = f"🔴 *Sirf {days} din baaki — abhi karo!*"
        elif days <= 7:
            urgency = f"🟡 {days} din baaki — is hafte file karo"
        else:
            urgency = f"🟢 {days} din baaki"

        lines.append(f"📋 *{name_hi}*")
        lines.append(f"   {due_str} — {urgency}")
        if penalty:
            lines.append(f"   Late fee: ₹{int(penalty)}/din")
        lines.append("")

    lines.append("Portal: gst.gov.in")
    lines.append("\nKisi bhi deadline ke liye step-by-step guide chahiye toh batao.")

    return "\n".join(lines)


def format_next_single_deadline(filing_name_keyword: str, user: dict) -> str | None:
    """
    Returns a focused message about one specific filing (e.g. 'GSTR-3B').
    Returns None if not found.
    """
    deadlines = get_upcoming_deadlines(user, law_key="GST", limit=10)
    keyword = filing_name_keyword.upper()
    match = next(
        (d for d in deadlines if keyword in d["filing_name"].upper()),
        None
    )
    if not match:
        return None

    days = match["days_until"]
    due_str = match["due_date"].strftime("%d %b %Y")
    name_hi = match["filing_name_hi"]
    penalty = match.get("penalty_per_day")

    if days == 0:
        timing = "Aaj ki last date hai — abhi file karo!"
    elif days < 0:
        timing = f"{abs(days)} din late ho gaye ho — jitna jaldi ho sake file karo."
    elif days <= 7:
        timing = f"Sirf {days} din baaki hain — is hafte zaroor file karo."
    else:
        timing = f"{days} din baaki hain."

    msg = f"*{name_hi}*\nDue date: {due_str}\n{timing}"
    if penalty:
        msg += f"\nLate fee: ₹{int(penalty)}/din, max ₹5,000."
    msg += "\nPortal: gst.gov.in"
    return msg
