-- Migration 004: Knowledge Graph Extensions
-- Adds compliance calendar, penalties, and compliance actions tables
-- Run in Supabase SQL Editor AFTER 003_knowledge_graph.sql

-- ─────────────────────────────────────────────
-- 1. Compliance Calendar
--    Powers proactive GST / MSMED / TDS reminders
-- ─────────────────────────────────────────────

create table if not exists public.kg_compliance_calendar (
  id                   serial primary key,
  law_key              text not null,
  filing_name          text not null,           -- "GSTR-1 Monthly", "Advance Tax Q1"
  filing_name_hi       text,
  frequency            text not null,           -- 'monthly' | 'quarterly' | 'annual' | 'half_yearly' | 'one_time'
  due_day              int,                     -- day of month (e.g. 11 for GSTR-1)
  due_month            int,                     -- null = repeating; set for annual (e.g. 7 = July)
  quarter_offset_month int,                     -- for quarterly: month after quarter end (1 = 1 month after)
  applies_to           text,                    -- free text: who this applies to
  turnover_min_lakh    numeric,                 -- lower bound filter (null = no min)
  turnover_max_lakh    numeric,                 -- upper bound filter (null = no max)
  taxpayer_type        text,                    -- 'regular' | 'composition' | 'qrmp' | 'all'
  penalty_per_day_inr  numeric,                 -- late fee per day (for reminder urgency)
  portal_url           text,
  notes_en             text,
  notes_hi             text
);

-- GST Filing Deadlines
insert into public.kg_compliance_calendar
  (law_key, filing_name, filing_name_hi, frequency, due_day, due_month, quarter_offset_month, applies_to, turnover_min_lakh, turnover_max_lakh, taxpayer_type, penalty_per_day_inr, portal_url, notes_en, notes_hi)
