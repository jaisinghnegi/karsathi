-- Migration 011: Conversation summaries
-- Stores rolling summaries of past conversations so context isn't lost
-- beyond the 20-message window loaded on each request.

CREATE TABLE IF NOT EXISTS public.conversation_summaries (
  id SERIAL PRIMARY KEY,
  wa_id TEXT UNIQUE NOT NULL,
  summary TEXT NOT NULL,
  message_count_at_summary INT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
