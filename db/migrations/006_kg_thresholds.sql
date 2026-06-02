-- 006_kg_thresholds.sql
-- Tax and compliance registration thresholds for India
-- These change with Budget / GST Council notifications — update here when they do.
-- Run in Supabase SQL Editor AFTER 005_reminders.sql

create table if not exists public.kg_thresholds (
  threshold_key   text primary key,
  law_key         text not null,          -- 'GST' | 'INCOME_TAX' | 'MSMED' | 'FSSAI' etc.
  description_en  text not null,
  description_hi  text,
  value_inr       numeric not null,       -- threshold amount in INR
  applies_to      text,                   -- who this threshold applies to
  effective_from  text,                   -- 'YYYY-MM-DD' when this value became effective
  source_url      text,
  notes_en        text
);

insert into public.kg_thresholds
  (threshold_key, law_key, description_en, description_hi, value_inr, applies_to, effective_from, source_url, notes_en)
values
  -- GST registration thresholds
  ('GST_REG_GOODS',       'GST', 'GST registration threshold for goods suppliers',
   'वस्तु आपूर्तिकर्ताओं के लिए GST पंजीकरण सीमा',
   4000000, 'Businesses supplying goods (normal category states)',
   '2019-04-01', 'https://www.gst.gov.in', '₹40 lakh for normal states. Special category states: ₹20 lakh.'),

  ('GST_REG_SERVICES',    'GST', 'GST registration threshold for service providers',
   'सेवा प्रदाताओं के लिए GST पंजीकरण सीमा',
   2000000, 'Businesses providing services',
   '2019-04-01', 'https://www.gst.gov.in', '₹20 lakh for normal states. Special category states: ₹10 lakh.'),

  ('GST_COMPOSITION_MAX', 'GST', 'Maximum turnover for GST Composition Scheme',
   'GST कम्पोजीशन स्कीम की अधिकतम टर्नओवर सीमा',
   15000000, 'Businesses eligible for composition scheme',
   '2019-04-01', 'https://www.gst.gov.in', '₹1.5 crore. Special category states: ₹75 lakh.'),

  -- Income Tax thresholds
  ('TDS_SALARY_NEW_REGIME', 'INCOME_TAX', 'Minimum salary for TDS deduction — new tax regime',
   'नई टैक्स व्यवस्था में TDS कटौती की न्यूनतम वेतन सीमा',
   700000, 'Salaried employees under new tax regime (default FY 2024-25 onwards)',
   '2023-04-01', 'https://www.incometax.gov.in',
   'Below ₹7L: zero tax liability under new regime with standard deduction of ₹50K. No TDS required.'),

  ('TDS_SALARY_OLD_REGIME', 'INCOME_TAX', 'Minimum salary for TDS deduction — old tax regime',
   'पुरानी टैक्स व्यवस्था में TDS कटौती की न्यूनतम वेतन सीमा',
   250000, 'Salaried employees who opt for old tax regime',
   '2014-07-10', 'https://www.incometax.gov.in', '₹2.5 lakh basic exemption under old regime.'),

  ('ADVANCE_TAX_MIN',     'INCOME_TAX', 'Minimum tax liability to trigger advance tax obligation',
   'एडवांस टैक्स दायित्व के लिए न्यूनतम कर देनदारी',
   10000, 'All taxpayers',
   '2014-07-10', 'https://www.incometax.gov.in', 'If estimated annual tax liability < ₹10,000, advance tax not required.'),

  ('ITR_AUDIT_BUSINESS',  'INCOME_TAX', 'Turnover threshold for mandatory tax audit — business',
   'व्यापार के लिए अनिवार्य टैक्स ऑडिट की टर्नओवर सीमा',
   10000000, 'Business taxpayers',
   '2021-04-01', 'https://www.incometax.gov.in',
   '₹1 crore for most businesses. ₹10 crore if cash transactions < 5% of total.'),

  ('ITR_AUDIT_PROFESSION', 'INCOME_TAX', 'Gross receipts threshold for mandatory tax audit — profession',
   'पेशे के लिए अनिवार्य टैक्स ऑडिट की सकल प्राप्ति सीमा',
   5000000, 'Professionals (doctors, lawyers, CAs, etc.)',
   '2021-04-01', 'https://www.incometax.gov.in', '₹50 lakh gross receipts triggers Section 44AB audit.'),

  -- MSMED thresholds
  ('MSME_MICRO_INV',      'MSMED', 'Investment ceiling for Micro enterprise classification',
   'सूक्ष्म उद्यम वर्गीकरण के लिए निवेश सीमा',
   10000000, 'Manufacturing and service businesses',
   '2020-07-01', 'https://udyamregistration.gov.in',
   '₹1 crore investment AND ₹5 crore turnover. Both must qualify.'),

  ('MSME_SMALL_INV',      'MSMED', 'Investment ceiling for Small enterprise classification',
   'लघु उद्यम वर्गीकरण के लिए निवेश सीमा',
   100000000, 'Manufacturing and service businesses',
   '2020-07-01', 'https://udyamregistration.gov.in',
   '₹10 crore investment AND ₹50 crore turnover. Both must qualify.'),

  ('MSME_MEDIUM_INV',     'MSMED', 'Investment ceiling for Medium enterprise classification',
   'मध्यम उद्यम वर्गीकरण के लिए निवेश सीमा',
   500000000, 'Manufacturing and service businesses',
   '2020-07-01', 'https://udyamregistration.gov.in',
   '₹50 crore investment AND ₹250 crore turnover. Both must qualify.'),

  -- FSSAI thresholds
  ('FSSAI_BASIC_MAX',     'FSSAI', 'Maximum annual turnover for FSSAI Basic Registration',
   'FSSAI बेसिक रजिस्ट्रेशन की अधिकतम वार्षिक टर्नओवर सीमा',
   1200000, 'Food businesses',
   '2011-08-05', 'https://foscos.fssai.gov.in',
   'Below ₹12 lakh: Basic Registration (₹100/yr). Above: State or Central licence required.'),

  -- PF/ESI thresholds
  ('PF_EMPLOYEE_COUNT',   'SS_CODE', 'Minimum employee count for mandatory PF registration',
   'अनिवार्य PF पंजीकरण के लिए न्यूनतम कर्मचारी संख्या',
   20, 'All establishments',
   '1952-11-19', 'https://unifiedportal-emp.epfindia.gov.in',
   '20 or more employees triggers mandatory EPFO registration.'),

  ('ESI_EMPLOYEE_COUNT',  'SS_CODE', 'Minimum employee count for mandatory ESI registration',
   'अनिवार्य ESI पंजीकरण के लिए न्यूनतम कर्मचारी संख्या',
   10, 'All establishments',
   '1948-04-19', 'https://www.esic.in',
   '10 or more employees (wages ≤ ₹21,000/month) triggers mandatory ESIC registration.'),

  ('ESI_WAGE_CEILING',    'SS_CODE', 'Maximum monthly wage for ESI coverage of employees',
   'ESI कवरेज के लिए अधिकतम मासिक वेतन सीमा',
   21000, 'Employees',
   '2017-01-01', 'https://www.esic.in',
   'Employees earning ≤ ₹21,000/month are covered. Above this: optional.');


create index if not exists kg_thresholds_law_key_idx on public.kg_thresholds(law_key);
