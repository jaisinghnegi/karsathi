-- 005_reminders.sql
-- Adds reminders_sent JSONB column to users table.
-- Tracks which reminders have already been sent to avoid duplicates.
-- Key format: "gst_{filing_name}_{due_date_isoformat}" or "inv_{invoice_id}"
-- Value: ISO date string of when the reminder was sent
-- Run in Supabase SQL Editor AFTER 004_kg_extensions.sql

alter table public.users
  add column if not exists reminders_sent jsonb not null default '{}';

create index if not exists users_reminders_sent_idx on public.users using gin(reminders_sent);
