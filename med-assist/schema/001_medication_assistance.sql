-- Medication assistance lookup: schema
-- Idempotent; safe to re-run. Postgres.
-- Compliance core: allowed_insurance drives the legal branch.
-- Manufacturer copay cards are prohibited for Medicare/Medicaid patients
-- (federal anti-kickback statute). PAPs, charitable foundations, cash
-- routes, and LIS/Extra Help are the Medicare-legal paths.

CREATE TABLE IF NOT EXISTS medications (
  med_slug        text PRIMARY KEY,          -- stable internal key
  rxcui           text,                      -- RxNorm concept ID; fill via RxNav (see README)
  generic_name    text NOT NULL,
  brand_name      text,
  drug_class      text NOT NULL,             -- ARNI, SGLT2, beta_blocker, MRA, loop_diuretic, ACE, ARB, DOAC, sGC_stimulator
  is_generic      boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS assistance_programs (
  program_slug        text PRIMARY KEY,
  program_name        text NOT NULL,
  program_type        text NOT NULL,         -- copay_card | pap | foundation | discount_cash | government
  sponsor             text,
  allowed_insurance   text NOT NULL,         -- pipe-delimited: commercial|medicare|medicaid|uninsured
  max_income_pct_fpl  integer,               -- NULL = no income test
  application_url     text,
  application_method  text,                  -- online | fax | provider_initiated | pharmacy
  typical_benefit     text,                  -- indicative; verify before quoting to a patient
  fund_status         text NOT NULL DEFAULT 'unverified',  -- open | closed | unverified
  last_verified       date
);

CREATE TABLE IF NOT EXISTS medication_programs (
  med_slug      text NOT NULL REFERENCES medications(med_slug),
  program_slug  text NOT NULL REFERENCES assistance_programs(program_slug),
  notes         text,
  PRIMARY KEY (med_slug, program_slug)
);

CREATE TABLE IF NOT EXISTS cash_prices (
  med_slug   text NOT NULL REFERENCES medications(med_slug),
  source     text NOT NULL,                  -- costplus | goodrx | pharmacy_cash
  price_usd  numeric,
  unit       text,                           -- e.g. '30-day supply'
  as_of      date NOT NULL,
  PRIMARY KEY (med_slug, source, as_of)
);

CREATE INDEX IF NOT EXISTS idx_programs_type   ON assistance_programs(program_type);
CREATE INDEX IF NOT EXISTS idx_programs_status ON assistance_programs(fund_status);

-- Agent query shape (given med + insurance + income signal):
--   SELECT m.*, p.*
--   FROM medications m
--   JOIN medication_programs mp USING (med_slug)
--   JOIN assistance_programs p USING (program_slug)
--   WHERE m.med_slug = $1
--     AND p.allowed_insurance LIKE '%' || $2 || '%'
--     AND (p.max_income_pct_fpl IS NULL OR p.max_income_pct_fpl >= $3)
--     AND p.fund_status <> 'closed'
--   ORDER BY CASE p.program_type
--     WHEN 'government' THEN 1   -- LIS first: durable, free to apply
--     WHEN 'pap' THEN 2          -- free drug beats discounts
--     WHEN 'foundation' THEN 3
--     WHEN 'copay_card' THEN 4
--     WHEN 'discount_cash' THEN 5 END;
