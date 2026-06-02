-- Migration 007: Add missing user profile columns
-- gst_status and city were referenced in code but never added to schema.
-- Without gst_status, compliance engine cannot personalise GST deadlines
-- and profile extraction silently fails on every message.

alter table public.users
  add column if not exists gst_status text,  -- 'registered' | 'not_registered' | null
  add column if not exists city       text;  -- city name from user messages