values
  -- GSTR-1 Monthly (turnover > ₹5Cr)
  ('GST', 'GSTR-1 (Monthly)', 'GSTR-1 (मासिक)', 'monthly', 11, null, null,
   'GST-registered businesses with annual turnover above ₹5 Crore', 500, null, 'regular',
   50, 'https://www.gst.gov.in',
   'File GSTR-1 by 11th of the following month. Reports all outward supplies (sales invoices).',
   'अगले महीने की 11 तारीख तक GSTR-1 भरें। सभी बिक्री इनवॉयस रिपोर्ट करें।'),

  -- GSTR-1 Quarterly (QRMP scheme, turnover ≤ ₹5Cr)
  ('GST', 'GSTR-1 (Quarterly – QRMP)', 'GSTR-1 (त्रैमासिक – QRMP)', 'quarterly', 13, null, 1,
   'Businesses with turnover up to ₹5 Crore under QRMP scheme', null, 500, 'qrmp',
   50, 'https://www.gst.gov.in',
   'File GSTR-1 quarterly by 13th of month after quarter end (Jul 13, Oct 13, Jan 13, Apr 13).',
   'QRMP स्कीम वाले तिमाही के बाद के महीने की 13 तारीख तक GSTR-1 भरें।'),

  -- GSTR-3B Monthly (turnover > ₹5Cr)
  ('GST', 'GSTR-3B (Monthly)', 'GSTR-3B (मासिक)', 'monthly', 20, null, null,
   'GST-registered businesses with annual turnover above ₹5 Crore', 500, null, 'regular',
   50, 'https://www.gst.gov.in',
   'File GSTR-3B by 20th of the following month. Pay net GST liability along with filing.',
   'अगले महीने की 20 तारीख तक GSTR-3B भरें और बकाया GST का भुगतान करें।'),

  -- GSTR-3B Monthly (turnover ₹1.5Cr–₹5Cr, Category 1 states: 22nd)
  ('GST', 'GSTR-3B (Monthly – Cat 1 States)', 'GSTR-3B (मासिक – श्रेणी 1)', 'monthly', 22, null, null,
   'Turnover ₹1.5Cr–₹5Cr in Category 1 states (MH, KA, GJ, etc.)', 150, 500, 'regular',
   50, 'https://www.gst.gov.in',
   'Category 1 states: Maharashtra, Karnataka, Gujarat, Goa, Andhra Pradesh, Telangana, Tamil Nadu, Kerala, West Bengal, Odisha, Jharkhand, Bihar, Sikkim, Arunachal Pradesh, Nagaland, Manipur, Mizoram, Tripura, Meghalaya, Assam, Chhattisgarh.',
   'श्रेणी 1 राज्यों के लिए 22 तारीख तक GSTR-3B भरें।'),

  -- GSTR-3B Monthly (turnover ₹1.5Cr–₹5Cr, Category 2 states: 24th)
  ('GST', 'GSTR-3B (Monthly – Cat 2 States)', 'GSTR-3B (मासिक – श्रेणी 2)', 'monthly', 24, null, null,
   'Turnover ₹1.5Cr–₹5Cr in Category 2 states (HP, UK, PB, RJ, UP, HR, DL, J&K, etc.)', 150, 500, 'regular',
   50, 'https://www.gst.gov.in',
   'Category 2 states: Himachal Pradesh, Uttarakhand, Punjab, Rajasthan, Uttar Pradesh, Haryana, Delhi, Jammu & Kashmir, Ladakh, Dadra & Nagar Haveli, Daman & Diu, Chandigarh, Lakshadweep, Puducherry, Andaman & Nicobar.',
   'श्रेणी 2 राज्यों के लिए 24 तारीख तक GSTR-3B भरें।'),

  -- GSTR-9 Annual Return
  ('GST', 'GSTR-9 (Annual Return)', 'GSTR-9 (वार्षिक रिटर्न)', 'annual', 31, 12, null,
   'All GST-registered businesses with turnover above ₹2 Crore (optional below)', 200, null, 'regular',
   200, 'https://www.gst.gov.in',
   'Annual GST return summarising the full financial year. Due 31 December. Late fee ₹200/day, max ₹10,000.',
   'पूरे वित्त वर्ष का सारांश वार्षिक GST रिटर्न। 31 दिसंबर तक भरें। Late fee ₹200/दिन, maximum ₹10,000 तक।'),

  -- GSTR-4 Composition Annual
  ('GST', 'GSTR-4 (Composition Annual)', 'GSTR-4 (कम्पोजीशन वार्षिक)', 'annual', 30, 4, null,
   'Businesses under GST Composition Scheme', null, 150, 'composition',
   50, 'https://www.gst.gov.in',
   'Composition taxpayers file GSTR-4 once a year by 30 April for the previous financial year.',
   'कम्पोजीशन स्कीम वाले पिछले FY के लिए 30 अप्रैल तक GSTR-4 भरें।'),

  -- Income Tax – Advance Tax Q1
  ('INCOME_TAX', 'Advance Tax – Q1 (15%)', 'एडवांस टैक्स – Q1 (15%)', 'annual', 15, 6, null,
   'All businesses/individuals with tax liability above ₹10,000 for the year', null, null, 'all',
   null, 'https://www.incometax.gov.in',
   'Pay 15% of estimated annual tax by 15 June.',
   'अनुमानित वार्षिक कर का 15% 15 जून तक चुकाएं।'),

  -- Income Tax – Advance Tax Q2
  ('INCOME_TAX', 'Advance Tax – Q2 (45%)', 'एडवांस टैक्स – Q2 (45%)', 'annual', 15, 9, null,
   'All businesses/individuals with tax liability above ₹10,000 for the year', null, null, 'all',
   null, 'https://www.incometax.gov.in',
   'Pay cumulative 45% of estimated annual tax by 15 September.',
   'अनुमानित वार्षिक कर का संचित 45% 15 सितंबर तक चुकाएं।'),

  -- Income Tax – Advance Tax Q3
  ('INCOME_TAX', 'Advance Tax – Q3 (75%)', 'एडवांस टैक्स – Q3 (75%)', 'annual', 15, 12, null,
   'All businesses/individuals with tax liability above ₹10,000 for the year', null, null, 'all',
   null, 'https://www.incometax.gov.in',
   'Pay cumulative 75% of estimated annual tax by 15 December.',
   'अनुमानित वार्षिक कर का संचित 75% 15 दिसंबर तक चुकाएं।'),

  -- Income Tax – Advance Tax Q4
  ('INCOME_TAX', 'Advance Tax – Q4 (100%)', 'एडवांस टैक्स – Q4 (100%)', 'annual', 15, 3, null,
   'All businesses/individuals with tax liability above ₹10,000 for the year', null, null, 'all',
   null, 'https://www.incometax.gov.in',
   'Pay 100% of estimated annual tax by 15 March.',
   'अनुमानित वार्षिक कर का 100% 15 मार्च तक चुकाएं।'),

  -- Income Tax – ITR Filing (Non-Audit)
  ('INCOME_TAX', 'ITR Filing (Non-Audit)', 'ITR दाखिल (बिना ऑडिट)', 'annual', 31, 7, null,
   'Individuals, proprietors, and partners not requiring tax audit', null, null, 'all',
   null, 'https://www.incometax.gov.in',
   'File income tax return by 31 July for the previous financial year.',
   'पिछले वित्त वर्ष के लिए 31 जुलाई तक इनकम टैक्स रिटर्न भरें।'),

  -- Income Tax – ITR Filing (Audit Cases)
  ('INCOME_TAX', 'ITR Filing (Tax Audit Cases)', 'ITR दाखिल (टैक्स ऑडिट)', 'annual', 31, 10, null,
   'Businesses requiring tax audit under Section 44AB (turnover > ₹1Cr for business, ₹50L for profession)', 100, null, 'all',
   null, 'https://www.incometax.gov.in',
   'File ITR by 31 October if your business requires a tax audit under Section 44AB.',
   'धारा 44AB के तहत टैक्स ऑडिट वाले व्यवसायों के लिए 31 अक्टूबर तक ITR भरें।'),

  -- TDS Deposit
  ('INCOME_TAX', 'TDS Deposit (Monthly)', 'TDS जमा (मासिक)', 'monthly', 7, null, null,
   'Businesses deducting TDS on salary, contractor payments, rent, or professional fees', null, null, 'all',
   null, 'https://www.incometax.gov.in',
   'Deposit TDS deducted in the previous month by 7th (30 April for March deductions).',
   'पिछले महीने का काटा गया TDS 7 तारीख तक जमा करें (मार्च का TDS 30 अप्रैल तक)।'),

  -- TDS Return Q1
  ('INCOME_TAX', 'TDS Return – Q1 (Apr–Jun)', 'TDS रिटर्न – Q1 (अप्रैल–जून)', 'annual', 31, 7, null,
   'All TDS deductors', null, null, 'all',
   null, 'https://www.incometax.gov.in',
   'File quarterly TDS return (Form 24Q/26Q) for April–June by 31 July.',
   'अप्रैल–जून तिमाही का TDS रिटर्न 31 जुलाई तक भरें।'),

  -- TDS Return Q2
  ('INCOME_TAX', 'TDS Return – Q2 (Jul–Sep)', 'TDS रिटर्न – Q2 (जुलाई–सितंबर)', 'annual', 31, 10, null,
   'All TDS deductors', null, null, 'all',
   null, 'https://www.incometax.gov.in',
   'File quarterly TDS return for July–September by 31 October.',
   'जुलाई–सितंबर तिमाही का TDS रिटर्न 31 अक्टूबर तक भरें।'),

  -- TDS Return Q3
  ('INCOME_TAX', 'TDS Return – Q3 (Oct–Dec)', 'TDS रिटर्न – Q3 (अक्टूबर–दिसंबर)', 'annual', 31, 1, null,
   'All TDS deductors', null, null, 'all',
   null, 'https://www.incometax.gov.in',
   'File quarterly TDS return for October–December by 31 January.',
   'अक्टूबर–दिसंबर तिमाही का TDS रिटर्न 31 जनवरी तक भरें।'),

  -- TDS Return Q4
  ('INCOME_TAX', 'TDS Return – Q4 (Jan–Mar)', 'TDS रिटर्न – Q4 (जनवरी–मार्च)', 'annual', 31, 5, null,
   'All TDS deductors', null, null, 'all',
   null, 'https://www.incometax.gov.in',
   'File quarterly TDS return for January–March by 31 May.',
   'जनवरी–मार्च तिमाही का TDS रिटर्न 31 मई तक भरें।'),

  -- PF/ESI Deposit
  ('SS_CODE', 'PF Deposit (Monthly)', 'PF जमा (मासिक)', 'monthly', 15, null, null,
   'Establishments with 20 or more employees', null, null, 'all',
   null, 'https://unifiedportal-emp.epfindia.gov.in',
   'Deposit both employer and employee PF contributions by 15th of the following month.',
   'अगले महीने की 15 तारीख तक नियोक्ता और कर्मचारी दोनों का PF जमा करें।'),

  ('SS_CODE', 'ESI Deposit (Monthly)', 'ESI जमा (मासिक)', 'monthly', 21, null, null,
   'Establishments with 10 or more employees with wages up to ₹21,000/month', null, null, 'all',
   null, 'https://www.esic.in',
   'Deposit ESI contributions by 21st of the following month.',
   'अगले महीने की 21 तारीख तक ESI का योगदान जमा करें।'),

  -- MSMED Form I (half-yearly)
  ('MSMED', 'MSMED Form I – H1 (Apr–Sep)', 'MSMED Form I – H1 (अप्रैल–सितंबर)', 'half_yearly', 31, 10, null,
   'All buyers who have received supplies from MSME vendors and have overdue payments', null, null, 'all',
   null, 'https://msme.gov.in/form-i',
   'File Form I for the April–September half-year by 31 October. Disclose all MSME vendors with pending payments and reasons for delay.',
   'अप्रैल–सितंबर की अर्धवार्षिक Form I 31 अक्टूबर तक भरें। MSME विक्रेताओं को बकाया भुगतान और देरी का कारण बताएं।'),

  ('MSMED', 'MSMED Form I – H2 (Oct–Mar)', 'MSMED Form I – H2 (अक्टूबर–मार्च)', 'half_yearly', 30, 4, null,
   'All buyers who have received supplies from MSME vendors and have overdue payments', null, null, 'all',
   null, 'https://msme.gov.in/form-i',
   'File Form I for the October–March half-year by 30 April. Failure to file invites penalty under MSMED Act.',
   'अक्टूबर–मार्च की अर्धवार्षिक Form I 30 अप्रैल तक भरें। न भरने पर MSMED Act के तहत जुर्माना।');


