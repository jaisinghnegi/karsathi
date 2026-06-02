-- Migration 012: KG data fixes
-- 1. Add GSTR-3B Quarterly entries for QRMP scheme users
-- 2. Add CMP-08 quarterly entry for Composition scheme users
-- 3. Fix DPDP penalty_amount_inr values (were 10x too high)

-- ─────────────────────────────────────────────
-- 1. GSTR-3B Quarterly for QRMP users
--    Due: 22nd (Cat 1 states) / 24th (Cat 2 states) of month after quarter end
--    quarter_offset_month = 1 means "1 month after the quarter ends"
-- ─────────────────────────────────────────────

insert into public.kg_compliance_calendar
  (law_key, filing_name, filing_name_hi, frequency, due_day, due_month,
   quarter_offset_month, applies_to, turnover_min_lakh, turnover_max_lakh,
   taxpayer_type, penalty_per_day_inr, portal_url, notes_en, notes_hi)
values

  ('GST', 'GSTR-3B Quarterly – QRMP (Cat 1 States)', 'GSTR-3B तिमाही – QRMP (श्रेणी 1 राज्य)', 'quarterly', 22, null, 1,
   'QRMP scheme businesses in Category 1 states (MH, KA, GJ, AP, TG, TN, KL, WB, OD, JH, BR, CG and others)',
   null, 500, 'qrmp', 50, 'https://www.gst.gov.in',
   'QRMP scheme users file GSTR-3B quarterly by 22nd of the month after quarter end (Jul 22, Oct 22, Jan 22, Apr 22) for Cat 1 states. Monthly PMT-06 challan payment still required by 25th of each month.',
   'QRMP स्कीम वाले Cat 1 राज्यों में तिमाही GSTR-3B 22 तारीख तक भरें (22 जुलाई, 22 अक्टूबर, 22 जनवरी, 22 अप्रैल)। हर महीने 25 तारीख तक PMT-06 चालान भुगतान जरूरी है।'),

  ('GST', 'GSTR-3B Quarterly – QRMP (Cat 2 States)', 'GSTR-3B तिमाही – QRMP (श्रेणी 2 राज्य)', 'quarterly', 24, null, 1,
   'QRMP scheme businesses in Category 2 states (HP, UK, PB, RJ, UP, HR, DL, J&K, Ladakh, Chandigarh and others)',
   null, 500, 'qrmp', 50, 'https://www.gst.gov.in',
   'QRMP scheme users file GSTR-3B quarterly by 24th of the month after quarter end (Jul 24, Oct 24, Jan 24, Apr 24) for Cat 2 states. Monthly PMT-06 challan payment still required by 25th of each month.',
   'QRMP स्कीम वाले Cat 2 राज्यों में तिमाही GSTR-3B 24 तारीख तक भरें (24 जुलाई, 24 अक्टूबर, 24 जनवरी, 24 अप्रैल)। हर महीने 25 तारीख तक PMT-06 चालान भुगतान जरूरी है।');


-- ─────────────────────────────────────────────
-- 2. CMP-08 for Composition scheme users
--    Due: 18th of month after each quarter end
-- ─────────────────────────────────────────────

insert into public.kg_compliance_calendar
  (law_key, filing_name, filing_name_hi, frequency, due_day, due_month,
   quarter_offset_month, applies_to, turnover_min_lakh, turnover_max_lakh,
   taxpayer_type, penalty_per_day_inr, portal_url, notes_en, notes_hi)
values

  ('GST', 'CMP-08 (Composition Quarterly Tax Payment)', 'CMP-08 (कम्पोजीशन तिमाही कर भुगतान)', 'quarterly', 18, null, 1,
   'Businesses registered under GST Composition Scheme (turnover ≤ ₹1.5 Crore)',
   null, 150, 'composition', 50, 'https://www.gst.gov.in',
   'Composition scheme taxpayers file CMP-08 (self-assessed tax challan) quarterly by 18th of the month after quarter end (Jul 18, Oct 18, Jan 18, Apr 18). Annual GSTR-4 still due by 30 April.',
   'कम्पोजीशन स्कीम वाले तिमाही के बाद के महीने की 18 तारीख तक CMP-08 भरें (18 जुलाई, 18 अक्टूबर, 18 जनवरी, 18 अप्रैल)। वार्षिक GSTR-4 अभी भी 30 अप्रैल तक देय है।');


-- ─────────────────────────────────────────────
-- 3. Fix DPDP penalty_amount_inr — values were 10x too high
--    ₹250 crore = 2,500,000,000 (not 25,000,000,000)
--    ₹200 crore = 2,000,000,000 (not 20,000,000,000)
--    ₹50 crore  =   500,000,000 (not  5,000,000,000)
-- ─────────────────────────────────────────────

update public.kg_penalties
set penalty_amount_inr = 2500000000
where law_key = 'DPDP' and violation_type = 'data_breach';

update public.kg_penalties
set penalty_amount_inr = 2000000000
where law_key = 'DPDP' and violation_type = 'consent_violation';

update public.kg_penalties
set penalty_amount_inr = 500000000
where law_key = 'DPDP' and violation_type = 'notice_violation';
