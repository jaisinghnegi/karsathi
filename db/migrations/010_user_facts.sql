-- Migration 010: Persistent user facts memory
-- Stores arbitrary named facts extracted from conversations (CA name, bank, GST number, etc.)

CREATE TABLE IF NOT EXISTS public.user_facts (
  id SERIAL PRIMARY KEY,
  wa_id TEXT NOT NULL,
  fact_key TEXT NOT NULL,
  fact_value TEXT NOT NULL,
  confidence TEXT DEFAULT 'high',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(wa_id, fact_key)
);

CREATE INDEX IF NOT EXISTS user_facts_wa_id_idx ON public.user_facts(wa_id);
