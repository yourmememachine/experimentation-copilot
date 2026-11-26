# Experimentation Copilot

Turn a plain-English request into a guarded Flagsmith experiment — and keep your flag list clean afterwards.

I built this for Toggle Wars Track 02 (AI Agents and Feature Flags). I kept running into the same two problems with feature flags: setting up a proper experiment takes a dozen careful steps in a dashboard, and old flags pile up until nobody knows what is safe to remove. Experimentation Copilot handles both ends of that lifecycle.

**Demo video:** _link added once the final recording is uploaded_
**Track:** 02 — AI Agents and Feature Flags

## What it does

1. **Prompt to experiment plan.** Type what you want to test, for example:
   > Test a new checkout button colour green vs blue for 20% of users, success is checkout_completed

   The copilot produces a complete plan: a multivariate flag (`checkout_button_colour`), control and variant values with allocations that sum to 100, the traffic percentage, the success metric, a written hypothesis, and a staged rollout (5% → 20% → 50% → 100%).
2. **Guardrails before anything ships.** The plan is checked before it can be applied:
   - Nothing is applied to production without my explicit approval in the UI.
   - Traffic above 50% warns; above 90% is blocked without approval.
   - An experiment cannot be created without a success metric and a hypothesis.
   - The previous flag state is snapshotted first, so every apply can be rolled back in one click.
   - Flag names must follow a clean snake_case convention.
3. **Approve and apply.** With approval, the copilot creates the multivariate flag in Flagsmith through the Flagsmith API, starting from the first rollout step rather than switching on at full exposure. Flagsmith is what serves the variants and splits the traffic from that point on — the copilot decides *what should happen next* (create, ramp, roll back, clean up), and Flagsmith carries it out and reports back.
4. **Results and winner rollout.** The results panel records exposures and conversions per variant (a built-in simulator can generate deterministic demo traffic), names the winning variant — or says "inconclusive" when there is not enough data — and, with a second approval, graduates the winner to 100% in Flagsmith, snapshotting the previous state first so that step can be rolled back too.
5. **Stale-flag cleanup.** A cleanup view scores every flag for staleness — older than 90 days with no evaluations in 30 days, sitting at 100% rollout for over 14 days (the experiment is decided; roll the winner out in code), or disabled for over 30 days — and recommends archive, roll out the winner, or keep, with the reasons shown.

## How Flagsmith is used

Flagsmith is the core of the project, not a storage layer:

- **Multivariate flags** hold the experiment variants and their allocations.
- **Traffic splits** are set on the flag, so Flagsmith decides which version each user sees.
- **The experiment lifecycle** — create, ramp through rollout stages, roll back from a snapshot, archive when stale — is driven through the Flagsmith API by the copilot's planner and guardrails.
- **Flag evaluation data** (age, last evaluation, rollout state) feeds the staleness scoring that drives cleanup recommendations.

### Flags used in the demo

| Flag | Type | Purpose |
| --- | --- | --- |
| `checkout_button_colour` | Multivariate (created live in the demo) | The experiment below |
| `new_onboarding_flow` | Boolean | Seeded example flag |
| `pricing_page_v2` | Boolean | Seeded example flag |
| `legacy_search_v1` | Boolean | Stale — recommended for archive |
| `old_promo_banner` | Boolean | Stale — recommended for archive |
| `holiday_sale_banner_2025` | Boolean | Stale — recommended for archive |

### Experiment hypothesis

> If users see the checkout button colour variant "blue" instead of "green", then `checkout_completed` will improve, because the change is easier to notice and act on.

Metric: `checkout_completed` events. Traffic: 20% of users, split 50/50 between control (green) and variant (blue), ramping 5% → 20% → 50% → 100% only while the guardrails pass.

## Flagsmith setup

Option A — Flagsmith Cloud (free tier):

1. Create a free account at https://flagsmith.com and create a project and an environment.
2. Create an API token for that environment.
3. Copy `.env.example` to `.env` and set:
   - `FLAGSMITH_API_URL` — the Flagsmith API base URL (cloud default is in `.env.example`)
   - `FLAGSMITH_API_TOKEN` — your environment API token
   - `FLAGSMITH_ENVIRONMENT_ID` — your environment ID
   - `FLAGSMITH_DEMO_MODE=0`

Option B — Self-hosted Flagsmith: run Flagsmith with its official Docker setup, create a project/environment/token the same way, and point `FLAGSMITH_API_URL` at your instance.

Option C — Demo mode (no account needed): leave the token unset or set `FLAGSMITH_DEMO_MODE=1`. The copilot then runs against a built-in store that implements the same interface and is seeded with the flags in the table above, so the full flow — plan, guardrails, approve, apply, stale cleanup, rollback — works end to end offline.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # optional in demo mode
uvicorn app.main:app --port 8077
```

Open http://127.0.0.1:8077, type a prompt (or click an example), review the plan and guardrails, tick the approval box, and apply. Then open the cleanup view to see the stale-flag recommendations.

Without FastAPI installed, the app falls back to a standard-library server with the same routes: `python3 -m app.main`.

## Tests

```bash
pytest tests/ -q
```

45 tests cover the guardrail rules, the staleness scoring, and the planner's edge cases.

## Disclosure

In line with the hackathon rules: I used AI coding assistance while building this project, and I reviewed, tested, and take responsibility for all of the code in this repository.

## Licence

MIT — see `LICENSE`.
