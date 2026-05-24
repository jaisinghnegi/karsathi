# Supabase Persistent Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace in-memory conversation dict with Supabase-backed persistent storage so KarSathi remembers users and conversations across server restarts.

**Architecture:** Add a `database.py` module with all async Supabase calls. Wire it into `main.py` replacing the `conversations` dict. Add a Groq profile extractor that auto-updates the users table when profile fields are detected in conversation. In-memory dict stays as fallback if Supabase is unreachable.

**Tech Stack:** FastAPI, supabase-py (async), Groq llama-3.3-70b-versatile, PostgreSQL via Supabase

---

### Task 1: Install dependency + add env vars

**Files:**
- Modify: `requirements.txt`
- Modify: `.env`

**Step 1: Add supabase-py to requirements.txt**

Open `requirements.txt` and add:
```
supabase
```

**Step 2: Install it**

```
pip install supabase
```

Expected output: `Successfully installed supabase-x.x.x`

**Step 3: Add Supabase keys to .env**

Add these two lines to `.env`:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key-here
```

Leave as placeholders for now — user will fill in from Supabase dashboard.

---

### Task 2: Create tables in Supabase

**Where:** Supabase dashboard → SQL Editor → New query

**Step 1: Run this SQL to create users table**

```sql
CREATE TABLE IF NOT EXISTS users (
  phone_number TEXT PRIMARY KEY,
  language TEXT,
  business_type TEXT,
  state TEXT,
  city TEXT,
  turnover_bracket TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
```

**Step 2: Run this SQL to create conversations table**

```sql
CREATE TABLE IF NOT EXISTS conversations (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  phone_number TEXT REFERENCES users(phone_number) ON DELETE CASCADE,
  role TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_phone_created
  ON conversations(phone_number, created_at DESC);
```

**Step 3: Verify both tables appear in Table Editor**

---

### Task 3: Create database.py

**Files:**
- Create: `database.py`

**Full file content:**

```python
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Single client instance — supabase-py handles connection pooling
_client: Client | None = None

def get_client() -> Client | None:
    global _client
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    if _client is None:
        try:
            _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            print(f"[DB] Supabase init failed: {e}")
            return None
    return _client


async def get_or_create_user(phone_number: str) -> dict:
    """Returns user profile dict. Creates row if first time."""
    db = get_client()
    if not db:
        return {"phone_number": phone_number}
    try:
        result = db.table("users").select("*").eq("phone_number", phone_number).execute()
        if result.data:
            return result.data[0]
        # First time — insert new user
        new_user = {"phone_number": phone_number}
        db.table("users").insert(new_user).execute()
        return new_user
    except Exception as e:
        print(f"[DB] get_or_create_user error: {e}")
        return {"phone_number": phone_number}


async def save_message(phone_number: str, role: str, message: str) -> None:
    """Saves a single message to conversations table."""
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
    """Returns last N messages as list of {role, content} dicts for Groq."""
    db = get_client()
    if not db:
        return []
    try:
        result = (
            db.table("conversations")
            .select("role, message, created_at")
            .eq("phone_number", phone_number)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        # Reverse so oldest message is first (Groq expects chronological order)
        messages = list(reversed(result.data or []))
        return [{"role": m["role"], "content": m["message"]} for m in messages]
    except Exception as e:
        print(f"[DB] get_conversation_history error: {e}")
        return []


async def update_user_profile(phone_number: str, field: str, value: str) -> None:
    """Updates a single profile field on the users row."""
    db = get_client()
    if not db:
        return
    valid_fields = {"language", "business_type", "state", "city", "turnover_bracket"}
    if field not in valid_fields:
        return
    try:
        db.table("users").update({field: value}).eq("phone_number", phone_number).execute()
        print(f"[DB] Profile updated — {phone_number}: {field} = {value}")
    except Exception as e:
        print(f"[DB] update_user_profile error: {e}")
```

---

### Task 4: Add profile extractor function to main.py

**Files:**
- Modify: `main.py`

This function sends the last assistant reply to Groq and asks it to extract any profile fields as JSON. It runs after every reply and silently updates the DB.

**Step 1: Add import at top of main.py**

Add after existing imports:
```python
from database import get_or_create_user, save_message, get_conversation_history, update_user_profile
```

**Step 2: Add the extractor function after the SYSTEM_PROMPT block**

```python
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

        import json
        extracted = json.loads(raw)
        for field, value in extracted.items():
            if value:
                await update_user_profile(phone_number, field, str(value))
    except Exception as e:
        print(f"[Profile extractor] silently failed: {e}")
```

---

### Task 5: Rewrite get_groq_response to use DB

**Files:**
- Modify: `main.py` — replace the `get_groq_response` function and the `conversations` dict

**Step 1: Remove the in-memory dict and old helper**

Delete these lines from main.py:
```python
# In-memory conversation store: { wa_id: { "messages": [], "profile": {} } }
conversations: dict = {}


def get_conversation(wa_id: str) -> dict:
    if wa_id not in conversations:
        conversations[wa_id] = {"messages": [], "profile": {}}
    return conversations[wa_id]
```

Replace with fallback-only in-memory store:
```python
# Fallback in-memory store used only when Supabase is unreachable
_memory_fallback: dict = {}

def _get_fallback(wa_id: str) -> dict:
    if wa_id not in _memory_fallback:
        _memory_fallback[wa_id] = {"messages": [], "profile": {}}
    return _memory_fallback[wa_id]
```

**Step 2: Replace get_groq_response entirely**

```python
async def get_groq_response(wa_id: str, user_message: str) -> str:
    # Ensure user exists in DB
    await get_or_create_user(wa_id)

    # Fetch history from DB (falls back to [] if DB is down)
    history = await get_conversation_history(wa_id, limit=20)

    # If DB returned nothing, try in-memory fallback
    if not history:
        fallback = _get_fallback(wa_id)
        fallback["messages"].append({"role": "user", "content": user_message})
        history = fallback["messages"][-20:]
    else:
        # Also keep fallback in sync so it's usable if DB goes down mid-session
        fallback = _get_fallback(wa_id)
        fallback["messages"] = history.copy()
        fallback["messages"].append({"role": "user", "content": user_message})

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_message}],
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

    # Persist both messages to DB (fire and forget — don't block reply)
    await save_message(wa_id, "user", user_message)
    await save_message(wa_id, "assistant", reply)

    # Extract profile fields silently
    await extract_and_update_profile(wa_id, user_message)

    return reply
```

---

### Task 6: Update conversation endpoints to use DB

**Files:**
- Modify: `main.py` — update GET and DELETE /conversation endpoints

**Replace the two existing endpoints:**

```python
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
```

Also add this import at the top of main.py for the reset endpoint:
```python
from database import get_client
```

---

### Task 7: Add GET /user/{wa_id} profile endpoint

**Files:**
- Modify: `main.py`

Add after the health endpoint:
```python
@app.get("/user/{wa_id}")
async def get_user_profile(wa_id: str):
    user = await get_or_create_user(wa_id)
    return user
```

---

### Task 8: Fill in Supabase credentials and test

**Step 1: Get credentials from Supabase dashboard**
- Go to supabase.com → your project → Settings → API
- Copy **Project URL** → paste as `SUPABASE_URL` in `.env`
- Copy **anon public key** → paste as `SUPABASE_KEY` in `.env`

**Step 2: Restart uvicorn**
```
python -m uvicorn main:app --reload --port 8000
```

**Step 3: Send a test message and verify DB**
```
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"from":"917814523601","type":"text","text":{"body":"Hi, mera kirana store hai Rajasthan mein"}}]}}]}]}'
```

**Step 4: Check Supabase Table Editor**
- `users` table should have a row for `917814523601`
- `conversations` table should have 2 rows (user + assistant)
- If `business_type` or `state` was extracted, the users row will be updated

**Step 5: Restart server and send another message**

Verify that the bot remembers the previous conversation — it should NOT ask for business type again.

**Step 6: Check profile endpoint**
```
curl http://localhost:8000/user/917814523601
```
Should return the profile with any extracted fields filled in.
