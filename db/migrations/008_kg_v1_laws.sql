-- Migration 008: KG V1 Priority Laws
-- Fills gaps for the 10 must-have laws:
-- GST, Income Tax+TDS, FSSAI, Udyam/MSMED, EPF+ESI, Shops Act (already covered)
-- NEW: Legal Metrology penalties+actions, DPDP penalties+actions,
--      Factories Act full (calendar+penalties+actions),
--      Income Tax compliance_actions (ITR+advance tax how-to),
--      FSSAI + Shops Act calendar renewal entries
-- Run AFTER 004_kg_extensions.sql

-- ─────────────────────────────────────────────
-- 1. INCOME TAX — Compliance Actions (missing from 004)
-- ─────────────────────────────────────────────

insert into public.kg_compliance_actions
  (result_key, law_key, action_title_en, action_title_hi, portal_url, portal_name,
   fee_inr, fee_notes_en, documents_en, documents_hi, processing_days,
   validity_years, renewal_required, steps_en, steps_hi, helpline, notes_en, notes_hi)
values

  ('ITR_FILING_REQUIRED', 'INCOME_TAX',
   'File Income Tax Return (ITR) on Income Tax Portal',
   'इनकम टैक्स पोर्टल पर ITR दाखिल करें',
   'https://www.incometax.gov.in', 'Income Tax e-Filing Portal',
   0, 'Filing ITR is free. Chartered Accountant fees are separate.',
   'PAN card, Form 16 (from employer), bank statements, TDS certificates (Form 26AS), details of income from all sources, investment proofs for deductions',
   'PAN कार्ड, Form 16, बैंक स्टेटमेंट, Form 26AS (TDS सर्टिफिकेट), सभी आय का विवरण, निवेश प्रमाण',
   null, null, false,
   '1. Log in at incometax.gov.in. 2. Go to e-File > Income Tax Returns > File ITR. 3. Select Assessment Year and ITR form (ITR-1 for salary/simple income, ITR-3/4 for business). 4. Pre-fill data from Form 26AS and AIS. 5. Verify all income, deductions, and TDS credits. 6. Pay any balance tax due. 7. Submit and e-verify using Aadhaar OTP or net banking.',
   '1. incometax.gov.in पर लॉग इन करें। 2. e-File > ITR File करें चुनें। 3. Assessment Year और ITR फॉर्म चुनें (ITR-1 वेतन के लिए, ITR-3/4 व्यापार के लिए)। 4. Form 26AS से डेटा प्री-फिल करें। 5. सभी आय, कटौतियां और TDS जांचें। 6. बकाया टैक्स भरें। 7. आधार OTP से e-verify करें।',
   '1800-103-0025',
   'Due date: 31 July for non-audit cases, 31 October for audit cases. Late filing fee ₹5,000 (₹1,000 if income ≤ ₹5L).',
   'गैर-ऑडिट मामलों के लिए 31 जुलाई, ऑडिट मामलों के लिए 31 अक्टूबर। देरी पर ₹5,000 जुर्माना (₹5L से कम आय पर ₹1,000)।'),

  ('ADVANCE_TAX_REQUIRED', 'INCOME_TAX',
   'Pay Advance Tax in quarterly instalments',
   'तिमाही किस्तों में एडवांस टैक्स जमा करें',
   'https://www.incometax.gov.in', 'Income Tax e-Filing Portal',
   0, 'No fee — only the tax amount is paid.',
   'PAN card, estimated income calculation, Challan ITNS 280',
   'PAN कार्ड, अनुमानित आय गणना, Challan ITNS 280',
   null, null, false,
   '1. Estimate your total income for the year. 2. Calculate tax on it using current slab rates. 3. Subtract any TDS already deducted. 4. If balance tax > ₹10,000, you must pay advance tax. 5. Go to incometax.gov.in > e-Pay Tax > Challan ITNS 280. 6. Select Advance Tax (code 100). 7. Pay: 15% by 15 Jun, 45% by 15 Sep, 75% by 15 Dec, 100% by 15 Mar.',
   '1. साल की कुल आय का अनुमान लगाएं। 2. मौजूदा स्लैब के अनुसार टैक्स निकालें। 3. पहले से कटे TDS को घटाएं। 4. अगर बकाया टैक्स ₹10,000 से ज़्यादा है तो एडवांस टैक्स देना ज़रूरी है। 5. incometax.gov.in > e-Pay Tax > Challan ITNS 280 पर जाएं। 6. Advance Tax (कोड 100) चुनें। 7. भुगतान करें: 15 जून तक 15%, 15 सितंबर तक 45%, 15 दिसंबर तक 75%, 15 मार्च तक 100%।',
   '1800-103-0025',
   'Mandatory if tax liability exceeds ₹10,000 for the year. Interest under 234B/234C applies if not paid on time.',
   'अगर वार्षिक टैक्स ₹10,000 से अधिक है तो अनिवार्य। समय पर न देने पर धारा 234B/234C के तहत ब्याज लगता है।');


