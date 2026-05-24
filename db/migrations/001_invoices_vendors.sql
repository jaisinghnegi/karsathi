-- Migration 001: Add tax_slab to users, create vendors and invoices tables
-- Run this in the Supabase SQL Editor

-- ─────────────────────────────────────────────
-- 1. Add tax_slab column to existing users table
-- ─────────────────────────────────────────────
alter table public.users
  add column if not exists tax_slab text default 'unknown';


-- ─────────────────────────────────────────────
-- 2. vendors table
-- ─────────────────────────────────────────────
create table if not exists public.vendors (
  id                uuid        default gen_random_uuid() primary key,
  phone_number      text        references public.users(phone_number),
  vendor_name       text        not null,
  gstin             text,
  msme_status       text        default 'unknown',    -- 'yes' | 'no' | 'unknown' | 'unverified'
  agreement_type    text        default 'unknown',    -- 'written' | 'verbal' | 'unknown'
  first_seen_date   date        default current_date,
  confirmed_by_user boolean     default false,
  created_at        timestamptz default now()
);

create index if not exists vendors_phone_vendor_idx
  on public.vendors (phone_number, vendor_name);


-- ─────────────────────────────────────────────
-- 3. invoices table
-- ─────────────────────────────────────────────
create table if not exists public.invoices (
  id                     uuid        default gen_random_uuid() primary key,
  phone_number           text        references public.users(phone_number),
  vendor_name            text        not null,
  amount                 numeric     not null,
  invoice_date           date        not null,
  payment_deadline_days  int         default 45,
  due_date               date,
  status                 text        default 'open',  -- 'open' | 'paid' | 'overdue'
  created_at             timestamptz default now()
);

create index if not exists invoices_phone_status_idx
  on public.invoices (phone_number, status);

create index if not exists invoices_phone_vendor_idx
  on public.invoices (phone_number, vendor_name);
