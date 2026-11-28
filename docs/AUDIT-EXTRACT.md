# Audit extract — live Flagsmith proof runs

Sanitized extract from the audit log of the self-hosted Flagsmith instance
used to record the demo (official Flagsmith image + PostgreSQL, run locally
for this project). It covers the copilot's live proof run against a **fresh**
flag, `pricing_page_banner` (feature id 9), created and driven end to end by
the copilot itself through the Flagsmith API — no flag state in this run was
set by hand. A second section below covers `checkout_button_colour`, the
flag the demo video centres on, from the recorded session.

**Actor:** every entry below is recorded under the same actor — the copilot,
acting through its configured Flagsmith API token (`Authorization: Token …`;
in the audit log this resolves to author id 1, the demo workspace user).
The token value is a credential and is not reproduced here.

**Scope:** project "Demo Project" (id 1), environment "Development" (id 1).
Timestamps are UTC, exactly as recorded in the audit log (`audit_auditlog`).

## Create and enable (audit ids 26–30)

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 26 | 2026-11-27 13:51:35.950 | New Flag / Remote Config created: pricing_page_banner | Feature 9 |
| 27 | 2026-11-27 13:51:36.347 | New Flag / Remote Config created: pricing_page_banner | Feature state 9, Development |
| 28 | 2026-11-27 13:51:36.844 | Multivariate option added to feature 'pricing_page_banner'. | Feature 9 |
| 29 | 2026-11-27 13:51:37.261 | Multivariate option added to feature 'pricing_page_banner'. | Feature 9 |
| 30 | 2026-11-27 13:51:39.439 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |

Id 30 is the enable step: the copilot's apply set the new flag's state to ON
in the Development environment.

## Graduate — roll the winner out to 100% (audit ids 31–36)

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 31 | 2026-11-27 13:51:56.561 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |
| 32 | 2026-11-27 13:51:58.540 | Flag / Remote Config updated: pricing_page_banner | Feature 9 |
| 33 | 2026-11-27 13:52:00.546 | Flag / Remote Config updated: pricing_page_banner | Feature 9 |
| 34 | 2026-11-27 13:52:01.737 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |
| 35 | 2026-11-27 13:54:38.852 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |
| 36 | 2026-11-27 13:54:39.237 | Multivariate value changed for feature 'pricing_page_banner'. | Feature state 9, Development |

Ids 31–36 are the graduate step: the copilot wrote the winning variant's
allocation (100/0) at both the feature-default level (ids 32–33) and the
environment level (ids 31, 34–36).

Rollback was live-verified separately in the same session: snapshot →
graduate to 100/0 → rollback restored the original 50/50 split, confirmed by
reading the flag back through the API — the same restore path the automated
tests exercise (`tests/test_api_safety.py`).

## The demo video's flag: `checkout_button_colour`

The sections above belong to `pricing_page_banner`. The flag the demo
video centres on is a different one, `checkout_button_colour`, and its own
audit entries from the recorded session (2026-11-27, same project,
environment and API-token actor) are below. The recording was captured in
passes, and each pass re-created the flag from scratch — so the flag
appears under three feature ids. They are grouped by feature id so each
pass can be checked on its own.

### Main session (feature id 10)

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 42 | 2026-11-27 13:57:26.075 | New Flag / Remote Config created: checkout_button_colour | Feature 10 |
| 43 | 2026-11-27 13:57:26.477 | New Flag / Remote Config created: checkout_button_colour | Feature state 10, Development |
| 44 | 2026-11-27 13:57:26.980 | Multivariate option added to feature 'checkout_button_colour'. | Feature 10 |
| 45 | 2026-11-27 13:57:27.399 | Multivariate option added to feature 'checkout_button_colour'. | Feature 10 |
| 46 | 2026-11-27 13:57:28.930 | Flag state updated for feature: checkout_button_colour | Feature state 10, Development |
| 47 | 2026-11-27 13:57:43.073 | Flag state updated for feature: checkout_button_colour | Feature state 10, Development |
| 48 | 2026-11-27 13:57:43.681 | Flag / Remote Config updated: checkout_button_colour | Feature 10 |
| 49 | 2026-11-27 13:57:44.071 | Flag / Remote Config updated: checkout_button_colour | Feature 10 |
| 50 | 2026-11-27 13:57:57.501 | Flag / Remote Config updated: holiday_sale_banner_2025 | Feature 6 |
| 51 | 2026-11-27 13:58:03.063 | Flag / Remote Config updated: checkout_button_colour | Feature 10 |
| 52 | 2026-11-27 14:00:06.482 | Flag state updated for feature: checkout_button_colour | Feature state 10, Development |