-- ─────────────────────────────────────────────
-- 2. FSSAI — Compliance Calendar (renewal reminders)
-- ─────────────────────────────────────────────

insert into public.kg_compliance_calendar
  (law_key, filing_name, filing_name_hi, frequency, due_day, due_month,
   quarter_offset_month, applies_to, turnover_min_lakh, turnover_max_lakh,
   taxpayer_type, penalty_per_day_inr, portal_url, notes_en, notes_hi)
values

  ('FSSAI', 'FSSAI Basic Registration Renewal', 'FSSAI बेसिक रजिस्ट्रेशन नवीनीकरण', 'annual', 31, 3,
   null, 'Food businesses with basic FSSAI registration (turnover < ₹12L)', null, 12, 'all',
   null, 'https://foscos.fssai.gov.in',
   'Renew FSSAI basic registration before expiry (typically 31 March every year). Fee: ₹100.',
   'FSSAI बेसिक रजिस्ट्रेशन समाप्ति से पहले नवीनीकृत करें (आमतौर पर 31 मार्च)। शुल्क: ₹100।');


-- ─────────────────────────────────────────────
-- 3. SHOPS ACT — Compliance Calendar (renewal reminders)
-- ─────────────────────────────────────────────

insert into public.kg_compliance_calendar
  (law_key, filing_name, filing_name_hi, frequency, due_day, due_month,
   quarter_offset_month, applies_to, turnover_min_lakh, turnover_max_lakh,
   taxpayer_type, penalty_per_day_inr, portal_url, notes_en, notes_hi)
values

  ('SHOPS_ACT', 'Shops & Establishment Licence Renewal', 'दुकान एवं प्रतिष्ठान लाइसेंस नवीनीकरण', 'annual', 31, 12,
   null, 'All shops and commercial establishments (varies by state)', null, null, 'all',
   null, 'https://shramsuvidha.gov.in',
   'Renew Shops & Establishment registration by 31 December (varies by state — check local labour dept). Penalty for operating with expired registration.',
   'दुकान एवं प्रतिष्ठान पंजीकरण 31 दिसंबर तक नवीनीकृत करें (राज्य अनुसार अलग हो सकता है)। समय पर नवीनीकरण न होने पर जुर्माना।');


-- ─────────────────────────────────────────────
-- 4. FACTORIES ACT — Calendar + Penalties + Actions
-- ─────────────────────────────────────────────

-- Calendar
insert into public.kg_compliance_calendar
  (law_key, filing_name, filing_name_hi, frequency, due_day, due_month,
   quarter_offset_month, applies_to, turnover_min_lakh, turnover_max_lakh,
   taxpayer_type, penalty_per_day_inr, portal_url, notes_en, notes_hi)
