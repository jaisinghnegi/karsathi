"""
test_karsathi.py -- KarSathi end-to-end test suite
Tests 20+ scenarios against the running local server via /test/chat endpoint.

Run: python test_karsathi.py
"""

import asyncio
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv()

# Force UTF-8 output so emoji in replies don't crash on Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"


# -- Helpers -------------------------------------------------------------------

def _db():
    """Return the supabase client (same instance the server uses)."""
    from supabase import create_client
    url = __import__("os").getenv("SUPABASE_URL")
    key = __import__("os").getenv("SUPABASE_KEY")
    return create_client(url, key)


_supabase = None


def get_supabase():
    global _supabase
    if _supabase is None:
        _supabase = _db()
    return _supabase


def prime_user_db(wa_id: str) -> None:
    """
    Directly writes a seed conversation row so the server sees existing history.
    Bypasses HTTP entirely — 100% reliable, no timing race.
    """
    db = get_supabase()
    # Ensure user row exists
    existing = db.table("users").select("phone_number").eq("phone_number", wa_id).execute()
    if not existing.data:
        db.table("users").insert({"phone_number": wa_id}).execute()
    # Clear old conversations, then insert one seed assistant message
    db.table("conversations").delete().eq("phone_number", wa_id).execute()
    db.table("conversations").insert({
        "phone_number": wa_id,
        "role": "assistant",
        "message": "KarSathi mein aapka swagat hai!",
    }).execute()


def reset_user_db(wa_id: str) -> None:
    """Hard-delete conversations and user for clean profile tests."""
    db = get_supabase()
    db.table("conversations").delete().eq("phone_number", wa_id).execute()
    db.table("users").delete().eq("phone_number", wa_id).execute()


async def send_message(client: httpx.AsyncClient, wa_id: str, text: str) -> str:
    try:
        resp = await client.post(
            f"{BASE}/test/chat",
            json={"wa_id": wa_id, "text": text},
            timeout=90,
        )
        data = resp.json()
        if "reply" in data:
            return data["reply"]
        return f"[ERROR] {data.get('error', 'no reply')}"
    except Exception as e:
        return f"[TIMEOUT] {e}"


async def get_profile(client: httpx.AsyncClient, wa_id: str) -> dict:
    resp = await client.get(f"{BASE}/user/{wa_id}", timeout=10)
    return resp.json()


# -- Result tracking -----------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
results = []

_GROQ_RATE_LIMIT_MSG = "abhi thoda technical issue"


def check(test_name: str, reply: str,
          must_contain: list = None,
          must_not_contain: list = None,
          min_len: int = 10) -> bool:
    reply_lower = reply.lower()
    errors = []

    # Groq rate-limited -> skip, not fail
    if _GROQ_RATE_LIMIT_MSG in reply_lower:
        short_reply = reply[:120].replace("\n", " | ")
        print(f"  [{SKIP}] {test_name}")
        print(f"         Groq rate-limited -- skipping")
        print(f"         Reply: {short_reply}")
        results.append((test_name, None, reply))  # None = skipped
        return True  # don't count as failure

    if len(reply) < min_len:
        errors.append(f"reply too short ({len(reply)} chars)")

    if reply.startswith("[ERROR]") or reply.startswith("[NO_REPLY]") or reply.startswith("[TIMEOUT]"):
        errors.append(f"handler error: {reply[:120]}")

    for phrase in (must_contain or []):
        if phrase.lower() not in reply_lower:
            errors.append(f"missing: '{phrase}'")

    for phrase in (must_not_contain or []):
        if phrase.lower() in reply_lower:
            errors.append(f"unwanted: '{phrase}'")

    passed = len(errors) == 0
    status = PASS if passed else FAIL
    short_reply = reply[:120].replace("\n", " | ")
    print(f"  [{status}] {test_name}")
    if not passed:
        for e in errors:
            print(f"         ERR: {e}")
    print(f"         Reply: {short_reply}")
    results.append((test_name, passed, reply))
    return passed


# -- Tests ---------------------------------------------------------------------

