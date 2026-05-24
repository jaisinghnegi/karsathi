# Invoice Parser + Form I Risk Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable KarSathi to parse invoice photos and bank SMS texts, track 45-day MSME payment deadlines, and instantly alert users to Form I / 43B(h) risk in Hinglish.

**Architecture:** WhatsApp image messages go through Groq vision to vendor registry check to invoices table. Text messages go through a lightweight intent classifier before routing to either the SMS parser or existing Groq flow. A risk engine calculates 45-day countdown, penalty interest, and 43B(h) tax loss on every new invoice.

**Tech Stack:** FastAPI, Groq llama-3.3-70b-versatile (text + vision), Supabase PostgreSQL, difflib (string similarity), python-dotenv, httpx

---

## Build Order (critical path first)

1. Task 1 - Supabase tables (invoices + vendors)
2. Task 2 - database.py CRUD functions
3. Task 3 - invoice_parser.py (Groq vision)
4. Task 4 - risk_engine.py (45-day calc)
5. Task 5 - sms_parser.py + match_engine.py
6. Task 6 - Intent classifier in main.py
7. Task 7 - Wire image + SMS handling into main.py
8. Task 8 - API endpoints (/invoices, /vendors, /form1-assessment)
9. Task 9 - Smoke test end to end

---

## Task 1: Create invoices + vendors tables in Supabase

Run this SQL in Supabase SQL Editor:

alter table public.users add column if not exists tax_slab text default "unknown ";

create table public.vendors (
  id uuid default gen_random_uuid() primary key,
  phone_number text references public.users(phone_number),
  vendor_name text not null,
  gstin text,
  msme_status text default "unknown ",
  agreement_type text default "unknown ",
  first_seen_date date default current_date,
  confirmed_by_user boolean default false,
  created_at timestamptz default now()
);

create table public.invoices (
  id uuid default gen_random_uuid() primary key,
  phone_number text references public.users(phone_number),
  vendor_name text not null,
  amount numeric not null,
  invoice_date date not null,
  payment_deadline_days int default 45,
  due_date date,
  status text default "open ",
  created_at timestamptz default now()
);

create index on public.invoices (phone_number, status);
create index on public.vendors (phone_number, vendor_name);

Expected: Success. No rows returned.

---

See design doc at docs/plans/2026-04-19-invoice-parser-form1-risk.md for full data model.

Full code for each task will be implemented step by step.
