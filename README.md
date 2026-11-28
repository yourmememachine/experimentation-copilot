# Experimentation Copilot

Turn a plain-English request into a guarded Flagsmith experiment — and keep your flag list clean afterwards.

I built this for Toggle Wars Track 02 (AI Agents and Feature Flags). I kept running into the same two problems with feature flags: setting up a proper experiment takes a dozen careful steps in a dashboard, and old flags pile up until nobody knows what is safe to remove. Experimentation Copilot handles both ends of that lifecycle.

**Demo video:** https://www.youtube.com/watch?v=2p-yWPd_9i4
**Track:** 02 — AI Agents and Feature Flags

## What it does

1. **Prompt to experiment plan.** Type what you want to test, for example:
   > Test a new checkout button colour green vs blue for 20% of users, success is checkout_completed

   The copilot produces a complete plan: a multivariate flag (`checkout_button_colour`), control and variant values with allocations that sum to 100, the traffic percentage, the success metric, a written hypothesis, and a staged rollout (5% → 20% → 50% → 100%).
2. **Guardrails before anything ships.** The plan is checked before it can be applied:
   - Nothing is applied to production without my explicit approval in the UI.
   - Traffic above 50% warns; above 90% is blocked without approval.
   - An experiment cannot be created without a success metric and a hypothesis.
   - The previous flag state is snapshotted first, so every apply can be rolled back in one click. Rolling back restores the snapshotted state; a flag the apply created is disabled and archived on rollback, so nothing it created stays servable.
   - Flag names must follow a clean snake_case convention.
3. **Approve and apply.** With approval, the copilot creates the multivariate flag in Flagsmith through the Flagsmith API, starting from the first rollout step rather than switching on at full exposure. Flagsmith is what serves the variants and splits the traffic from that point on — the copilot decides *what should happen next* (create, ramp, roll back, clean up), and Flagsmith carries it out and reports back.
4. **Results and winner rollout.** The results panel records exposures and conversions per variant (a built-in simulator can generate deterministic demo traffic), names the winning variant — or says "inconclusive" when there is not enough data — and, with a second approval, graduates the winner to 100% in Flagsmith, snapshotting the previous state first so that step can be rolled back too.
5. **Stale-flag cleanup.** A cleanup view scores every flag for staleness — old and quiet together, sitting at 100% rollout for over 14 days (the experiment is decided; roll the winner out in code), or disabled for over 30 days — and recommends archive, roll out the winner, or keep, with the reasons shown. "Quiet" is judged on whatever evaluation evidence a flag carries: an evaluation count or a last-evaluated timestamp when one is available. Live Flagsmith payloads carry neither, so there quiet is inferred from age alone and the reason says "no evaluation data recorded" instead of claiming an evaluation history that was never measured; durations that no explicit record verifies are stated as unverified rather than asserted.

## How Flagsmith is used

Flagsmith is the core of the project, not a storage layer:

- **Multivariate flags** hold the experiment variants and their allocations.
- **Traffic splits** are set on the flag, so Flagsmith decides which version each user sees.
- **The experiment lifecycle** — create, ramp through rollout stages, roll back from a snapshot, archive when stale — is driven through the Flagsmith API by the copilot's planner and guardrails.
- **Flag state data** (age, rollout state, enabled state) feeds the staleness scoring that drives cleanup recommendations. Where a flag carries evaluation data — a recent evaluation count or a last-evaluated timestamp — that feeds the scoring too; live Flagsmith feature payloads carry neither, and the scorer's reasons say so rather than assuming an evaluation history.

### Flags used in the demo

| Flag | Type | Purpose |
| --- | --- | --- |
| `checkout_button_colour` | Multivariate (created live in the demo) | The experiment below |
| `new_checkout_flow` | Boolean | Seeded example flag |
| `pricing_page_redesign` | Boolean | Seeded example flag |
| `recommendations_v2` | Boolean | Seeded example flag |
| `beta_dashboard_access` | Boolean | Seeded example flag |
| `legacy_search_v1` | Boolean | Stale — recommended for archive |
| `old_promo_banner` | Boolean | Stale — recommended for archive |
| `holiday_sale_banner_2025` | Boolean | Stale — recommended for archive |

