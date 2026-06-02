"""
test_group9.py — Group 9 only (Day 7: Government Paperwork Guidance)
Run: python test_group9.py
"""
import asyncio, sys, time
import httpx
from dotenv import load_dotenv
load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"
_GROQ_RATE_LIMIT_MSG = "abhi thoda technical issue"
results = []


def _db():
    from supabase import create_client
    import os
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

_sb = None
def get_sb():
    global _sb
    if not _sb: _sb = _db()
    return _sb

def prime(wa_id):
    db = get_sb()
    if not db.table("users").select("phone_number").eq("phone_number", wa_id).execute().data:
        db.table("users").insert({"phone_number": wa_id}).execute()
    db.table("conversations").delete().eq("phone_number", wa_id).execute()
    db.table("conversations").insert({"phone_number": wa_id, "role": "assistant", "message": "KarSathi mein swagat!"}).execute()

async def send(client, wa_id, text):
    try:
        r = await client.post(f"{BASE}/test/chat", json={"wa_id": wa_id, "text": text}, timeout=90)
        d = r.json()
        return d.get("reply", f"[ERROR] {d.get('error','no reply')}")
    except Exception as e:
        return f"[TIMEOUT] {e}"

def check(name, reply, must_contain=None, must_not_contain=None):
    rl = reply.lower()
    if _GROQ_RATE_LIMIT_MSG in rl:
        print(f"  [SKIP] {name} — rate limited")
        results.append((name, None))
        return
    errors = []
    for p in (must_contain or []):
        if p.lower() not in rl:
            errors.append(f"missing: '{p}'")
    for p in (must_not_contain or []):
        if p.lower() in rl:
            errors.append(f"unwanted: '{p}'")
    ok = not errors
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        for e in errors: print(f"         ERR: {e}")
    print(f"         Reply: {reply[:130].replace(chr(10),' | ')}")
    results.append((name, ok))

async def run():
    async with httpx.AsyncClient(timeout=httpx.Timeout(90)) as c:
        print(f"\nServer: {(await c.get(f'{BASE}/health')).json()}")
        print("=" * 65)
        print("GROUP 9 — Day 7: Government Paperwork Guidance (8 tests)")
        print("=" * 65)

        prime("g9_1")
        r = await send(c, "g9_1", "GST registration kaise karte hain? Steps batao")
        check("TD7_1 GST registration steps", r, must_contain=["gst"])

        prime("g9_2")
        r = await send(c, "g9_2", "FSSAI licence kaise milega? Kya documents chahiye?")
        check("TD7_2 FSSAI steps + documents", r, must_contain=["fssai"])

        prime("g9_3")
        r = await send(c, "g9_3", "Udyam registration kaise karein? Process kya hai?")
        check("TD7_3 Udyam steps (free + Aadhaar)", r, must_contain=["udyam"])

        prime("g9_4")
        r = await send(c, "g9_4", "Shop registration kaise karein? Trade licence kaise banwao?")
        check("TD7_4 Shops Act / trade licence", r, must_contain=["registration"])

        await asyncio.sleep(10)

        prime("g9_5")
        r = await send(c, "g9_5", "Export karna hai, IEC kaise lena hai? DGFT pe kaise apply karein?")
        check("TD7_5 IEC steps (DGFT + Rs.500)", r, must_contain=["iec"])

        prime("g9_6")
        r = await send(c, "g9_6", "PF registration kaise karein? EPFO mein kaise register hote hain?")
        check("TD7_6 PF/EPFO registration steps", r, must_contain=["pf"])

        prime("g9_7")
        r = await send(c, "g9_7", "Mujhe naya restaurant kholna hai. GST aur FSSAI dono kaise loon?")
        check("TD7_7 Multi-law (GST + FSSAI both)", r, must_contain=["gst", "fssai"])

        prime("g9_8")
        r = await send(c, "g9_8", "IEC update karna hai, kab tak karna padega?")
        check("TD7_8 IEC annual update deadline (June 30)", r, must_contain=["iec"])

        print("\n" + "=" * 65)
        passed = sum(1 for _, p in results if p is True)
        failed = sum(1 for _, p in results if p is False)
        skipped = sum(1 for _, p in results if p is None)
        run = len(results) - skipped
        print(f"RESULTS: {passed}/{run} passed  |  {skipped} skipped  |  {failed} failed")
        if failed:
            print("FAILED:")
            for n, p in results:
                if p is False: print(f"  - {n}")
        print("=" * 65)

if __name__ == "__main__":
    t = time.time()
    asyncio.run(run())
    print(f"Done in {time.time()-t:.1f}s")