Ids 42–45 are the create step (flag, environment state, and the two variant
options). Id 46 is the enable. Ids 47–49 are the graduate step (winner to
100%). Id 50 sits inside this session's window because it is the archive
beat: the copilot's cleanup archived the stale `holiday_sale_banner_2025`
flag. Id 51 is the rollback step restoring the pre-apply state from its
snapshot.

### Dashboard pass (feature id 11)

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 56 | 2026-11-27 14:02:44.586 | New Flag / Remote Config created: checkout_button_colour | Feature 11 |
| 57 | 2026-11-27 14:02:44.958 | New Flag / Remote Config created: checkout_button_colour | Feature state 11, Development |
| 58 | 2026-11-27 14:02:45.463 | Multivariate option added to feature 'checkout_button_colour'. | Feature 11 |
| 59 | 2026-11-27 14:02:45.869 | Multivariate option added to feature 'checkout_button_colour'. | Feature 11 |
| 60 | 2026-11-27 14:02:46.510 | Flag state updated for feature: checkout_button_colour | Feature state 11, Development |
| 61 | 2026-11-27 14:03:40.388 | Flag state updated for feature: checkout_button_colour | Feature state 11, Development |
| 62 | 2026-11-27 14:03:40.946 | Flag / Remote Config updated: checkout_button_colour | Feature 11 |
| 63 | 2026-11-27 14:03:41.349 | Flag / Remote Config updated: checkout_button_colour | Feature 11 |

This pass produced the dashboard shots: create and enable (ids 56–60),
then the graduate (ids 61–63) whose 0/100 weights the Edit Feature panel
shows in the video.

### Results pass (feature id 12)

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 66 | 2026-11-27 14:07:28.636 | New Flag / Remote Config created: checkout_button_colour | Feature 12 |
| 67 | 2026-11-27 14:07:28.999 | New Flag / Remote Config created: checkout_button_colour | Feature state 12, Development |
| 68 | 2026-11-27 14:07:29.491 | Multivariate option added to feature 'checkout_button_colour'. | Feature 12 |
| 69 | 2026-11-27 14:07:29.887 | Multivariate option added to feature 'checkout_button_colour'. | Feature 12 |
| 70 | 2026-11-27 14:07:30.228 | Flag state updated for feature: checkout_button_colour | Feature state 12, Development |

Each pass ended by deleting its flag so the next pass started from the
same clean state (deletion entries: ids 53–55, 64–65 and 73–74). An
earlier run the same morning used feature id 8 for the same flag name
(ids 20–25) and was deleted before the recorded session (ids 40–41).

## What this proves

- One flag, one environment, one API actor across the whole sequence —
  create, enable and graduate form a single copilot execution (with rollback
  verified in the same session), corroborated by Flagsmith's own audit trail
  rather than by screenshots.
- The enable (id 30) was performed by the copilot's API token. No dashboard
  session or manual toggle is involved in any entry above.
- The same holds for the video's own flag: `checkout_button_colour`'s
  create, enable, graduate, archive-assist and rollback entries (ids 42–52,
  with the dashboard and results passes at ids 56–63 and 66–70) are all
  recorded under the copilot's API token in the same audit log.

*Note: this self-hosted build's Audit Log page in the web UI is
Enterprise-gated, which is why this extract is taken from the audit records
themselves (database/API) instead of a UI screenshot.*