values

  ('FACTORIES_ACT', 'Factory Annual Return (Form 21)', 'फैक्ट्री वार्षिक रिटर्न (Form 21)', 'annual', 31, 1,
   null, 'All registered factories under the Factories Act 1948', null, null, 'all',
   null, 'https://shramsuvidha.gov.in',
   'Submit Annual Return in Form 21 to the Chief Inspector of Factories by 31 January every year. Covers employment details, working hours, accidents, and production data.',
   'हर साल 31 जनवरी तक फैक्ट्री निरीक्षक को Form 21 में वार्षिक रिटर्न जमा करें। रोजगार, कार्य घंटे, दुर्घटनाएं और उत्पादन का विवरण देना होगा।'),

  ('FACTORIES_ACT', 'Factory Half-Yearly Return (Form 22)', 'फैक्ट्री अर्धवार्षिक रिटर्न (Form 22)', 'half_yearly', 31, 7,
   null, 'All registered factories under the Factories Act 1948', null, null, 'all',
   null, 'https://shramsuvidha.gov.in',
   'Submit Half-Yearly Return in Form 22: Jul 31 (for Jan–Jun) and Jan 31 (for Jul–Dec). Covers worker welfare and compliance status.',
   'Form 22 में अर्धवार्षिक रिटर्न जमा करें: 31 जुलाई (जनवरी–जून के लिए) और 31 जनवरी (जुलाई–दिसंबर के लिए)।');


-- Penalties
insert into public.kg_penalties
  (law_key, violation_type, description_en, description_hi, penalty_type,
   penalty_amount_inr, penalty_percentage, penalty_min_inr, penalty_max_inr,
   interest_rate_annual, compounding, imprisonment_months, authority, notes_en, notes_hi)
values

  ('FACTORIES_ACT', 'non_registration',
   'Operating a factory without registration or licence under Factories Act',
   'Factories Act के तहत पंजीकरण/लाइसेंस के बिना फैक्ट्री चलाना',
   'fixed', 100000, null, null, null, null, false, 18, 'State Factory Inspectorate',
   'Fine up to ₹1 lakh and/or imprisonment up to 18 months. Continuing offence: ₹1,000/day.',
   '₹1 लाख तक जुर्माना और/या 18 महीने तक कारावास। जारी उल्लंघन पर ₹1,000/दिन।'),

  ('FACTORIES_ACT', 'safety_violation',
   'Violation of safety provisions (dangerous machinery, hazardous processes)',
   'सुरक्षा प्रावधानों का उल्लंघन (खतरनाक मशीनरी, हानिकारक प्रक्रियाएं)',
   'range', null, null, 25000, 200000, null, false, 24, 'State Factory Inspectorate',
   '₹25,000–₹2 lakh fine and/or up to 2 years imprisonment. If accident causes death or serious injury, enhanced penalties apply.',
   '₹25,000–₹2 लाख जुर्माना और/या 2 साल तक कारावास। मृत्यु या गंभीर चोट पर और कड़ी सज़ा।'),

  ('FACTORIES_ACT', 'late_return',
   'Late submission of annual or half-yearly factory return',
   'वार्षिक या अर्धवार्षिक फैक्ट्री रिटर्न देरी से जमा करना',
   'range', null, null, 1000, 100000, null, false, null, 'State Factory Inspectorate',
   '₹1,000–₹1 lakh fine for failing to submit returns on time.',
   'समय पर रिटर्न न भरने पर ₹1,000–₹1 लाख जुर्माना।');


-- Actions
insert into public.kg_compliance_actions
  (result_key, law_key, action_title_en, action_title_hi, portal_url, portal_name,
   fee_inr, fee_notes_en, documents_en, documents_hi, processing_days,
   validity_years, renewal_required, steps_en, steps_hi, helpline, notes_en, notes_hi)
