# Weeks 3-4: Invoice Parser + Form I Risk Engine — Design Doc

## What We're Building

KarSathi receives invoice photos and bank SMS texts on WhatsApp.
It parses them, builds a vendor registry, tracks 45-day payment deadlines,
and instantly alerts the user to Form I / 43B(h) risk in plain Hinglish.

---

## Architecture

```
WhatsApp image  → invoice_parser.py (Groq vision) → vendors table (ask once per new vendor)
                                                   → invoices table (start 45-day clock)
                                                   → risk_engine.py (instant alert)

WhatsApp text   → classify_intent() (Groq, 2 tokens)
                    "sms_payment"        → sms_parser.py → match_engine.py → mark paid / confirm / flag
                    "invoice_question"   → existing Groq flow with invoice context injected
                    "general_compliance" → existing Groq flow (unchanged)
```

---

## New Supabase Tables

### invoices
| column | type | notes |
|--------|------|-------|
| id | uuid PK | |
| phone_number | text FK → users | |
| vendor_name | text | |
| amount | numeric | |
| invoice_date | date | |
| agreement_type | text | 'written' \| 'verbal' \| 'unknown', default 'unknown' |
| payment_deadline_days | int | 15 if verbal, 45 if written/unknown |
| due_date | date | invoice_date + payment_deadline_days |
| status | text | 'open' \| 'paid' \| 'overdue' |
| created_at | timestamptz | |

### vendors
| column | type | notes |
|--------|------|-------|
| id | uuid PK | |
| phone_number | text FK → users | |
| vendor_name | text | |
| gstin | text | optional |
| msme_status | text | 'yes' \| 'no' \| 'unknown' \| 'unverified' |
| first_seen_date | date | |
| confirmed_by_user | bool | default false |

### users table addition
| column | type | notes |
|--------|------|-------|
| tax_slab | text | '30%' \| '25%' \| '22%' \| 'unknown', default 'unknown' |

---

## New Files

| file | purpose |
|------|---------|
| `invoice_parser.py` | Groq vision call → returns {vendor_name, amount, invoice_date} |
| `sms_parser.py` | Groq text → returns {vendor_name, amount, payment_date} from SMS |
| `risk_engine.py` | 45-day countdown, penalty calc, 43B(h) tax loss range |
| `match_engine.py` | exact/fuzzy/no-match logic (stub first, full in week 4) |

## Modified Files

| file | change |
|------|--------|
| `database.py` | add invoice + vendor CRUD |
| `main.py` | handle image msg type + intent classifier |

---

## Intent Classification

Every incoming text goes through a lightweight Groq classifier first:

```python
# returns one of: "sms_payment" | "invoice_question" | "general_compliance" | "other"
intent = await classify_intent(text)
```

Why: regex is fragile. "UPI se kal bheja tha Ramesh ko" will never match a pattern
but Groq classifies it correctly. Cost is negligible (2 tokens output).

---

## Vendor Flow (ask once, never again)

1. Invoice parsed → vendor_name extracted
2. Check vendors table: has this vendor appeared before?
3. **New vendor** → ask: *"Ramesh Traders — kya yeh MSME registered supplier hai? (Haan / Nahi / Pata nahi)"*
4. Store answer permanently:
   - Haan → msme_status = 'yes', confirmed_by_user = true
   - Nahi → msme_status = 'no', confirmed_by_user = true
   - Pata nahi → msme_status = 'unknown', ask for GSTIN: *"GSTIN doge toh main verify kar sakta hoon"*
5. All future invoices from same vendor → use stored status, never ask again

Also ask once per vendor: *"Koi written agreement hai Ramesh Traders ke saath?"*
→ sets agreement_type → sets payment_deadline_days (15 or 45)

---

## SMS Payment Matching Logic

```
Exact match:  vendor similarity > 90% AND amount exact AND date within 60 days → auto-close ✅
Fuzzy match:  similarity 70–90% OR amount within 5% OR multiple open invoices → ask to confirm
No match:     similarity < 70% OR no open invoices → log + notify user
```

---

## Risk Output Format (WhatsApp reply)

```
Ramesh Traders ₹45,000 — 15 March ✅ saved

⏳ 23 din baaki payment ke liye (due: 29 April)
Agar late hua:
• Interest: ₹2,250 (3× bank rate)
• Tax loss: ₹9,900–₹13,500 extra tax (43B(h), slab ke hisaab se)

MSME status: confirmed ✓
```

If tax_slab known: show exact figure. If unknown: show range.

---

## /form1-assessment Response (demo endpoint)

```json
{
  "summary": {
    "total_overdue_amount": 145000,
    "total_penalty_interest": 7250,
    "total_43bh_tax_loss_min": 31900,
    "total_43bh_tax_loss_max": 43500,
    "invoices_at_risk": 3
  },
  "invoices": [
    {
      "vendor_name": "Ramesh Traders",
      "amount": 45000,
      "invoice_date": "2026-03-15",
      "due_date": "2026-04-29",
      "days_remaining": 10,
      "status": "open",
      "msme_status": "yes",
      "penalty_interest": 2250,
      "tax_loss_min": 9900,
      "tax_loss_max": 13500
    }
  ]
}
```

---

## Build Order (critical path first)

1. `invoice_parser.py` — everything depends on structured invoice data
2. DB schema — invoices + vendors tables
3. Vendor flow in main.py — ask once logic
4. `risk_engine.py` — 45-day calc + penalty
5. `sms_parser.py` + `match_engine.py` (stub first)
6. `/form1-assessment` endpoint
7. `/invoices/{wa_id}` + `/vendors/{wa_id}` endpoints

