-- Migration 003: Knowledge Graph v19 tables
-- Run this in the Supabase SQL Editor BEFORE running migrate_kg.py

-- ─────────────────────────────────────────────
-- Core reference tables (order matters for FK deps)
-- ─────────────────────────────────────────────

create table if not exists public.kg_segments (
  segmentid   int  primary key,
  segmentname text not null,
  description text
);

create table if not exists public.kg_subsegments (
  subsegmentid   int  primary key,
  segmentid      int  references public.kg_segments(segmentid),
  subsegmentname text not null,
  description    text
);

create table if not exists public.kg_flags (
  flagkey     text primary key,
  description text
);

create table if not exists public.kg_subsegment_flags (
  subsegmentid int  references public.kg_subsegments(subsegmentid),
  flagkey      text references public.kg_flags(flagkey),
  primary key (subsegmentid, flagkey)
);

create table if not exists public.kg_nic_codes (
  niccode     text primary key,
  level       text,
  description text
);

create table if not exists public.kg_subsegment_nic_map (
  subsegmentid int  references public.kg_subsegments(subsegmentid),
  niccode      text references public.kg_nic_codes(niccode),
  primary key (subsegmentid, niccode)
);

create table if not exists public.kg_states (
  stateid      int  primary key,
  statename    text not null,
  gst_category text
);

create table if not exists public.kg_laws (
  lawid              int  primary key,
  lawname            text not null,
  lawkey             text,
  scope              text,
  description        text,
  primaryauthority   text,
  lawtype            text,
  benefitcategory    text,
  maxbenefit_inr     text,
  applicablesegments text,
  sourceurl          text,
  statecode          text
);

create table if not exists public.kg_result_types (
  resultkey       text primary key,
  lawcomponentkey text,
  description     text
);

create table if not exists public.kg_inputs (
  inputkey  text primary key,
  prompt_en text,
  prompt_hi text
);

create table if not exists public.kg_law_component_inputs (
  lawcomponentkey text,
  inputkey        text references public.kg_inputs(inputkey),
  isrequired      text,
  primary key (lawcomponentkey, inputkey)
);

create table if not exists public.kg_explanations (
  explanationcode text primary key,
  shorttext_en    text,
  longtext_en     text,
  shorttext_hi    text,
  longtext_hi     text
);

create table if not exists public.kg_rules (
  ruleid          int  primary key,
  lawid           int  references public.kg_laws(lawid),
  lawcomponentkey text,
  segmentid       int,
  subsegmentid    int,
  resultkey       text,
  priority        int,
  effectivefrom   text,
  effectiveto     text,
  explanationcode text references public.kg_explanations(explanationcode)
);

create table if not exists public.kg_rule_conditions (
  ruleid    int  references public.kg_rules(ruleid),
  fieldname text,
  operator  text,
  value     text
);

create table if not exists public.kg_nic_master (
  sectioncode   text,
  sectionname   text,
  divisioncode  text,
  divisionname  text,
  msme_relevant text
);

create table if not exists public.kg_law_knowledge (
  lawid                int,
  lawcomponentkey      text,
  summary_en           text,
  summary_hi           text,
  msme_relevance_en    text,
  msme_relevance_hi    text,
  key_thresholds_en    text,
  key_thresholds_hi    text,
  typical_scenarios_en text,
  typical_scenarios_hi text,
  faq1_q_en            text,
  faq1_a_en            text,
  faq1_q_hi            text,
  faq1_a_hi            text,
  faq2_q_en            text,
  faq2_a_en            text,
  faq2_q_hi            text,
  faq2_a_hi            text,
  primarysourceurl     text,
  secondarysourceurl   text
);

create table if not exists public.kg_nic_flag_map (
  sectioncode  text,
  divisioncode text,
  divisionname text,
  defaultflags text,
  notes_en     text
);

-- ─────────────────────────────────────────────
-- State law summary tables
-- All 12 states share the same column schema
-- ─────────────────────────────────────────────

create table if not exists public.kg_state_laws_rj (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

create table if not exists public.kg_state_laws_gj (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

create table if not exists public.kg_state_laws_mh (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

create table if not exists public.kg_state_laws_up (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

create table if not exists public.kg_state_laws_tn (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

create table if not exists public.kg_state_laws_wb (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

create table if not exists public.kg_state_laws_ka (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

create table if not exists public.kg_state_laws_dl (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

create table if not exists public.kg_state_laws_ts (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

create table if not exists public.kg_state_laws_ap (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

create table if not exists public.kg_state_laws_mp (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

create table if not exists public.kg_state_laws_pb (
  law_id              text,
  law_name            text,
  law_key             text,
  primary_authority   text,
  key_obligation      text,
  threshold_trigger   text,
  verification_status text,
  effective_date      text,
  source_url          text
);

-- ─────────────────────────────────────────────
-- Indexes for common query patterns
-- ─────────────────────────────────────────────

create index if not exists kg_subsegments_segmentid_idx   on public.kg_subsegments(segmentid);
create index if not exists kg_laws_statecode_idx          on public.kg_laws(statecode);
create index if not exists kg_laws_lawkey_idx             on public.kg_laws(lawkey);
create index if not exists kg_rules_lawid_idx             on public.kg_rules(lawid);
create index if not exists kg_rules_segmentid_idx         on public.kg_rules(segmentid);
create index if not exists kg_rules_subsegmentid_idx      on public.kg_rules(subsegmentid);
create index if not exists kg_rule_conditions_ruleid_idx  on public.kg_rule_conditions(ruleid);
create index if not exists kg_law_knowledge_lawid_idx     on public.kg_law_knowledge(lawid);
create index if not exists kg_nic_master_sectioncode_idx  on public.kg_nic_master(sectioncode);