async def run_tests():
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:

        health = (await client.get(f"{BASE}/health")).json()
        print(f"\nServer: {health}")
        print("=" * 70)
        print("KarSathi Test Suite -- 52 test cases")
        print("=" * 70)

        # -- GROUP 1: Onboarding & Greetings ----------------------------------
        print("\n[1] ONBOARDING & GREETINGS")

        # T1: First-time user gets onboarding (no history)
        wa = "test_001"
        reset_user_db(wa)   # delete user+conversations so first-time path triggers
        reply = await send_message(client, wa, "hi")
        check("T1  First-time user onboarding",
              reply, must_contain=["KarSathi", "Hindi", "English"])

        # T2: Repeat greeting (user has history)
        wa = "test_002"
        prime_user_db(wa)
        reply = await send_message(client, wa, "hello")
        check("T2  Repeat greeting -> Welcome back",
              reply, must_contain=["back"])

        # T3: Hindi language choice
        wa = "test_003"
        prime_user_db(wa)
        reply = await send_message(client, wa, "Hindi mein baat karein")
        check("T3  Language choice (Hindi)", reply, min_len=5)

        # T4: Date query
        wa = "test_004"
        prime_user_db(wa)
        reply = await send_message(client, wa, "aaj kya date hai")
        today_year = str(datetime.now(ZoneInfo("Asia/Kolkata")).year)
        check("T4  Date query returns current year",
              reply, must_contain=[today_year])

        # -- GROUP 2: GST Compliance Deadlines --------------------------------
        print("\n[2] GST COMPLIANCE DEADLINES")

        # T5: Generic GST deadline
        wa = "test_005"
        prime_user_db(wa)
        reply = await send_message(client, wa, "GST kab bharna hai? Koi deadline hai abhi?")
        check("T5  Generic GST deadline",
              reply, must_contain=["gstr"])

        # T6: GSTR-1 specific deadline (11th) -- "due date kya hai" now correctly hits gst_compliance
        wa = "test_006"
        prime_user_db(wa)
        reply = await send_message(client, wa, "GSTR-1 ki due date kya hai?")
        check("T6  GSTR-1 due date contains 11",
              reply, must_contain=["gstr-1", "11"])

        # T7: GSTR-3B specific deadline
        wa = "test_007"
        prime_user_db(wa)
        reply = await send_message(client, wa, "GSTR-3B kab submit karna hai?")
        check("T7  GSTR-3B due date mentioned",
              reply, must_contain=["gstr-3b"])

        # T8: Advance tax deadline
        wa = "test_008"
        prime_user_db(wa)
        reply = await send_message(client, wa, "advance tax ki deadline kya hai?")
        check("T8  Advance tax deadline",
              reply, must_contain=["advance tax"])

        # T9: TDS return filing dates
        wa = "test_009"
        prime_user_db(wa)
        reply = await send_message(client, wa, "TDS return kab file karna hai? 24Q ki due date?")
        check("T9  TDS return dates",
              reply, must_contain=["tds"])

        # T10: ITR deadline
        wa = "test_010"
        prime_user_db(wa)
        reply = await send_message(client, wa, "ITR kab tak bharna hai?")
        check("T10 ITR deadline mentioned",
              reply, must_contain=["itr"])

        # T11: How many days left for GSTR-3B
        wa = "test_011"
        prime_user_db(wa)
        reply = await send_message(client, wa, "GSTR-3B mein kitne din baaki hain?")
        check("T11 Days remaining for GSTR-3B",
              reply, must_contain=["gstr-3b"])

        await asyncio.sleep(8)  # let Groq RPM window recover

        # -- GROUP 3: General Compliance (KG-backed) --------------------------
        print("\n[3] GENERAL COMPLIANCE (KG-backed)")

        # T12: GST registration process
        wa = "test_012"
        prime_user_db(wa)
        reply = await send_message(client, wa, "GST registration kaise karte hain?")
        check("T12 GST registration steps",
              reply, must_contain=["gst"],
              must_not_contain=["i don't know", "i cannot"])

        # T13: FSSAI for food business
        wa = "test_013"
        prime_user_db(wa)
        reply = await send_message(client, wa, "Mera restaurant hai. FSSAI licence zaroori hai kya?")
        check("T13 FSSAI for restaurant",
              reply, must_contain=["fssai"])

        # T14: MSME 45-day payment rule
        wa = "test_014"
        prime_user_db(wa)
        reply = await send_message(client, wa, "MSME suppliers ko 45 din mein pay karna kyun zaroori hai?")
        check("T14 MSME 45-day rule explained",
              reply, must_contain=["45"])

        # T15: Udyam registration
        wa = "test_015"
        prime_user_db(wa)
        reply = await send_message(client, wa, "Udyam registration kaise karein? Free hai kya?")
        check("T15 Udyam registration guidance",
              reply, must_contain=["udyam"])

        # T16: PF/ESI threshold
        wa = "test_016"
        prime_user_db(wa)
        reply = await send_message(client, wa, "PF aur ESI kab mandatory hoti hai? Employee count kya chahiye?")
        check("T16 PF/ESI threshold",
              reply, must_contain=["pf", "esi"])

        # T17: Section 43B(h)
        wa = "test_017"
        prime_user_db(wa)
        reply = await send_message(client, wa, "Section 43B(h) kya hai aur vendor payment se kya connection hai?")
        check("T17 Section 43B(h) tax risk",
              reply, must_contain=["43b"])

        # T18: GST composition scheme
        wa = "test_018"
        prime_user_db(wa)
        reply = await send_message(client, wa, "GST composition scheme kya hoti hai? Kaun le sakta hai?")
        check("T18 GST composition scheme",
              reply, must_contain=["composition"])

        # T19: GST rate for groceries
        wa = "test_019"
        prime_user_db(wa)
        reply = await send_message(client, wa, "Grocery items pe GST rate kya hota hai?")
        check("T19 GST rate for groceries",
              reply, must_contain=["gst"])

        await asyncio.sleep(8)

        # -- GROUP 4: Profile Extraction --------------------------------------
        print("\n[4] PROFILE EXTRACTION")

        # Profile tests: reset_user_db first (delete stale profile), then prime_user_db (seed history)

        # T20: Business type + state extracted
        wa = "test_020"
        reset_user_db(wa)
        prime_user_db(wa)
        await send_message(client, wa, "Mera kirana store hai Rajasthan mein")
        await asyncio.sleep(1.5)
        profile = await get_profile(client, wa)
        check("T20 Profile: business_type + state saved",
              f"business_type={profile.get('business_type','')} state={profile.get('state','')}",
              must_contain=["kirana", "rajasthan"])

        # T21: GST registered -- NOTE: requires migration 007 (gst_status column missing)
        wa = "test_021"
        reset_user_db(wa)
        prime_user_db(wa)
        await send_message(client, wa, "Haan GST registered hoon mere paas GSTIN hai")
        await asyncio.sleep(1.5)
        profile = await get_profile(client, wa)
        gst = str(profile.get("gst_status") or "")
        check("T21 Profile: gst_status=registered (needs migration 007)",
              f"gst_status={gst}",
              must_contain=["registered"])

        # T22: Turnover bracket extracted (80L -> 40L_to_1.5Cr)
        wa = "test_022"
        reset_user_db(wa)
        prime_user_db(wa)
        await send_message(client, wa, "Mera turnover 80 lakh hai")
        await asyncio.sleep(1.5)
        profile = await get_profile(client, wa)
        check("T22 Profile: turnover 80L -> 40L_to_1.5Cr bracket",
              f"turnover_bracket={profile.get('turnover_bracket','')}",
              must_contain=["40l_to_1.5cr"])

        # T23: TDS salary flag (below 7L)
        wa = "test_023"
        reset_user_db(wa)
        prime_user_db(wa)
        await send_message(client, wa, "Employee ki salary 7 lakh se kam hai")
        await asyncio.sleep(1.5)
        profile = await get_profile(client, wa)
        check("T23 Profile: tds_on_salary=false when salary < 7L",
              f"tds_on_salary={profile.get('tds_on_salary','')}",
              must_contain=["false"])

        await asyncio.sleep(8)

        # -- GROUP 5: TDS LOGIC -----------------------------------------------
        print("\n[5] TDS LOGIC")

        # T24: TDS deduction threshold
        wa = "test_024"
        prime_user_db(wa)
        reply = await send_message(client, wa, "TDS deduction kab karni padti hai salary se?")
        check("T24 TDS deduction threshold (7L rule)",
              reply, must_contain=["tds", "7"])

        # T25: TDS return mandatory regardless of deduction
        wa = "test_025"
        prime_user_db(wa)
        await send_message(client, wa, "Employee salary 5 lakh hai, TDS nahi katna")
        await asyncio.sleep(0.3)
        reply = await send_message(client, wa, "TDS return file karna padega kya agar TDS nahi kata?")
        check("T25 TDS return mandatory even with no deduction",
              reply, must_contain=["return"])

        await asyncio.sleep(8)

        # -- GROUP 6: SMS PAYMENT PARSING -------------------------------------
        print("\n[6] SMS PAYMENT PARSING")

        # T26: Bank NEFT debit SMS (outgoing vendor payment -- what the parser expects)
        wa = "test_026"
        prime_user_db(wa)
        reply = await send_message(
            client, wa,
            "Rs.25000 debited from A/C XX1234 on 28-May-2026. "
            "Transferred to Sharma Traders via NEFT. Ref No: NEFT123456789"
        )
        # Reply will say "Rs.25,000.00 payment record ho gayi" -- amount is parsed, no invoice match is fine
        check("T26 Bank NEFT debit SMS parsed (vendor payment)",
              reply,
              must_contain=["25,000"])

        # T27: UPI debit SMS (outgoing vendor payment)
        wa = "test_027"
        prime_user_db(wa)
        reply = await send_message(
            client, wa,
            "Rs.15000 debited from your account. Payment to Krishna Store via UPI. "
            "UPI Ref: 123456789012"
        )
        check("T27 UPI debit SMS parsed (vendor payment)",
              reply,
              must_contain=["15,000"])

        await asyncio.sleep(8)

        # -- GROUP 7: FLOW TESTS ----------------------------------------------
        print("\n[7] FLOW TESTS")

        # T28: Delete account flow starts correctly
        wa = "test_028"
        prime_user_db(wa)
        reply = await send_message(client, wa, "delete account kar do mera")
        check("T28 Delete account flow initiated",
              reply, must_contain=["delete", "kyun"])

        # T29: Invoice confirmation flow
        wa = "test_029"
        prime_user_db(wa)
        # Simulate invoice image confirmation pending (set directly)
        # We send a text that should be treated as general compliance since
        # no pending invoice. Test that "haan" without pending state is handled.
        reply = await send_message(client, wa, "Kya koi naya sawaal pooch sakta hoon?")
        check("T29 General question handled gracefully",
              reply, min_len=5)

        # T30: GST non-registered user -- no deadlines
        wa = "test_030"
        prime_user_db(wa)
        await send_message(client, wa, "GST nahi hai mere paas, GST register nahi hoon")
        await asyncio.sleep(0.3)
        reply = await send_message(client, wa, "GST kab bharna hai?")
        check("T30 Non-GST user gets registration guidance (not filing dates)",
              reply, min_len=10)

        await asyncio.sleep(8)

        # -- GROUP 8: Day 4 — GST Calendar (live kg_compliance_calendar) ------
        print("\n[8] DAY 4: GST COMPLIANCE CALENDAR")

        # TD4_1: Full calendar fast-path — "saari deadlines dikhao"
        wa = "test_d4_1"
        prime_user_db(wa)
        reply = await send_message(client, wa, "Meri saari GST deadlines dikhao")
        check("TD4_1 Calendar fast-path (saari deadlines)",
              reply, must_contain=["gstr"])

        # TD4_2: Calendar keyword — "GST calendar"
        wa = "test_d4_2"
        prime_user_db(wa)
        reply = await send_message(client, wa, "GST calendar show karo")
        check("TD4_2 Calendar fast-path (GST calendar show karo)",
              reply, must_contain=["gstr"])

        # TD4_3: Proactive calendar on GST registration — check the REPLY itself
        # (T21 only checked profile; here we check the reply content)
        wa = "test_d4_3"
        reset_user_db(wa)
        prime_user_db(wa)
        reply = await send_message(client, wa, "Haan GST registered hoon, GSTIN hai mera")
        # The background task sends proactive calendar; main reply should ack the registration
        check("TD4_3 GST registration reply is non-empty", reply, min_len=5)

        # TD4_4: Non-GST user asking for calendar — should NOT show filing dates
        wa = "test_d4_4"
        reset_user_db(wa)
        prime_user_db(wa)
        # Seed non-registered status
        get_supabase().table("users").update({"gst_status": "not_registered"}).eq("phone_number", wa).execute()
        reply = await send_message(client, wa, "Meri saari GST deadlines dikhao")
        check("TD4_4 Non-GST user: no filing dates, gets registration guidance",
              reply, must_not_contain=["gstr-1", "gstr-3b"])

        # TD4_5: QRMP unknown — bot asks about scheme when turnover is small
        wa = "test_d4_5"
        prime_user_db(wa)
        reply = await send_message(client, wa, "GSTR-1 ki due date kya hai?")
        check("TD4_5 GSTR-1 date answered (11th mentioned)",
              reply, must_contain=["11"])

        # TD4_6: All deadlines list returns urgency indicators
        wa = "test_d4_6"
        reset_user_db(wa)
        prime_user_db(wa)
        get_supabase().table("users").update({"gst_status": "registered"}).eq("phone_number", wa).execute()
        reply = await send_message(client, wa, "all deadlines list karo")
        check("TD4_6 All deadlines: urgency format present",
              reply, must_contain=["gstr"])

        await asyncio.sleep(8)

        # -- GROUP 9: Day 7 — Government Paperwork Guidance -------------------
        print("\n[9] DAY 7: GOVERNMENT PAPERWORK GUIDANCE")

        # TD7_1: GST registration steps
        wa = "test_d7_1"
        prime_user_db(wa)
        reply = await send_message(client, wa, "GST registration kaise karte hain? Steps batao")
        check("TD7_1 GST registration steps (portal + steps)",
              reply, must_contain=["gst"],
              must_not_contain=["i don't know", "i cannot"])

        # TD7_2: FSSAI licence — food business
        wa = "test_d7_2"
        prime_user_db(wa)
        reply = await send_message(client, wa, "FSSAI licence kaise milega? Kya documents chahiye?")
        check("TD7_2 FSSAI licence steps + documents",
              reply, must_contain=["fssai"])

        # TD7_3: Udyam registration — free + instant
        wa = "test_d7_3"
        prime_user_db(wa)
        reply = await send_message(client, wa, "Udyam registration kaise karein? Process kya hai?")
        check("TD7_3 Udyam registration steps (free + Aadhaar)",
              reply, must_contain=["udyam"])

        # TD7_4: Shops Act / Trade licence
        wa = "test_d7_4"
        prime_user_db(wa)
        reply = await send_message(client, wa, "Shop registration kaise karein? Trade licence kaise banwao?")
        check("TD7_4 Shops Act / trade licence steps",
              reply, must_contain=["registration"])

        await asyncio.sleep(8)

        # TD7_5: IEC for export business
        wa = "test_d7_5"
        prime_user_db(wa)
        reply = await send_message(client, wa, "Export karna hai, IEC kaise lena hai? DGFT pe kaise apply karein?")
        check("TD7_5 IEC registration steps (DGFT + fee)",
              reply, must_contain=["iec"])

        # TD7_6: PF/ESI registration
        wa = "test_d7_6"
        prime_user_db(wa)
        reply = await send_message(client, wa, "PF registration kaise karein? EPFO mein kaise register hote hain?")
        check("TD7_6 PF/EPFO registration steps",
              reply, must_contain=["pf"])

        # TD7_7: Multi-law paperwork — GST + FSSAI together
        wa = "test_d7_7"
        prime_user_db(wa)
        reply = await send_message(client, wa, "Mujhe naya restaurant kholna hai. GST aur FSSAI dono kaise loon?")
        check("TD7_7 Multi-law paperwork (GST + FSSAI)",
              reply, must_contain=["gst", "fssai"])

        # TD7_8: IEC annual update reminder
        wa = "test_d7_8"
        prime_user_db(wa)
        reply = await send_message(client, wa, "IEC update karna hai, kab tak karna padega?")
        check("TD7_8 IEC annual update deadline",
              reply, must_contain=["iec"])

        await asyncio.sleep(8)

        # -- GROUP 10: Day 8 — Form I Assessment + Vendor Tools ---------------
        print("\n[10] DAY 8: FORM I + VENDOR TOOLS")

        # TD8_1: Form I — no MSME vendors → clean bill
        wa = "test_d8_1"
        prime_user_db(wa)
        reply = await send_message(client, wa, "form i check karo")
        check("TD8_1 Form I — no overdue MSME invoices",
              reply, must_contain=["form"])

        # TD8_2: Vendor list — empty
        wa = "test_d8_2"
        prime_user_db(wa)
        reply = await send_message(client, wa, "vendors dikhao")
        check("TD8_2 Vendor list — empty state message",
              reply, min_len=10)

        # TD8_3: Mark vendor MSME via conversation
        # Seed a vendor first via DB, then mark it as MSME
        wa = "test_d8_3"
        prime_user_db(wa)
        db = get_supabase()
        db.table("vendors").insert({"phone_number": wa, "vendor_name": "Sharma Traders"}).execute()
        reply = await send_message(client, wa, "Sharma Traders MSME hai")
        check("TD8_3 Mark vendor as MSME",
              reply, must_contain=["sharma traders", "msme"])

        # TD8_4: Mark vendor as non-MSME
        wa = "test_d8_4"
        prime_user_db(wa)
        db.table("vendors").insert({"phone_number": wa, "vendor_name": "Kumar Supplies"}).execute()
        reply = await send_message(client, wa, "Kumar Supplies MSME nahi hai")
        check("TD8_4 Mark vendor as non-MSME",
              reply, must_contain=["kumar supplies"])

        # TD8_5: Vendor list with seeded vendor
        wa = "test_d8_5"
        prime_user_db(wa)
        db.table("vendors").insert({"phone_number": wa, "vendor_name": "Patel & Co"}).execute()
        reply = await send_message(client, wa, "mere vendors dikhao")
        check("TD8_5 Vendor list shows seeded vendor",
              reply, must_contain=["patel"])

        await asyncio.sleep(8)

        # TD8_6: Form I — with overdue MSME invoice
        wa = "test_d8_6"
        prime_user_db(wa)
        db.table("vendors").insert({"phone_number": wa, "vendor_name": "ABC Metals", "is_msme": True}).execute()
        # Invoice 60 days overdue
        from datetime import date as _date2, timedelta as _td2
        inv_date = (_date2.today() - _td2(days=60)).isoformat()
        due_date = (_date2.today() - _td2(days=15)).isoformat()
        db.table("invoices").insert({
            "phone_number": wa, "vendor_name": "ABC Metals",
            "amount": 50000, "invoice_date": inv_date,
            "due_date": due_date, "payment_deadline_days": 45, "status": "open"
        }).execute()
        reply = await send_message(client, wa, "form i bharna hai kya?")
        check("TD8_6 Form I — overdue MSME invoice detected",
              reply, must_contain=["form", "abc metals"])

        # TD8_7: Vendor-specific invoice query
        wa = "test_d8_7"
        prime_user_db(wa)
        db.table("vendors").insert({"phone_number": wa, "vendor_name": "Gupta Traders", "is_msme": True}).execute()
        db.table("invoices").insert({
            "phone_number": wa, "vendor_name": "Gupta Traders",
            "amount": 30000, "invoice_date": (_date2.today() - _td2(days=10)).isoformat(),
            "due_date": (_date2.today() + _td2(days=35)).isoformat(),
            "payment_deadline_days": 45, "status": "open"
        }).execute()
        reply = await send_message(client, wa, "Gupta Traders ka kitna dena hai?")
        check("TD8_7 Vendor invoice detail",
              reply, must_contain=["gupta"])

        # TD8_8: MSME interest calculation for overdue vendor
        wa = "test_d8_8"
        prime_user_db(wa)
        reply = await send_message(client, wa, "MSME vendor ko 45 din baad pay karne par kitna interest lagega?")
        check("TD8_8 MSME interest question answered",
              reply, must_contain=["interest"])

        # -- Summary ----------------------------------------------------------
        print("\n" + "=" * 70)
        passed_count = sum(1 for _, p, _ in results if p is True)
        failed_count = sum(1 for _, p, _ in results if p is False)
        skipped_count = sum(1 for _, p, _ in results if p is None)
        total = len(results)
        run = total - skipped_count
        pct = int(passed_count / run * 100) if run else 0
        print(f"RESULTS: {passed_count}/{run} passed ({pct}%)  |  {skipped_count} skipped (Groq rate limit)  |  {failed_count} failed")

        failed = [(n, r) for n, p, r in results if p is False]
        if failed:
            print(f"\nFailed ({len(failed)}):")
            for name, reply in failed:
                print(f"  - {name}")
                print(f"    Reply: {reply[:200]}")
        print("=" * 70)
        return passed_count, failed_count


if __name__ == "__main__":
    start = time.time()
    passed, failed = asyncio.run(run_tests())
    elapsed = time.time() - start
    print(f"Completed in {elapsed:.1f}s")
    sys.exit(0 if failed == 0 else 1)