values

  ('FACTORY_REGISTRATION_REQUIRED', 'FACTORIES_ACT',
   'Register your factory under the Factories Act 1948',
   'Factories Act 1948 के तहत फैक्ट्री पंजीकरण करें',
   'https://shramsuvidha.gov.in', 'State Factory Inspector / Shram Suvidha',
   2500, 'Fee varies by state and factory size: typically ₹1,000–₹10,000 based on worker count.',
   'Site plan/layout of factory, list of machinery and their HP/KW ratings, list of workers, PAN, business registration (GST/Udyam), ownership/lease of premises, particulars of occupier and manager, power connection details',
   'फैक्ट्री का साइट प्लान/लेआउट, मशीनरी और उनकी HP/KW रेटिंग की सूची, कर्मचारी सूची, PAN, व्यापार पंजीकरण, परिसर का दस्तावेज़, मालिक और मैनेजर का विवरण, बिजली कनेक्शन विवरण',
   30, 1, true,
   '1. Contact your State Factory Inspectorate (each state has its own portal — check Shram Suvidha). 2. Submit Notice of Occupation (Form 2) at least 15 days before starting operations. 3. Apply for Factory Licence (Form 4) with all documents. 4. Pay fee based on worker count. 5. Factory Inspector may visit for inspection. 6. Licence issued within 30 days. Renew annually.',
   '1. अपने राज्य के फैक्ट्री निरीक्षालय से संपर्क करें (Shram Suvidha पर देखें)। 2. संचालन शुरू करने से कम से कम 15 दिन पहले Form 2 (Occupation Notice) जमा करें। 3. सभी दस्तावेज़ों के साथ Factory Licence (Form 4) के लिए आवेदन करें। 4. कर्मचारी संख्या के अनुसार शुल्क दें। 5. निरीक्षक निरीक्षण कर सकते हैं। 6. 30 दिन में लाइसेंस मिलेगा। सालाना नवीनीकरण करें।',
   null,
   'Applies to factories with 10+ workers using power, or 20+ workers without power. Occupier must display factory licence prominently at the premises.',
   '10+ कर्मचारी (बिजली सहित) या 20+ कर्मचारी (बिना बिजली) वाली फैक्ट्री पर लागू। लाइसेंस फैक्ट्री में स्पष्ट रूप से प्रदर्शित करना अनिवार्य है।');


-- ─────────────────────────────────────────────
-- 5. LEGAL METROLOGY — Penalties + Actions
-- ─────────────────────────────────────────────

insert into public.kg_penalties
  (law_key, violation_type, description_en, description_hi, penalty_type,
   penalty_amount_inr, penalty_percentage, penalty_min_inr, penalty_max_inr,
   interest_rate_annual, compounding, imprisonment_months, authority, notes_en, notes_hi)
values

  ('LEGAL_METROLOGY', 'unverified_weights',
   'Using weights or measures that have not been verified/stamped by Legal Metrology Inspector',
   'बिना जांचे-परखे (unstamped) बाट-माप का उपयोग करना',
   'range', null, null, 2000, 10000, null, false, 6, 'Legal Metrology Dept (State)',
   'Fine ₹2,000–₹10,000 for first offence. Up to 6 months imprisonment for repeat offence.',
   'पहली बार ₹2,000–₹10,000 जुर्माना। बार-बार उल्लंघन पर 6 महीने तक कारावास।'),

  ('LEGAL_METROLOGY', 'improper_label',
   'Selling pre-packaged goods without mandatory declarations (MRP, net quantity, manufacturer details)',
   'पैकेज्ड वस्तु पर MRP, नेट वजन, निर्माता विवरण न लगाना',
   'range', null, null, 2000, 25000, null, false, null, 'Legal Metrology Dept (State)',
   'Fine ₹2,000–₹25,000 under Packaged Commodities Rules 2011. Mandatory declarations: name of commodity, net quantity, MRP (inclusive of all taxes), manufacturer name and address, month and year of manufacture/packing.',
   'Packaged Commodities Rules 2011 के तहत ₹2,000–₹25,000 जुर्माना। अनिवार्य: वस्तु का नाम, नेट मात्रा, MRP (सभी कर सहित), निर्माता का नाम और पता, निर्माण/पैकिंग का माह और वर्ष।'),

  ('LEGAL_METROLOGY', 'fraudulent_weight',
   'Using incorrect, tampered, or fraudulent weights/measures to cheat customers',
   'ग्राहकों को ठगने के लिए गलत या छेड़छाड़ किए गए बाट-माप का उपयोग',
   'range', null, null, 25000, 50000, null, false, 12, 'Legal Metrology Dept (State)',
   '₹25,000–₹50,000 fine and/or up to 1 year imprisonment. Repeat offence: up to 2 years.',
   '₹25,000–₹50,000 जुर्माना और/या 1 साल तक कारावास। दोबारा उल्लंघन पर 2 साल तक।');


insert into public.kg_compliance_actions
  (result_key, law_key, action_title_en, action_title_hi, portal_url, portal_name,
   fee_inr, fee_notes_en, documents_en, documents_hi, processing_days,
   validity_years, renewal_required, steps_en, steps_hi, helpline, notes_en, notes_hi)