-- ─────────────────────────────────────────────
-- 2. Penalties Table
--    Structured penalty data for programmatic calculations
-- ─────────────────────────────────────────────

create table if not exists public.kg_penalties (
  id                    serial primary key,
  law_key               text not null,
  violation_type        text not null,          -- 'late_filing' | 'non_registration' | 'non_payment' | 'non_disclosure'
  description_en        text not null,
  description_hi        text,
  penalty_type          text not null,          -- 'fixed' | 'per_day' | 'percentage' | 'compound_interest' | 'range'
  penalty_amount_inr    numeric,                -- fixed amount or per-day amount
  penalty_percentage    numeric,                -- % of tax/amount due
  penalty_min_inr       numeric,                -- for range type
  penalty_max_inr       numeric,                -- for range type
  interest_rate_annual  numeric,                -- annual % interest (e.g. 18 for 18%)
  compounding           boolean default false,
  imprisonment_months   int,                    -- max imprisonment if applicable
  authority             text,
  notes_en              text,
  notes_hi              text
);

insert into public.kg_penalties
  (law_key, violation_type, description_en, description_hi, penalty_type, penalty_amount_inr, penalty_percentage, penalty_min_inr, penalty_max_inr, interest_rate_annual, compounding, imprisonment_months, authority, notes_en, notes_hi)
