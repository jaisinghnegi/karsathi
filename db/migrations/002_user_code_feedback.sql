-- Migration 002: Add user_code to users, create feedback table
-- Run this in the Supabase SQL Editor

-- ─────────────────────────────────────────────
-- 1. Add user_code to users table
-- ─────────────────────────────────────────────
alter table public.users
  add column if not exists user_code text unique;

-- Backfill existing users with a random 6-digit code
update public.users
set user_code = lpad((floor(random() * 900000) + 100000)::int::text, 6, '0')
where user_code is null;

-- ─────────────────────────────────────────────
-- 2. Ensure conversations table has created_at
-- ─────────────────────────────────────────────
alter table public.conversations
  add column if not exists created_at timestamptz default now();

-- ─────────────────────────────────────────────
-- 3. feedback table
-- ─────────────────────────────────────────────
create table if not exists public.feedback (
  id           uuid        default gen_random_uuid() primary key,
  phone_number text        not null,
  user_code    text,
  feedback     text        not null,
  created_at   timestamptz default now()
);

create index if not exists feedback_phone_idx
  on public.feedback (phone_number);