values

  ('LEGAL_METROLOGY_VERIFICATION', 'LEGAL_METROLOGY',
   'Get weighing machines and measures verified by Legal Metrology Inspector',
   'बाट-माप (तराजू, माप) की कानूनी मेट्रोलॉजी विभाग से जांच करवाएं',
   'https://legalmetrology.gov.in', 'Legal Metrology Dept (State)',
   200, 'Verification fee varies by type and number of instruments: ₹50–₹500 per instrument.',
   'List of all weighing/measuring instruments used in business, business address proof, identity proof of owner',
   'व्यापार में उपयोग सभी तराजू/माप उपकरणों की सूची, पते का प्रमाण, मालिक का पहचान प्रमाण',
   7, 1, true,
   '1. Contact your district Legal Metrology office (Controller of Legal Metrology). 2. Submit application with list of instruments. 3. Inspector will visit your premises on scheduled date. 4. All instruments are tested for accuracy and stamped/sealed. 5. Verification certificate issued. Renew every year.',
   '1. जिले के कानूनी मेट्रोलॉजी कार्यालय (Controller of Legal Metrology) से संपर्क करें। 2. उपकरणों की सूची के साथ आवेदन दें। 3. निरीक्षक तय तारीख पर परिसर में आएंगे। 4. सभी उपकरणों की जांच होगी और स्टैंप/सील लगेगी। 5. सत्यापन प्रमाण पत्र मिलेगा। हर साल नवीनीकरण करें।',
   null,
   'All businesses using weighing/measuring instruments commercially must get them verified annually. Packaged goods sellers must additionally comply with Packaged Commodities Rules 2011.',
   'व्यावसायिक रूप से बाट-माप उपयोग करने वाले सभी व्यवसायों को सालाना जांच कराना अनिवार्य है। पैकेज्ड वस्तु विक्रेताओं को Packaged Commodities Rules 2011 भी मानने होंगे।');


-- ─────────────────────────────────────────────
-- 6. DPDP (Digital Personal Data Protection Act 2023) — Penalties + Actions
-- ─────────────────────────────────────────────

insert into public.kg_penalties
  (law_key, violation_type, description_en, description_hi, penalty_type,
   penalty_amount_inr, penalty_percentage, penalty_min_inr, penalty_max_inr,
   interest_rate_annual, compounding, imprisonment_months, authority, notes_en, notes_hi)
values

  ('DPDP', 'data_breach',
   'Failure to implement reasonable security safeguards, resulting in data breach',
   'उचित सुरक्षा उपाय न करना जिससे डेटा चोरी/लीक हो',
   'fixed', 25000000000, null, null, null, null, false, null, 'Data Protection Board of India',
   'Fine up to ₹250 crore for failure to prevent data breach. For significant fiduciaries, fines can be higher.',
   'डेटा उल्लंघन को न रोकने पर ₹250 करोड़ तक जुर्माना।'),

  ('DPDP', 'consent_violation',
   'Processing personal data without valid consent or violating data principal rights',
   'वैध सहमति के बिना व्यक्तिगत डेटा प्रोसेस करना या डेटा अधिकारों का उल्लंघन',
   'fixed', 20000000000, null, null, null, null, false, null, 'Data Protection Board of India',
   'Fine up to ₹200 crore for processing without consent or not fulfilling data principal rights (access, correction, erasure).',
   'बिना सहमति के प्रोसेसिंग या डेटा अधिकार पूरे न करने पर ₹200 करोड़ तक जुर्माना।'),

  ('DPDP', 'notice_violation',
   'Failure to provide clear privacy notice to users before collecting data',
   'डेटा एकत्र करने से पहले स्पष्ट गोपनीयता सूचना न देना',
   'fixed', 5000000000, null, null, null, null, false, null, 'Data Protection Board of India',
   'Fine up to ₹50 crore for not giving proper notice before data collection. Small businesses and startups may get reduced penalties.',
   'डेटा एकत्र करने से पहले उचित सूचना न देने पर ₹50 करोड़ तक जुर्माना। छोटे व्यवसायों के लिए कम जुर्माना हो सकता है।');


insert into public.kg_compliance_actions
  (result_key, law_key, action_title_en, action_title_hi, portal_url, portal_name,
   fee_inr, fee_notes_en, documents_en, documents_hi, processing_days,
   validity_years, renewal_required, steps_en, steps_hi, helpline, notes_en, notes_hi)
