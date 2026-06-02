-- Migration 009: IEC (Import Export Code) — penalties + compliance actions
-- Required for any business doing international trade (import or export)
-- Issued by DGFT (Director General of Foreign Trade), Ministry of Commerce
-- Run AFTER 008_kg_v1_laws.sql

-- ─────────────────────────────────────────────
-- Penalties
-- ─────────────────────────────────────────────

insert into public.kg_penalties
  (law_key, violation_type, description_en, description_hi, penalty_type,
   penalty_amount_inr, penalty_percentage, penalty_min_inr, penalty_max_inr,
   interest_rate_annual, compounding, imprisonment_months, authority, notes_en, notes_hi)
values

  ('IEC', 'no_iec',
   'Importing or exporting goods without a valid IEC (Import Export Code)',
   'IEC (आयात निर्यात कोड) के बिना आयात या निर्यात करना',
   'range', null, null, 10000, 500000, null, false, null, 'DGFT / Customs',
   'Penalty up to ₹5 lakh under FTDR Act. Customs can seize goods. Shipment held at port until IEC is produced.',
   'FTDR Act के तहत ₹5 लाख तक जुर्माना। सीमा शुल्क विभाग माल जब्त कर सकता है। IEC दिखाने तक शिपमेंट पोर्ट पर रुकेगी।'),

  ('IEC', 'expired_iec',
   'Using an IEC that has not been updated/renewed in the last financial year',
   'IEC को पिछले वित्त वर्ष में अपडेट/नवीनीकरण न करना',
   'fixed', 0, null, null, null, null, false, null, 'DGFT',
   'IEC gets automatically deactivated if not updated annually (April–June window). Reactivation requires filing update on DGFT portal. No direct fine but operations are blocked.',
   'IEC सालाना अपडेट न होने पर अपने आप निष्क्रिय हो जाता है (अप्रैल–जून में अपडेट करें)। DGFT पोर्टल पर अपडेट दाखिल करने पर पुनः सक्रिय होगा।');


-- ─────────────────────────────────────────────
-- Compliance Actions — How to get IEC
-- ─────────────────────────────────────────────

insert into public.kg_compliance_actions
  (result_key, law_key, action_title_en, action_title_hi, portal_url, portal_name,
   fee_inr, fee_notes_en, documents_en, documents_hi, processing_days,
   validity_years, renewal_required, steps_en, steps_hi, helpline, notes_en, notes_hi)
values

  ('IEC_REQUIRED', 'IEC',
   'Apply for IEC (Import Export Code) on DGFT portal',
   'DGFT पोर्टल पर IEC (आयात निर्यात कोड) के लिए आवेदन करें',
   'https://www.dgft.gov.in', 'DGFT Portal (dgft.gov.in)',
   500, '₹500 one-time government fee. No annual renewal fee.',
   'PAN card, Aadhaar card, cancelled cheque or bank certificate (with IFSC and account number), business address proof, digital signature (Class 2 or 3 DSC) or Aadhaar OTP',
   'PAN कार्ड, आधार कार्ड, कैंसिल्ड चेक या बैंक सर्टिफिकेट (IFSC सहित), व्यापार पते का प्रमाण, डिजिटल हस्ताक्षर (Class 2/3 DSC) या आधार OTP',
   2, null, false,
   '1. Go to dgft.gov.in and register/login with your PAN. 2. Click Services > IEC > Apply for IEC. 3. Fill in all business details (name, address, bank account). 4. Upload PAN, cancelled cheque, and address proof. 5. Pay ₹500 fee online. 6. Authenticate with Aadhaar OTP or DSC. 7. IEC is issued immediately (e-IEC) or within 2 working days.',
   '1. dgft.gov.in पर PAN से रजिस्टर/लॉगिन करें। 2. Services > IEC > Apply for IEC पर जाएं। 3. सभी व्यापार विवरण भरें (नाम, पता, बैंक खाता)। 4. PAN, कैंसिल्ड चेक और पते का प्रमाण अपलोड करें। 5. ₹500 शुल्क ऑनलाइन भुगतान करें। 6. आधार OTP या DSC से प्रमाणित करें। 7. IEC तुरंत (e-IEC) या 2 कार्यदिवसों में जारी होगा।',
   '1800-111-550',
   'IEC is mandatory for any business importing or exporting goods. It is a 10-digit code linked to your PAN. One IEC per PAN — covers all branches. Must be updated annually (April–June) to stay active.',
   'किसी भी वस्तु के आयात या निर्यात के लिए IEC अनिवार्य है। यह आपके PAN से जुड़ा 10 अंकों का कोड है। प्रति PAN एक IEC — सभी शाखाओं के लिए। सक्रिय रखने के लिए सालाना (अप्रैल–जून) अपडेट करें।');


-- ─────────────────────────────────────────────
-- Compliance Calendar — IEC annual update reminder
-- ─────────────────────────────────────────────

insert into public.kg_compliance_calendar
  (law_key, filing_name, filing_name_hi, frequency, due_day, due_month,
   quarter_offset_month, applies_to, turnover_min_lakh, turnover_max_lakh,
   taxpayer_type, penalty_per_day_inr, portal_url, notes_en, notes_hi)
values

  ('IEC', 'IEC Annual Update (Apr–Jun)', 'IEC वार्षिक अपडेट (अप्रैल–जून)', 'annual', 30, 6,
   null, 'All IEC holders — businesses engaged in import or export', null, null, 'all',
   null, 'https://www.dgft.gov.in',
   'IEC must be updated every year between April 1 and June 30 on DGFT portal. Missing the update deactivates the IEC. No fee — just confirm/update your business details.',
   'IEC को हर साल 1 अप्रैल से 30 जून के बीच DGFT पोर्टल पर अपडेट करना अनिवार्य है। अपडेट न होने पर IEC निष्क्रिय हो जाता है। कोई शुल्क नहीं — केवल व्यापार विवरण की पुष्टि करें।');


-- Indexes
create index if not exists kg_pen_iec_idx  on public.kg_penalties(law_key)          where law_key = 'IEC';
create index if not exists kg_act_iec_idx  on public.kg_compliance_actions(law_key) where law_key = 'IEC';
create index if not exists kg_cal_iec_idx  on public.kg_compliance_calendar(law_key) where law_key = 'IEC';