values
  -- GST Penalties
  ('GST', 'late_filing',
   'Late fee for filing GSTR-1 or GSTR-3B after due date',
   'GSTR-1 या GSTR-3B देरी से भरने पर लेट फीस',
   'per_day', 50, null, null, 5000, null, false, null, 'CBIC',
   '₹50/day (₹25 CGST + ₹25 SGST). Capped at ₹5,000 per return. NIL returns attract ₹20/day.',
   '₹50/दिन (₹25 CGST + ₹25 SGST), अधिकतम ₹5,000 प्रति रिटर्न। NIL रिटर्न पर ₹20/दिन।'),

  ('GST', 'non_registration',
   'Penalty for operating without GST registration when required',
   'आवश्यक होने पर GST पंजीकरण के बिना व्यापार करना',
   'range', null, 10, 10000, null, null, false, null, 'CBIC',
   'Higher of ₹10,000 or 10% of tax evaded. If deliberate tax evasion: 100% of tax evaded.',
   '₹10,000 या चोरी किए गए टैक्स का 10% — जो भी अधिक हो। जानबूझकर चोरी पर 100%।'),

  ('GST', 'non_payment',
   'Interest on delayed payment of GST',
   'GST का भुगतान देरी से करने पर ब्याज',
   'percentage', null, null, null, null, 18, false, null, 'CBIC',
   '18% per annum on outstanding GST amount from due date to actual payment date.',
   'देय तिथि से भुगतान तिथि तक बकाया GST पर 18% प्रतिवर्ष ब्याज।'),

  ('GST', 'fraud',
   'Penalty for fraud, suppression of facts, or deliberate misstatement',
   'धोखाधड़ी, तथ्य छुपाने पर जुर्माना',
   'percentage', null, 100, 10000, null, null, false, 60, 'CBIC',
   '100% of tax evaded, minimum ₹10,000. Imprisonment up to 5 years for tax evaded above ₹5Cr.',
   'चोरी किए गए टैक्स का 100%, न्यूनतम ₹10,000। ₹5Cr से अधिक की चोरी पर 5 साल तक की जेल।'),

  -- Income Tax Penalties
  ('INCOME_TAX', 'late_filing',
   'Late fee for filing ITR after due date (Section 234F)',
   'निर्धारित तिथि के बाद ITR भरने पर जुर्माना (धारा 234F)',
   'fixed', 5000, null, null, null, null, false, null, 'CBDT',
   '₹5,000 if filed after due date. Reduced to ₹1,000 if total income does not exceed ₹5 lakh.',
   'देय तिथि के बाद भरने पर ₹5,000। अगर आय ₹5 लाख से कम है तो ₹1,000।'),

  ('INCOME_TAX', 'non_payment',
   'Interest for late payment of advance tax (Section 234B/234C)',
   'एडवांस टैक्स देरी से भरने पर ब्याज (धारा 234B/234C)',
   'percentage', null, null, null, null, 12, false, null, 'CBDT',
   '1% per month (12% p.a.) on unpaid advance tax amount under Sections 234B and 234C.',
   'धारा 234B और 234C के तहत बकाया एडवांस टैक्स पर 1% प्रति माह (12% वार्षिक)।'),

  ('INCOME_TAX', 'tds_non_deduction',
   'Penalty for failure to deduct TDS (Section 201)',
   'TDS न काटने पर जुर्माना (धारा 201)',
   'percentage', null, null, null, null, 12, false, null, 'CBDT',
   '1% interest per month from date payment was made to date TDS is actually deducted.',
   'भुगतान की तिथि से TDS काटने की तिथि तक 1% प्रति माह ब्याज।'),

  ('INCOME_TAX', 'tds_non_deposit',
   'Penalty for failure to deposit TDS after deduction (Section 201)',
   'TDS काटकर जमा न करने पर जुर्माना (धारा 201)',
   'percentage', null, null, null, null, 18, false, null, 'CBDT',
   '1.5% per month (18% p.a.) from date TDS was deducted to date of actual deposit.',
   'TDS काटने की तिथि से जमा करने की तिथि तक 1.5% प्रति माह (18% वार्षिक)।'),

  -- MSMED Act Penalties
  ('MSMED', 'overdue_payment',
   'Compound interest on delayed payment to MSME vendors beyond 45 days',
   'MSME विक्रेताओं को 45 दिन से अधिक देरी से भुगतान पर चक्रवृद्धि ब्याज',
   'compound_interest', null, null, null, null, null, true, null, 'MSME Ministry',
   'Interest at 3x the bank rate (compounded monthly) on the overdue amount. Current bank rate ~6.5%, so effective rate ~19.5% p.a. Not tax-deductible for the buyer.',
   'बकाया राशि पर बैंक दर का 3 गुना (मासिक चक्रवृद्धि) ब्याज। यह ब्याज खरीदार के लिए टैक्स में कटौती योग्य नहीं है।'),

  ('MSMED', 'form_i_non_filing',
   'Penalty for not filing MSMED Form I within due date',
   'MSMED Form I समय पर न भरने पर जुर्माना',
   'range', null, null, 10000, 1000000, null, false, null, 'MSME Ministry / MSEFC',
   'Fine of ₹10,000 to ₹10,00,000 under Section 27 of MSMED Act. Micro/Small enterprises cannot waive or reduce this interest contractually.',
   'MSMED Act की धारा 27 के तहत ₹10,000 से ₹10,00,000 तक जुर्माना। यह ब्याज अनुबंध से माफ नहीं हो सकता।'),

  -- FSSAI Penalties
  ('FSSAI', 'non_registration',
   'Penalty for operating a food business without FSSAI registration/licence',
   'FSSAI पंजीकरण/लाइसेंस के बिना खाद्य व्यवसाय चलाने पर जुर्माना',
   'fixed', 500000, null, null, null, null, false, 6, 'FSSAI',
   'Fine up to ₹5 lakh and/or imprisonment up to 6 months for operating without FSSAI registration.',
   'FSSAI पंजीकरण के बिना व्यापार पर ₹5 लाख तक जुर्माना और/या 6 महीने तक की जेल।'),

  ('FSSAI', 'unsafe_food',
   'Penalty for selling adulterated or unsafe food',
   'मिलावटी या असुरक्षित खाद्य बेचने पर जुर्माना',
   'range', null, null, 100000, 1000000, null, false, 72, 'FSSAI',
   '₹1L–₹10L fine and up to 6 years imprisonment depending on severity. Death caused by unsafe food: life imprisonment.',
   '₹1 लाख–₹10 लाख जुर्माना और 6 साल तक की जेल। मृत्यु होने पर आजीवन कारावास।'),

  -- PF/ESI Penalties
  ('SS_CODE', 'pf_non_deposit',
   'Penalty for late or non-deposit of PF contributions',
   'PF योगदान देरी से या न जमा करने पर दंड',
   'percentage', null, null, null, null, 12, false, null, 'EPFO',
   'Interest at 12% p.a. on delayed deposits. Damages from 5%–25% p.a. depending on delay period. Criminal prosecution possible for willful default.',
   '12% वार्षिक ब्याज + देरी अवधि के अनुसार 5%–25% तक हर्जाना। जानबूझकर चूक पर आपराधिक मुकदमा।'),

  ('SS_CODE', 'esi_non_deposit',
   'Penalty for late or non-deposit of ESI contributions',
   'ESI योगदान देरी से या न जमा करने पर दंड',
   'percentage', null, null, null, null, 12, false, 12, 'ESIC',
   '12% per annum interest plus damages. Prosecution under Section 85 of ESI Act for repeated defaults.',
   '12% वार्षिक ब्याज और हर्जाना। बार-बार चूक पर ESI Act की धारा 85 के तहत मुकदमा।'),

  -- Shops & Establishment
  ('SHOPS_ACT', 'non_registration',
   'Operating a shop or commercial establishment without registration',
   'पंजीकरण के बिना दुकान या व्यावसायिक प्रतिष्ठान चलाना',
   'range', null, null, 1000, 50000, null, false, null, 'State Labour Dept',
   'Penalty varies by state: typically ₹1,000–₹50,000 for first offence. Higher for repeat offences.',
   'राज्य के अनुसार भिन्न: पहली बार ₹1,000–₹50,000। बार-बार उल्लंघन पर अधिक।');


