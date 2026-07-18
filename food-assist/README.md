# Food assistance lookup

Schema + demo-county seed data for the food security feature: given the
patient's insurance plan, age, homebound status, and home county/zip, walk
the waterfall and initiate delivery referrals timed to the day the patient
is home.

## The waterfall

1. **Tier 1 — insurance pays.** Check `insurance_meal_benefits` by plan_id.
   Many MA plans cover 2-4 weeks of home-delivered meals after an inpatient
   stay (fulfilled by vendors like Mom's Meals). Traditional Medicare covers
   nothing — that row exists in the seed so the demo shows the branch failing
   honestly. Activation happens pre-discharge via the plan care management line.
2. **Tier 2 — Meals on Wheels.** ~5,000 independent local programs; no national
   API. Seeded with the real Orange County FL provider. `waitlist_status`
   matters: "eligible" and "fed next week" are different facts. If waitlisted,
   the agent continues to tier 3 rather than stopping.
3. **Tier 3 — everything else.** Medically tailored self-pay (heart-friendly
   menus rank first for HF), food bank, SNAP, OAA senior meals, and 211 /
   findhelp as live referral networks when the static rows miss.

## The verb is "initiate," not "enroll"

Each program has its own intake. The agent creates a `food_referrals` row with
`delivery_start_date` pegged to expected discharge, emits a FHIR Task for
social work review at rounds, and tracks status through
initiated -> submitted -> confirmed -> first_delivery_verified. The
confirmation step is the loop-closure metric.

## Demo county

Orange County, FL (Orlando). Real organizations, but contact details,
waitlist status, and benefit specifics are indicative and marked unverified.
Patient rows must be synthetic (Synthea) only.

## Loading

```
psql $DATABASE_URL -f schema/002_food_assistance.sql
# load seeds/*.csv with \copy
```

## TODO before demo

- [ ] Verify Seniors First intake process and current waitlist status
- [ ] Verify Mom's Meals self-pay pricing and heart-friendly menu name
- [ ] Confirm the demo MA plan benefit numbers read as realistic (28 meals / 28 days is typical)
- [ ] Decide the demo patient's plan_id: DEMO-H0000-001 shows the tier-1 win; DEMO-TRADITIONAL shows the full waterfall

## Production later (not hackathon)

- CMS Plan Benefit Package (PBP) files: annual, public — build the real
  plan_id -> meal benefit table from these
- findhelp or 211 API license for live tier-3 coverage in any zip
- Medicaid MTM waiver flags by state (e.g. CalAIM in CA)
- Waitlist freshness job for tier-2 programs