values

  ('DPDP_COMPLIANCE_REQUIRED', 'DPDP',
   'Basic DPDP compliance: Privacy notice + Consent mechanism',
   'बुनियादी DPDP अनुपालन: गोपनीयता सूचना और सहमति तंत्र',
   'https://www.meity.gov.in', 'MeitY (Ministry of Electronics and IT)',
   0, 'No registration fee. Compliance is a process, not a licence.',
   'Privacy policy document, consent form/mechanism, data inventory (what data you collect and why), process for handling user requests (access/delete)',
   'गोपनीयता नीति दस्तावेज़, सहमति फॉर्म/तंत्र, डेटा सूची (क्या डेटा एकत्र करते हैं और क्यों), उपयोगकर्ता अनुरोध प्रबंधन प्रक्रिया',
   null, null, false,
   '1. Map all personal data you collect (customer name, phone, email, payment info). 2. Create a clear Privacy Notice explaining what data is collected, why, and for how long. 3. Get explicit consent before collecting data (checkbox, not pre-ticked). 4. Create a process for users to request their data or ask for deletion. 5. Ensure data is stored securely (encrypted databases, access controls). 6. Train staff on data handling. Note: DPDP Rules are still being notified — follow MeitY updates.',
   '1. आप जो व्यक्तिगत डेटा एकत्र करते हैं उसकी सूची बनाएं (नाम, फोन, ईमेल, भुगतान जानकारी)। 2. स्पष्ट गोपनीयता सूचना बनाएं — क्या डेटा, क्यों और कितने समय के लिए। 3. डेटा एकत्र करने से पहले स्पष्ट सहमति लें (चेकबॉक्स, पहले से चेक नहीं)। 4. उपयोगकर्ताओं को अपना डेटा देखने और हटाने की प्रक्रिया बनाएं। 5. डेटा सुरक्षित रखें (एन्क्रिप्टेड डेटाबेस, एक्सेस कंट्रोल)। 6. कर्मचारियों को डेटा हैंडलिंग का प्रशिक्षण दें। नोट: DPDP नियम अभी अधिसूचित हो रहे हैं — MeitY अपडेट देखते रहें।',
   null,
   'DPDP Act 2023 applies to any entity processing digital personal data in India. Rules not yet fully notified as of 2025 — implement basic privacy practices now to stay prepared.',
   'DPDP Act 2023 भारत में डिजिटल व्यक्तिगत डेटा प्रोसेस करने वाले सभी पर लागू होता है। नियम अभी पूरी तरह अधिसूचित नहीं हुए — अभी से बुनियादी गोपनीयता प्रथाएं अपनाएं।');


-- ─────────────────────────────────────────────
-- Indexes for new law_keys
-- ─────────────────────────────────────────────

create index if not exists kg_cal_factories_idx   on public.kg_compliance_calendar(law_key) where law_key = 'FACTORIES_ACT';
create index if not exists kg_cal_fssai_idx        on public.kg_compliance_calendar(law_key) where law_key = 'FSSAI';
create index if not exists kg_cal_shops_idx        on public.kg_compliance_calendar(law_key) where law_key = 'SHOPS_ACT';
create index if not exists kg_pen_factories_idx    on public.kg_penalties(law_key)            where law_key = 'FACTORIES_ACT';
create index if not exists kg_pen_legalmet_idx     on public.kg_penalties(law_key)            where law_key = 'LEGAL_METROLOGY';
create index if not exists kg_pen_dpdp_idx         on public.kg_penalties(law_key)            where law_key = 'DPDP';
create index if not exists kg_act_factories_idx    on public.kg_compliance_actions(law_key)   where law_key = 'FACTORIES_ACT';
create index if not exists kg_act_legalmet_idx     on public.kg_compliance_actions(law_key)   where law_key = 'LEGAL_METROLOGY';
create index if not exists kg_act_dpdp_idx         on public.kg_compliance_actions(law_key)   where law_key = 'DPDP';
create index if not exists kg_act_incometax_idx    on public.kg_compliance_actions(law_key)   where law_key = 'INCOME_TAX';
