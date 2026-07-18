# Medication assistance lookup

Schema + seed data for the affordability feature: given a discharge med, the
patient's insurance type, and an income signal from the ambient conversation,
return legally usable assistance options ranked by value.

## The compliance branch (why this isn't just a coupon lookup)

Manufacturer copay cards are **prohibited for Medicare and Medicaid patients**
under the federal anti-kickback statute. `assistance_programs.allowed_insurance`
enforces this. The agent must never surface a `copay_card` row to a
Medicare/Medicaid patient. Legal Medicare routes, in ranking order:

1. `government` — Extra Help / LIS (durable, capped copays, income <=150% FPL)
2. `pap` — manufacturer Patient Assistance Programs (free drug, income-tested)
3. `foundation` — PAN / HealthWell disease funds (open/close monthly — check `fund_status`)
4. `discount_cash` — Cost Plus / GoodRx cash price outside insurance

For commercial patients, copay cards rank first. When nothing qualifies,
the correct output is a prompt back to the prescriber for an on-formulary
therapeutic alternative *before* discharge — not silence.

## Loading

```
psql $DATABASE_URL -f schema/001_medication_assistance.sql
# then load seeds/*.csv with \copy, splitting allowed_insurance on '|'
```

## TODO before demo

- [ ] Fill `rxcui` via RxNav: `https://rxnav.nlm.nih.gov/REST/rxcui.json?name=<generic_name>&search=1` (free, no key)
- [ ] Verify every `typical_benefit`, `max_income_pct_fpl`, and `application_url`
      — all values are indicative as of 2026-07-18 and marked `fund_status=unverified`
- [ ] Check PAN HF fund and HealthWell CV fund open/closed status (changes monthly)
- [ ] Refresh `cash_prices` (indicative estimates, not scraped quotes)

## Production later (not hackathon)

- NeedyMeds dataset license for comprehensive PAP coverage
- Nightly fund_status refresh job for foundations
- Formulary integration (patient's actual plan tier) replaces the
  insurance-type heuristic
