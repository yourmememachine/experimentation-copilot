# Audit extract — live Flagsmith proof runs

Sanitized extract from the audit log of the self-hosted Flagsmith instance
used to record the demo (official Flagsmith image + PostgreSQL, run locally
for this project). It covers the copilot's live proof run against a **fresh**
flag, `pricing_page_banner` (feature id 9), created and driven end to end
through the Flagsmith API. A second section below covers
`checkout_button_colour`, the flag the demo video centres on, from the
recorded session. Field-level before/after values were cross-checked
against Flagsmith's own history tables (`features_historicalfeature`,
`features_historicalfeaturestate` and the multivariate history tables),
which record what each write actually changed.

**Actor:** every entry below is recorded under the same actor — author
id 1, the demo workspace user, which is who the copilot's configured
Flagsmith API token (`Authorization: Token …`) resolves to. The token
value is a credential and is not reproduced here. One limit of this
evidence: the audit log records the same author for dashboard actions
as for this token's API calls, so the rows alone do not exclude manual
action. What ties the entries to the copilot's API calls is their
timing and shape — bursts of writes seconds apart that match the
client's call sequence (create → options → state), repeated
identically across independent passes — together with the session
record, in which the run was driven through the API. No stronger claim
is made.

**Scope:** project "Demo Project" (id 1), environment "Development" (id 1).
Timestamps are UTC, exactly as recorded in the audit log (`audit_auditlog`).

## Create and enable (audit ids 26–30)

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 26 | 2026-11-27 13:51:35.950 | New Flag / Remote Config created: pricing_page_banner | Feature 9 |
| 27 | 2026-11-27 13:51:36.347 | New Flag / Remote Config created: pricing_page_banner | Feature state 9, Development |
| 28 | 2026-11-27 13:51:36.844 | Multivariate option added to feature 'pricing_page_banner'. | Feature 9 |
| 29 | 2026-11-27 13:51:37.260 | Multivariate option added to feature 'pricing_page_banner'. | Feature 9 |
| 30 | 2026-11-27 13:51:39.439 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |

Id 30 is the enable step: the state history shows `enabled` going
false → true at that instant. Ids 26–29 are the create and the two
variant options, both starting at a 50/50 split.

## After the enable (audit ids 31–37)

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 31 | 2026-11-27 13:51:56.560 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |
| 32 | 2026-11-27 13:51:58.539 | Flag / Remote Config updated: pricing_page_banner | Feature 9 |
| 33 | 2026-11-27 13:52:00.545 | Flag / Remote Config updated: pricing_page_banner | Feature 9 |
| 34 | 2026-11-27 13:52:01.736 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |
| 35 | 2026-11-27 13:54:38.852 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |
| 36 | 2026-11-27 13:54:39.236 | Multivariate value changed for feature 'pricing_page_banner'. | Feature state 9, Development |
| 37 | 2026-11-27 13:54:39.344 | Multivariate value changed for feature 'pricing_page_banner'. | Feature state 9, Development |

The history tables show what each of these writes changed:

- Id 31 rewrote the state and the feature-level allocations with
  identical values (`enabled` stayed on; the split stayed 50/50).
- Ids 32–33 are an archive followed two seconds later by an
  un-archive: the feature history shows `is_archived` going
  false → true at 13:51:58.539 and back to false at 13:52:00.545 —
  the archive and archive-rollback exercise.
- Id 34 rewrote the state; nothing changed.
- Ids 35–37 are the graduate write, about two and a half minutes
  later: the feature-level default allocations went to green 0 /
  blue 100 at 13:54:38.078/.228, and ids 36–37 wrote the same split
  into the environment state. This is the only point in the run
  where the 100/0 split was written.

The flag was then deleted (ids 38–39, 13:54:52.855/13:54:53.245)
while still at 0/100. This run's records contain no rollback of the
graduate; the verified rollback restore is feature 13's, below. (The
restore path itself is also exercised by the automated tests,
`tests/test_api_safety.py`.)

## The demo video's flag: `checkout_button_colour`

The sections above belong to `pricing_page_banner`. The flag the demo
video centres on is a different one, `checkout_button_colour`, and its own
audit entries from the recorded session (2026-11-27, same project,
environment and API-token actor) are below. The recording was captured in
passes, and each pass re-created the flag from scratch — so the flag
appears under three feature ids in the recorded session, plus a fourth
in the verification pass. They are grouped by feature id so each pass
can be checked on its own.

### Main session (feature id 10)

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 42 | 2026-11-27 13:57:26.559 | New Flag / Remote Config created: checkout_button_colour | Feature 10 |
| 43 | 2026-11-27 13:57:26.643 | New Flag / Remote Config created: checkout_button_colour | Feature state 10, Development |
| 44 | 2026-11-27 13:57:26.839 | Multivariate option added to feature 'checkout_button_colour'. | Feature 10 |
| 45 | 2026-11-27 13:57:27.133 | Multivariate option added to feature 'checkout_button_colour'. | Feature 10 |
| 46 | 2026-11-27 13:57:28.847 | Flag state updated for feature: checkout_button_colour | Feature state 10, Development |
| 47 | 2026-11-27 13:57:43.944 | Flag state updated for feature: checkout_button_colour | Feature state 10, Development |
| 48 | 2026-11-27 13:57:44.223 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 10, Development |
| 49 | 2026-11-27 13:57:44.423 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 10, Development |
| 50 | 2026-11-27 13:57:57.833 | Flag / Remote Config updated: holiday_sale_banner_2025 | Feature 6 |
| 51 | 2026-11-27 13:58:03.965 | Flag / Remote Config updated: checkout_button_colour | Feature 10 |
| 52 | 2026-11-27 14:00:06.265 | Flag state updated for feature: checkout_button_colour | Feature state 10, Development |

