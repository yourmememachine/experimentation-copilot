# Audit extract — live Flagsmith proof runs

Sanitized extract from the audit log of the self-hosted Flagsmith instance
used to record the demo (official Flagsmith image + PostgreSQL, run locally
for this project). It covers the copilot's live proof run against a **fresh**
flag, `pricing_page_banner` (feature id 9), created and driven end to end by
the copilot itself through the Flagsmith API — no flag state in this run was
set by hand.

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

## What this proves

- One flag, one environment, one API actor across the whole sequence —
  create, enable and graduate form a single copilot execution (with rollback
  verified in the same session), corroborated by Flagsmith's own audit trail
  rather than by screenshots.
- The enable (id 30) was performed by the copilot's API token. No dashboard
  session or manual toggle is involved in any entry above.

*Note: this self-hosted build's Audit Log page in the web UI is
Enterprise-gated, which is why this extract is taken from the audit records
themselves (database/API) instead of a UI screenshot.*