-- ─────────────────────────────────────────────
-- 3. Compliance Actions Table
--    "Here is how to actually do it" — portal, docs, fee, time
-- ─────────────────────────────────────────────

create table if not exists public.kg_compliance_actions (
  id               serial primary key,
  result_key       text not null,               -- matches kg_result_types.resultkey
  law_key          text not null,
  action_title_en  text not null,
  action_title_hi  text,
  portal_url       text,
  portal_name      text,
  fee_inr          numeric,                     -- registration/application fee (0 = free)
  fee_notes_en     text,
  documents_en     text,                        -- comma-separated list of required docs
  documents_hi     text,
  processing_days  int,                         -- typical approval time
  validity_years   numeric,                     -- how long before renewal (null = one-time)
  renewal_required boolean default false,
  steps_en         text,                        -- numbered steps as plain text
  steps_hi         text,
  helpline         text,
  notes_en         text,
  notes_hi         text
);

insert into public.kg_compliance_actions
  (result_key, law_key, action_title_en, action_title_hi, portal_url, portal_name, fee_inr, fee_notes_en, documents_en, documents_hi, processing_days, validity_years, renewal_required, steps_en, steps_hi, helpline, notes_en, notes_hi)
values
  ('GST_REG_REQUIRED', 'GST',
   'Register under GST on GST portal',
   'GST पोर्टल पर GST में रजिस्ट्रेशन करें',
   'https://www.gst.gov.in', 'GST Portal (gst.gov.in)',
   0, 'GST registration is free of charge.',
   'PAN card, Aadhaar card, business address proof, bank account statement/cancelled cheque, passport-size photograph, proof of constitution (Partnership deed / MOA / Certificate of incorporation)',
   'PAN कार्ड, आधार कार्ड, व्यापार के पते का प्रमाण, बैंक स्टेटमेंट/कैंसिल्ड चेक, पासपोर्ट साइज फोटो, व्यापार संरचना का प्रमाण',
   7, null, false,
   '1. Go to gst.gov.in > Register Now. 2. Fill Part-A: PAN, mobile, email. 3. Verify OTP sent to mobile and email. 4. Fill Part-B: business details, address, bank account, upload documents. 5. Submit. GSTIN is issued within 7 working days if documents are correct.',
   '1. gst.gov.in पर जाएं > Register Now। 2. Part-A भरें: PAN, मोबाइल, ईमेल। 3. OTP वेरीफाई करें। 4. Part-B: बिज़नेस विवरण, पता, बैंक, दस्तावेज़ अपलोड करें। 5. सबमिट करें। 7 कार्यदिवसों में GSTIN मिल जाता है।',
   '1800-103-4786', null, null),

  ('GST_COMPOSITION_ELIGIBLE', 'GST',
   'Opt into GST Composition Scheme (pay flat 1–2% instead of full GST)',
   'GST कम्पोजीशन स्कीम चुनें (पूरे GST की बजाय 1–2% फ्लैट दें)',
   'https://www.gst.gov.in', 'GST Portal (gst.gov.in)',
   0, 'Free — opt-in during registration or via Form GST CMP-02.',
   'Existing GSTIN, Form GST CMP-02 submission',
   'मौजूदा GSTIN, Form GST CMP-02',
   1, null, false,
   '1. Log in to gst.gov.in. 2. Go to Services > Registration > Application to Opt for Composition Levy. 3. File Form CMP-02 before the start of the financial year (or at time of registration).',
   '1. gst.gov.in पर लॉग इन करें। 2. Services > Registration > Composition Levy चुनें। 3. वित्त वर्ष की शुरुआत से पहले CMP-02 भरें।',
   '1800-103-4786', 'Eligible if turnover ≤ ₹1.5 Crore (₹75L for some special category states). Cannot sell inter-state or supply exempt goods.', null),

  ('FSSAI_BASIC_REG', 'FSSAI',
   'Get basic FSSAI registration (for small food businesses)',
   'बेसिक FSSAI रजिस्ट्रेशन लें (छोटे खाद्य व्यवसायों के लिए)',
   'https://foscos.fssai.gov.in', 'FoSCoS Portal (foscos.fssai.gov.in)',
   100, '₹100 per year.',
   'PAN / Aadhaar, passport-size photo, business address proof, list of food categories to be handled',
   'PAN/आधार, पासपोर्ट साइज फोटो, पते का प्रमाण, खाद्य श्रेणियों की सूची',
   7, 1, true,
   '1. Go to foscos.fssai.gov.in. 2. Click Apply for Licence/Registration. 3. Select Basic Registration. 4. Fill in business details and food categories. 5. Upload documents and pay ₹100. 6. Registration certificate issued within 7 days.',
   '1. foscos.fssai.gov.in पर जाएं। 2. Basic Registration चुनें। 3. व्यापार विवरण और खाद्य श्रेणियां भरें। 4. दस्तावेज़ अपलोड करें और ₹100 का भुगतान करें। 5. 7 दिन में सर्टिफिकेट मिलेगा।',
   '1800-112-100', 'Required for food businesses with turnover below ₹12 lakh/year. Renew annually.', null),

  ('FSSAI_STATE_LICENSE', 'FSSAI',
   'Get FSSAI State Licence (for medium food businesses)',
   'FSSAI स्टेट लाइसेंस लें (मध्यम खाद्य व्यवसायों के लिए)',
   'https://foscos.fssai.gov.in', 'FoSCoS Portal (foscos.fssai.gov.in)',
   2000, '₹2,000–₹5,000 per year depending on category.',
   'PAN, business registration proof, premises ownership/rent agreement, water test report, list of food products, equipment list, layout plan',
   'PAN, व्यापार पंजीकरण, परिसर का प्रमाण, पानी परीक्षण रिपोर्ट, खाद्य उत्पाद सूची, उपकरण सूची, लेआउट प्लान',
   30, 5, true,
   '1. Go to foscos.fssai.gov.in. 2. Select State Licence. 3. Fill Form B with full business details. 4. Upload all documents. 5. Pay fee. 6. Inspector may visit premises. 7. Licence issued within 30 days.',
   '1. foscos.fssai.gov.in पर जाएं। 2. State Licence चुनें। 3. Form B भरें। 4. सभी दस्तावेज़ अपलोड करें। 5. शुल्क भुगतान करें। 6. निरीक्षक परिसर का दौरा कर सकते हैं। 7. 30 दिन में लाइसेंस मिलेगा।',
   '1800-112-100', 'Required for turnover ₹12L–₹20Cr, or manufacturers, transporters, wholesalers.', null),

  ('UDYAM_REG_RECOMMENDED', 'MSMED',
   'Register on Udyam Portal (free MSME certificate)',
   'Udyam पोर्टल पर पंजीकरण करें (मुफ्त MSME प्रमाण पत्र)',
   'https://udyamregistration.gov.in', 'Udyam Registration Portal',
   0, 'Completely free. No intermediary needed.',
   'Aadhaar of proprietor/partner/director, PAN of business entity, GST number (if registered)',
   'मालिक/साझेदार/निदेशक का आधार, व्यापार का PAN, GST नंबर (यदि हो)',
   1, null, false,
   '1. Go to udyamregistration.gov.in. 2. Click "For New Entrepreneurs". 3. Enter Aadhaar number and validate with OTP. 4. Fill business details (NIC code, investment, turnover). 5. Submit. Udyam Certificate generated instantly.',
   '1. udyamregistration.gov.in पर जाएं। 2. नए उद्यमियों के लिए विकल्प चुनें। 3. आधार नंबर दर्ज करें और OTP से सत्यापित करें। 4. व्यापार विवरण भरें। 5. सबमिट करें। Udyam प्रमाण पत्र तुरंत मिलेगा।',
   '18001800763', 'Udyam registration is needed to claim MSMED Act protections, government tenders, priority sector lending, and state scheme benefits.', null),

  ('SHOPS_REG_REQUIRED', 'SHOPS_ACT',
   'Register your shop/establishment with the state labour department',
   'राज्य श्रम विभाग में दुकान/प्रतिष्ठान का पंजीकरण करें',
   'https://shramsuvidha.gov.in', 'Shram Suvidha Portal (shramsuvidha.gov.in)',
   500, 'Fee varies by state and number of employees: typically ₹250–₹2,000.',
   'Business address proof, identity proof of owner, list of employees with designation and salary, bank account details, rental/ownership deed for premises',
   'पते का प्रमाण, मालिक की पहचान, कर्मचारियों की सूची, बैंक विवरण, परिसर का किराया/स्वामित्व दस्तावेज़',
   15, 5, true,
   '1. Visit your state labour department portal or Shram Suvidha at shramsuvidha.gov.in. 2. Register as employer. 3. Fill establishment details and employee list. 4. Pay fee online. 5. Registration certificate issued within 15 days.',
   '1. अपने राज्य के श्रम विभाग पोर्टल या shramsuvidha.gov.in पर जाएं। 2. नियोक्ता के रूप में पंजीकरण करें। 3. प्रतिष्ठान विवरण और कर्मचारी सूची भरें। 4. ऑनलाइन शुल्क भुगतान करें। 5. 15 दिन में प्रमाण पत्र मिलेगा।',
   null, 'Required for any shop, hotel, restaurant, commercial establishment, or office. Mandatory within 30 days of opening.', null),

  ('PF_REGISTRATION_REQUIRED', 'SS_CODE',
   'Register your establishment under EPFO (Employee Provident Fund)',
   'EPFO में अपने प्रतिष्ठान का पंजीकरण करें',
   'https://unifiedportal-emp.epfindia.gov.in', 'EPFO Employer Portal',
   0, 'Registration is free.',
   'PAN of establishment, business registration proof, bank account details, list of employees with salaries, DSC of employer',
   'प्रतिष्ठान का PAN, व्यापार पंजीकरण, बैंक विवरण, कर्मचारी और वेतन सूची, नियोक्ता का DSC',
   7, null, false,
   '1. Go to unifiedportal-emp.epfindia.gov.in. 2. Click Establishment Registration. 3. Fill employer details and employee count. 4. Upload documents and verify with DSC. 5. PF code allotted within 3–7 days.',
   '1. unifiedportal-emp.epfindia.gov.in पर जाएं। 2. Establishment Registration चुनें। 3. नियोक्ता विवरण और कर्मचारी संख्या भरें। 4. दस्तावेज़ अपलोड करें। 5. 3–7 दिन में PF कोड मिलेगा।',
   '1800-118-005', 'Mandatory for establishments with 20 or more employees. Contribution: 12% of basic salary from both employer and employee.', null),

  ('ESI_REGISTRATION_REQUIRED', 'SS_CODE',
   'Register your establishment under ESIC (Employee State Insurance)',
   'ESIC में अपने प्रतिष्ठान का पंजीकरण करें',
   'https://www.esic.in', 'ESIC Portal (esic.in)',
   0, 'Registration is free.',
   'PAN, establishment registration certificate, list of employees earning up to ₹21,000/month, bank details',
   'PAN, प्रतिष्ठान पंजीकरण, ₹21,000/माह तक वेतन पाने वाले कर्मचारियों की सूची, बैंक विवरण',
   7, null, false,
   '1. Go to esic.in. 2. Click Employer Login > New Employer Registration. 3. Fill establishment details. 4. Add all eligible employees. 5. Get ESI code number and start deducting contributions.',
   '1. esic.in पर जाएं। 2. नए नियोक्ता पंजीकरण पर क्लिक करें। 3. प्रतिष्ठान विवरण भरें। 4. सभी पात्र कर्मचारी जोड़ें। 5. ESI कोड मिलेगा और योगदान काटना शुरू करें।',
   '1800-11-2526', 'Mandatory for establishments with 10+ employees. Employer contributes 3.25%, employee 0.75% of wages.', null);


-- ─────────────────────────────────────────────
-- Indexes
-- ─────────────────────────────────────────────

create index if not exists kg_compliance_calendar_law_key_idx  on public.kg_compliance_calendar(law_key);
create index if not exists kg_compliance_calendar_frequency_idx on public.kg_compliance_calendar(frequency);
create index if not exists kg_compliance_calendar_due_day_idx  on public.kg_compliance_calendar(due_day);
create index if not exists kg_penalties_law_key_idx            on public.kg_penalties(law_key);
create index if not exists kg_penalties_violation_idx          on public.kg_penalties(law_key, violation_type);
create index if not exists kg_compliance_actions_result_key_idx on public.kg_compliance_actions(result_key);
create index if not exists kg_compliance_actions_law_key_idx   on public.kg_compliance_actions(law_key);