- Ids 42–45 are the create step (flag, environment state, and the two
  variant options, green and blue, at 50/50). Id 46 is the enable
  (`enabled` false → true).
- Ids 47–49 are the graduate step: the feature-level default
  allocations were written to green 0 / blue 100 at
  13:57:43.057/.238, and ids 48–49 wrote the same split into the
  environment state.
- Id 50 sits inside this session's window because it is the archive
  beat: the copilot's stale-check flow archived the stale
  `holiday_sale_banner_2025` flag.
- Id 51 is the rollback of the apply. The snapshot taken at apply
  time recorded that the flag did not exist beforehand, and the app
  implements rollback of a flag the apply itself created as an
  archive. The feature history row at 13:58:03.965 shows exactly one
  change — `is_archived` false → true. The flag was not deleted, and
  its enabled state and 0/100 split were left untouched. What the
  rollback restored, for a created flag, is the pre-apply situation:
  no live flag under that name.
- Id 52, about two minutes later, rewrote the environment state with
  identical values — `enabled` stayed on and the allocations stayed
  green 0 / blue 100, as the state history at 14:00:06.265 and the
  value history at 14:00:06.644/.758 show. It changed nothing and
  restored nothing; in particular it did not restore the 50/50
  split. The records do not identify which call produced this write,
  and this extract does not guess.
- The pass ended by un-archiving the flag (id 53, 14:02:24.046 —
  this Flagsmith build refuses to delete an archived feature) and
  deleting it (ids 54–55, 14:02:25.235/.442).

### Dashboard pass (feature id 11)

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 56 | 2026-11-27 14:02:44.088 | New Flag / Remote Config created: checkout_button_colour | Feature 11 |
| 57 | 2026-11-27 14:02:44.165 | New Flag / Remote Config created: checkout_button_colour | Feature state 11, Development |
| 58 | 2026-11-27 14:02:44.349 | Multivariate option added to feature 'checkout_button_colour'. | Feature 11 |
| 59 | 2026-11-27 14:02:44.533 | Multivariate option added to feature 'checkout_button_colour'. | Feature 11 |
| 60 | 2026-11-27 14:02:46.176 | Flag state updated for feature: checkout_button_colour | Feature state 11, Development |
| 61 | 2026-11-27 14:03:40.580 | Flag state updated for feature: checkout_button_colour | Feature state 11, Development |
| 62 | 2026-11-27 14:03:41.124 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 11, Development |
| 63 | 2026-11-27 14:03:41.363 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 11, Development |

This pass produced the dashboard shots: create and enable (ids 56–60),
then the graduate (ids 61–63) whose 0/100 weights the Edit Feature panel
shows in the video.

### Results pass (feature id 12)

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 66 | 2026-11-27 14:07:28.141 | New Flag / Remote Config created: checkout_button_colour | Feature 12 |
| 67 | 2026-11-27 14:07:28.159 | New Flag / Remote Config created: checkout_button_colour | Feature state 12, Development |
| 68 | 2026-11-27 14:07:28.245 | Multivariate option added to feature 'checkout_button_colour'. | Feature 12 |
| 69 | 2026-11-27 14:07:28.447 | Multivariate option added to feature 'checkout_button_colour'. | Feature 12 |
| 70 | 2026-11-27 14:07:30.357 | Flag state updated for feature: checkout_button_colour | Feature state 12, Development |

The passes' flags were deleted at ids 54–55 (feature 10, above),
ids 64–65 (feature 11, 14:07:13.394/.557) and ids 73–74 (feature 12,
14:33:53.841/.650 — after two further state rewrites at ids 71–72,
14:33:16.544/14:33:44.044, which left the enabled state unchanged).
An earlier run the same morning used feature id 8 for the same flag
name (ids 20–25) and was deleted before the recorded session
(ids 40–41).

### Verification pass (feature id 13)

A final pass the same day ran the whole lifecycle as an explicit
rollback check: create (ids 75–78, 14:34:04–05), enable (id 79,
14:34:07.635), graduate to green 0 / blue 100 (ids 80–83,
14:34:12–20), then rollback (ids 84–86, 14:34:26–27). The rollback's
allocation writes at 14:34:26.755 and 14:34:27.043 put the split
back to 50/50, confirmed in the feature-state history. This is the
run the build record's end-to-end rollback proof refers to: rolling
back a graduate restores the exact state the graduate replaced,
because the snapshot was taken before the graduate ran.

## What this proves

- The audit log and the history tables agree entry for entry, and
  the history tables show exactly which field each write changed —
  including the writes that changed nothing (ids 31, 34 and 52),
  which this extract reports as no-ops rather than dressing them up
  as steps.
- The entries' timing and shape match the copilot's API call
  sequence, and the recorded session was driven through the API.
  Per the Actor note, that conclusion rests on the session record
  and the pattern of the writes, not on the author field alone —
  the same holds for the video's own flag, `checkout_button_colour`
  (ids 42–52, with the dashboard and results passes at ids 56–63
  and 66–70).

*Note: this self-hosted build's Audit Log page in the web UI is
Enterprise-gated, which is why this extract is taken from the audit records
themselves (database/API) instead of a UI screenshot.*