The three stale flags are seeded fixtures: their creation dates were set
210 days in the past, which is the "210 days" age the cleanup check and
the Flagsmith dashboard show in the video.

### Experiment hypothesis

> If users see the checkout button colour variant "blue" instead of "green", then `checkout_completed` will improve, because the change is easier to notice and act on.

Metric: `checkout_completed` events. Traffic: 20% of users, split 50/50 between control (green) and variant (blue), ramping 5% → 20% → 50% → 100% only while the guardrails pass.

### Decision rule (fixed in advance)

The simulation's winner rule is predetermined — it is defined here and in `app/main.py` (`h_simulate`), and it does not change from run to run:

- **Primary metric:** the per-variant conversion rate of the experiment's success metric.
- **Significance threshold:** a two-proportion z-test of the leader against the runner-up must reach **p < 0.05** (alpha = 0.05).
- **Sample-size floor:** at least **30 conversions in total** before any winner can be recommended, however large the gap looks.
- **Stopping rule:** if either condition fails, the verdict is **Inconclusive** (with the reason recorded: `insufficient_conversions` or `not_significant`) and the correct action is to keep collecting data — the current leader is never promoted on a hunch.
- **Reproducibility:** variant conversion rates are deterministic per flag + variant, derived from a hash of their names, so the same scenario always produces the same numbers and the p-value shown on the results card can be recomputed from the exposures and conversions displayed next to it. The demo shows both outcomes: a defensible winner (blue, p < 0.001 at 2,000 visitors) and a genuine Inconclusive (a 60-visitor run that clears neither bar).

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

## Reproducing the demo

From a clean checkout:

```bash
pip install -r requirements.txt
FLAGSMITH_DEMO_MODE=1 uvicorn app.main:app --port 8077
```

Demo mode needs no Flagsmith account and no credentials: the copilot runs against the built-in store (Option C above). Live mode (`FLAGSMITH_DEMO_MODE=0` with a token set) runs the identical flows against a real Flagsmith project — the demo video was recorded in live mode against a self-hosted Flagsmith, and the header of the app states which mode you are in ("Using sample flags" in demo mode, "Connected to Flagsmith (live)" in live mode).

The recorded demo flow, in order: describe the checkout experiment → review the plan → watch a 95%-traffic plan and a no-metric plan get stopped by the guardrails → approve and apply the 20% plan → see the flag live in the Flagsmith dashboard → simulate 2,000 visitors (winner: blue, p < 0.001) → simulate 60 visitors (Inconclusive) → roll the winner out to 100% and verify the weights in Flagsmith → run the stale check → archive a stale flag → roll the apply back from its snapshot.

The self-hosted build used for the demo gates its Audit Log page behind an Enterprise plan banner, so the page itself cannot be shown. An extract from the underlying audit table is published at [docs/AUDIT-EXTRACT.md](docs/AUDIT-EXTRACT.md). It is generated mechanically from the audit log and the history tables by `docs/generate_audit_extract.py` (raw export: [docs/audit-export.json](docs/audit-export.json)), and it keeps the runs it covers separate: `pricing_page_banner`, from the live-API verification run; `checkout_button_colour`, the flag the demo video centres on (its create, enable, graduate, archive-assist and rollback entries from the recorded session and the later capture passes); and the two rollback measurements — `signup_button_label`, which showed that an archive-only rollback left a created flag served enabled, and `hero_banner_colour`, the same lifecycle after the fix, where the created flag is disabled and archived on rollback and the SDK endpoint no longer serves it enabled.

## Tests

```bash
pytest tests/ -q
```

78 tests: the guardrail rules, the staleness scoring, the planner's edge cases, the Flagsmith client's request shapes against the current API, the simulation's significance gate, variant names rendering alongside their allocations in the flag list, the p-value rendering identically in the results and rollout views, and API-level safety tests proving that refused plans never mutate flag state, that rollback restores the pre-change state (including variant allocations), that a flag created by an apply is disabled and archived — in that order — when its apply is rolled back, and that archiving only ever touches flags the stale check marks safe to remove.

## Disclosure

In line with the hackathon rules: I used AI coding assistance while building this project, and I reviewed, tested, and take responsibility for all of the code in this repository.

## Licence

MIT — see `LICENSE`.
