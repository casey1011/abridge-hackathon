-- Food assistance lookup: schema
-- Idempotent; safe to re-run. Postgres.
-- Waterfall: tier 1 insurance benefit -> tier 2 Meals on Wheels -> tier 3 other.
-- The agent initiates referrals with a delivery start pegged to discharge date,
-- then closes the loop on confirmation. It does not "enroll" the patient itself.

CREATE TABLE IF NOT EXISTS food_programs (
  program_slug        text PRIMARY KEY,
  program_name        text NOT NULL,
  program_type        text NOT NULL,      -- insurance_benefit | mow | mtm | food_bank | government | referral_network
  tier                integer NOT NULL,   -- 1 insurance pays, 2 MoW, 3 everything else
  medically_tailored  boolean NOT NULL DEFAULT false,  -- low-sodium HF menus vs general meals
  eligibility_notes   text,
  signup_method       text,               -- plan_care_mgmt | phone_intake | online | provider_referral
  signup_contact      text,               -- phone or URL
  waitlist_status     text NOT NULL DEFAULT 'unverified',  -- open | waitlist | closed | unverified
  coverage_level      text NOT NULL,      -- plan | national | state | county | zip
  coverage_value      text,               -- plan_id, state code, county name, or zip
  last_verified       date
);

CREATE TABLE IF NOT EXISTS insurance_meal_benefits (
  plan_id             text PRIMARY KEY,   -- CMS contract-plan ID (from annual PBP files)
  plan_name           text,
  meals_covered       integer,            -- e.g. 28
  benefit_trigger     text,               -- 'post inpatient discharge'
  duration_days       integer,
  activation_channel  text,               -- plan care management line, vendor portal
  fulfillment_vendor  text                -- e.g. Mom's Meals
);

CREATE TABLE IF NOT EXISTS food_referrals (
  referral_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_ref          text NOT NULL,     -- synthetic patient ID (Synthea); never PHI in demo
  program_slug         text NOT NULL REFERENCES food_programs(program_slug),
  initiated_at         timestamptz NOT NULL DEFAULT now(),
  expected_discharge   date,
  delivery_start_date  date,              -- pegged to day patient is home
  status               text NOT NULL DEFAULT 'initiated',
    -- initiated -> submitted -> confirmed -> first_delivery_verified | declined | waitlisted
  status_updated_at    timestamptz,
  notes                text
);

CREATE INDEX IF NOT EXISTS idx_food_programs_tier     ON food_programs(tier);
CREATE INDEX IF NOT EXISTS idx_food_programs_coverage ON food_programs(coverage_level, coverage_value);
CREATE INDEX IF NOT EXISTS idx_food_referrals_status  ON food_referrals(status);

-- Agent waterfall (given plan_id, age, homebound flag, county/zip):
--   1. SELECT * FROM insurance_meal_benefits WHERE plan_id = $1;
--      -> hit: emit activation task to plan care mgmt; delivery_start = discharge date. STOP.
--   2. SELECT * FROM food_programs
--      WHERE tier = 2 AND coverage_value = $county AND waitlist_status <> 'closed';
--      -> initiate phone intake referral; if 'waitlist', ALSO continue to tier 3.
--   3. SELECT * FROM food_programs WHERE tier = 3 AND (coverage_value IN ($county,$state) OR coverage_level = 'national')
--      ORDER BY medically_tailored DESC;   -- HF patients: low-sodium menus first
-- Every hit becomes a food_referrals row + FHIR Task for social work review at rounds.
