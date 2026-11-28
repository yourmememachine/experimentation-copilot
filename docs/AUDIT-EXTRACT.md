# Audit extract — live Flagsmith proof runs

Sanitized extract from the audit log of the self-hosted Flagsmith instance used to record the demo (official Flagsmith image + PostgreSQL, run locally for this project).

**This file is generated, not hand-written.** `docs/generate_audit_extract.py` reads `audit_auditlog` and the history tables and rebuilds this extract plus the raw export at `docs/audit-export.json`. Every timestamp and entry text below is the database's own value. Each audit row links to the history record it produced, and the change shown for an entry is the diff of that record against the previous record for the same object — so a write that changed nothing is reported as a no-op, mechanically. (An earlier hand-maintained version of this extract contained timestamps that differed from the log by up to about half a second and a few mislabelled entry types; that is why it is generated now.)

**Actor:** every entry below is recorded under the same actor — author id 1, the demo workspace user, which is who the copilot's configured Flagsmith API token (`Authorization: Token …`) resolves to. The token value is a credential and is not reproduced here. One limit of this evidence: the audit log records the same author for dashboard actions as for this token's API calls, so the rows alone do not exclude manual action. What ties the entries to the copilot's API calls is their timing and shape — bursts of writes seconds apart that match the client's call sequence (create → options → state), repeated identically across independent passes — together with the session record, in which the run was driven through the API. No stronger claim is made.

**Scope:** project "Demo Project" (id 1), environment "Development" (id 1). Timestamps are UTC, exactly as recorded in the audit log (`audit_auditlog`).

## Verification run: `pricing_page_banner` (feature 9)

A fresh flag created and driven end to end through the Flagsmith API by the copilot's own token: create, enable, graduate, and an archive / archive-rollback exercise.

### Audit entries

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 26 | 2026-11-27 13:51:35.950 | New Flag / Remote Config created: pricing_page_banner | Feature 9 |
| 27 | 2026-11-27 13:51:36.347 | New Flag / Remote Config created: pricing_page_banner | Feature state 9, Development |
| 28 | 2026-11-27 13:51:36.844 | Multivariate option added to feature 'pricing_page_banner'. | Feature 9 |
| 29 | 2026-11-27 13:51:37.260 | Multivariate option added to feature 'pricing_page_banner'. | Feature 9 |
| 30 | 2026-11-27 13:51:39.439 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |
| 31 | 2026-11-27 13:51:56.560 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |
| 32 | 2026-11-27 13:51:58.539 | Flag / Remote Config updated: pricing_page_banner | Feature 9 |
| 33 | 2026-11-27 13:52:00.545 | Flag / Remote Config updated: pricing_page_banner | Feature 9 |
| 34 | 2026-11-27 13:52:01.736 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |
| 35 | 2026-11-27 13:54:38.852 | Flag state updated for feature: pricing_page_banner | Feature state 9, Development |
| 36 | 2026-11-27 13:54:39.236 | Multivariate value changed for feature 'pricing_page_banner'. | Feature state 9, Development |
| 37 | 2026-11-27 13:54:39.344 | Multivariate value changed for feature 'pricing_page_banner'. | Feature state 9, Development |
| 38 | 2026-11-27 13:54:53.245 | Flag / Remote Config Deleted: pricing_page_banner | Feature 9 |
| 39 | 2026-11-27 13:54:52.855 | Flag / Remote Config Deleted: pricing_page_banner | Feature state 9, Development |

What the linked history records show each write changed:

- Id 26 (13:51:35.950): feature 9 created (name=pricing_page_banner, default_enabled=False, is_archived=False).
- Id 27 (13:51:36.347): feature state 9 created (enabled=False).
- Id 28 (13:51:36.844): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 29 (13:51:37.260): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 30 (13:51:39.439): feature state 9: enabled False → True.
- Id 31 (13:51:56.560): feature state 9: no field changed.
- Id 32 (13:51:58.539): feature 9: is_archived False → True.
- Id 33 (13:52:00.545): feature 9: is_archived True → False.
- Id 34 (13:52:01.736): feature state 9: no field changed.
- Id 35 (13:54:38.852): feature state 9: no field changed.
- Id 36 (13:54:39.236): environment value for option 'green': percentage_allocation 50 → 0.
- Id 37 (13:54:39.344): environment value for option 'blue': percentage_allocation 50 → 100.
- Id 38 (13:54:53.245): feature 9 deleted.
- Id 39 (13:54:52.855): feature state 9 deleted.

Reading of the run, from the linked history records above: the enable is the state write whose diff is `enabled False → True`; the two "Flag / Remote Config updated" entries in the middle of the run are an archive followed two seconds later by an un-archive (`is_archived` False → True → False); the graduate (ids 35–37) writes the environment values to green 0 / blue 100. The flag was then deleted while still at 0/100. This run contains no rollback of the graduate; the verified rollback restores are feature 13's and feature 19's, below. (The restore path is also exercised by the automated tests, `tests/test_api_safety.py`.)

## The demo video's flag: `checkout_button_colour`

The flag the demo video centres on. The recording was captured in passes, and each pass re-created the flag from scratch — so the flag appears under several feature ids. They are grouped by feature id so each pass can be checked on its own. Features 10–13 are the recorded session of 2026-11-27; features 14–17 and 20 are the later capture passes of 2026-11-28 (the audit log also records a dashboard login during those passes — see the appendix). Entries for other flags that fall inside these sessions' windows (the stale-check archive of `holiday_sale_banner_2025`) are listed in the appendix.

### Main session (feature 10) — 2026-11-27

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
| 51 | 2026-11-27 13:58:03.965 | Flag / Remote Config updated: checkout_button_colour | Feature 10 |
| 52 | 2026-11-27 14:00:06.265 | Flag state updated for feature: checkout_button_colour | Feature state 10, Development |
| 53 | 2026-11-27 14:02:24.046 | Flag / Remote Config updated: checkout_button_colour | Feature 10 |
| 54 | 2026-11-27 14:02:25.235 | Flag / Remote Config Deleted: checkout_button_colour | Feature state 10, Development |
| 55 | 2026-11-27 14:02:25.442 | Flag / Remote Config Deleted: checkout_button_colour | Feature 10 |

What the linked history records show each write changed:

- Id 42 (13:57:26.559): feature 10 created (name=checkout_button_colour, default_enabled=False, is_archived=False).
- Id 43 (13:57:26.643): feature state 10 created (enabled=False).
- Id 44 (13:57:26.839): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 45 (13:57:27.133): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 46 (13:57:28.847): feature state 10: enabled False → True.
- Id 47 (13:57:43.944): feature state 10: no field changed.
- Id 48 (13:57:44.223): environment value for option 'green': percentage_allocation 50 → 0.
- Id 49 (13:57:44.423): environment value for option 'blue': percentage_allocation 50 → 100.
- Id 51 (13:58:03.965): feature 10: is_archived False → True.
- Id 52 (14:00:06.265): feature state 10: no field changed.
- Id 53 (14:02:24.046): feature 10: is_archived True → False.
- Id 54 (14:02:25.235): feature state 10 deleted.
- Id 55 (14:02:25.442): feature 10 deleted.

### Dashboard pass (feature 11) — 2026-11-27

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
| 64 | 2026-11-27 14:07:13.394 | Flag / Remote Config Deleted: checkout_button_colour | Feature state 11, Development |
| 65 | 2026-11-27 14:07:13.557 | Flag / Remote Config Deleted: checkout_button_colour | Feature 11 |

What the linked history records show each write changed:

- Id 56 (14:02:44.088): feature 11 created (name=checkout_button_colour, default_enabled=False, is_archived=False).
- Id 57 (14:02:44.165): feature state 11 created (enabled=False).
- Id 58 (14:02:44.349): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 59 (14:02:44.533): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 60 (14:02:46.176): feature state 11: enabled False → True.
- Id 61 (14:03:40.580): feature state 11: no field changed.
- Id 62 (14:03:41.124): environment value for option 'green': percentage_allocation 50 → 0.
- Id 63 (14:03:41.363): environment value for option 'blue': percentage_allocation 50 → 100.
- Id 64 (14:07:13.394): feature state 11 deleted.
- Id 65 (14:07:13.557): feature 11 deleted.

### Results pass (feature 12) — 2026-11-27

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 66 | 2026-11-27 14:07:28.141 | New Flag / Remote Config created: checkout_button_colour | Feature 12 |
| 67 | 2026-11-27 14:07:28.159 | New Flag / Remote Config created: checkout_button_colour | Feature state 12, Development |
| 68 | 2026-11-27 14:07:28.245 | Multivariate option added to feature 'checkout_button_colour'. | Feature 12 |
| 69 | 2026-11-27 14:07:28.447 | Multivariate option added to feature 'checkout_button_colour'. | Feature 12 |
| 70 | 2026-11-27 14:07:30.357 | Flag state updated for feature: checkout_button_colour | Feature state 12, Development |
| 71 | 2026-11-27 14:33:16.544 | Flag state updated for feature: checkout_button_colour | Feature state 12, Development |
| 72 | 2026-11-27 14:33:44.044 | Flag state updated for feature: checkout_button_colour | Feature state 12, Development |
| 73 | 2026-11-27 14:33:53.841 | Flag / Remote Config Deleted: checkout_button_colour | Feature 12 |
| 74 | 2026-11-27 14:33:53.650 | Flag / Remote Config Deleted: checkout_button_colour | Feature state 12, Development |

What the linked history records show each write changed:

- Id 66 (14:07:28.141): feature 12 created (name=checkout_button_colour, default_enabled=False, is_archived=False).
- Id 67 (14:07:28.159): feature state 12 created (enabled=False).
- Id 68 (14:07:28.245): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 69 (14:07:28.447): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 70 (14:07:30.357): feature state 12: enabled False → True.
- Id 71 (14:33:16.544): feature state 12: no field changed.
- Id 72 (14:33:44.044): feature state 12: no field changed.
- Id 73 (14:33:53.841): feature 12 deleted.
- Id 74 (14:33:53.650): feature state 12 deleted.

### Verification pass (feature 13) — 2026-11-27

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 75 | 2026-11-27 14:34:04.749 | New Flag / Remote Config created: checkout_button_colour | Feature 13 |
| 76 | 2026-11-27 14:34:04.838 | New Flag / Remote Config created: checkout_button_colour | Feature state 13, Development |
| 77 | 2026-11-27 14:34:05.046 | Multivariate option added to feature 'checkout_button_colour'. | Feature 13 |
| 78 | 2026-11-27 14:34:05.429 | Multivariate option added to feature 'checkout_button_colour'. | Feature 13 |
| 79 | 2026-11-27 14:34:07.635 | Flag state updated for feature: checkout_button_colour | Feature state 13, Development |
| 80 | 2026-11-27 14:34:12.961 | Flag state updated for feature: checkout_button_colour | Feature state 13, Development |
| 81 | 2026-11-27 14:34:13.644 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 13, Development |
| 82 | 2026-11-27 14:34:13.949 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 13, Development |
| 83 | 2026-11-27 14:34:20.845 | Flag state updated for feature: checkout_button_colour | Feature state 13, Development |
| 84 | 2026-11-27 14:34:26.264 | Flag state updated for feature: checkout_button_colour | Feature state 13, Development |
| 85 | 2026-11-27 14:34:26.755 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 13, Development |
| 86 | 2026-11-27 14:34:27.043 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 13, Development |
| 88 | 2026-11-28 02:04:32.452 | Flag / Remote Config Deleted: checkout_button_colour | Feature 13 |
| 89 | 2026-11-28 02:04:32.288 | Flag / Remote Config Deleted: checkout_button_colour | Feature state 13, Development |

What the linked history records show each write changed:

- Id 75 (14:34:04.749): feature 13 created (name=checkout_button_colour, default_enabled=False, is_archived=False).
- Id 76 (14:34:04.838): feature state 13 created (enabled=False).
- Id 77 (14:34:05.046): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 78 (14:34:05.429): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 79 (14:34:07.635): feature state 13: enabled False → True.
- Id 80 (14:34:12.961): feature state 13: no field changed.
- Id 81 (14:34:13.644): environment value for option 'green': percentage_allocation 50 → 0.
- Id 82 (14:34:13.949): environment value for option 'blue': percentage_allocation 50 → 100.
- Id 83 (14:34:20.845): feature state 13: no field changed.
- Id 84 (14:34:26.264): feature state 13: no field changed.
- Id 85 (14:34:26.755): environment value for option 'green': percentage_allocation 0 → 50.
- Id 86 (14:34:27.043): environment value for option 'blue': percentage_allocation 100 → 50.
- Id 88 (02:04:32.452): feature 13 deleted.
- Id 89 (02:04:32.288): feature state 13 deleted.

### Capture pass (feature 14) — 2026-11-28

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 90 | 2026-11-28 02:06:21.097 | New Flag / Remote Config created: checkout_button_colour | Feature 14 |
| 91 | 2026-11-28 02:06:21.145 | New Flag / Remote Config created: checkout_button_colour | Feature state 14, Development |
| 92 | 2026-11-28 02:06:21.236 | Multivariate option added to feature 'checkout_button_colour'. | Feature 14 |
| 93 | 2026-11-28 02:06:21.328 | Multivariate option added to feature 'checkout_button_colour'. | Feature 14 |
| 94 | 2026-11-28 02:06:22.647 | Flag state updated for feature: checkout_button_colour | Feature state 14, Development |
| 95 | 2026-11-28 02:06:35.451 | Flag state updated for feature: checkout_button_colour | Feature state 14, Development |
| 96 | 2026-11-28 02:06:35.538 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 14, Development |
| 97 | 2026-11-28 02:06:35.572 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 14, Development |
| 99 | 2026-11-28 02:06:52.041 | Flag / Remote Config updated: checkout_button_colour | Feature 14 |
| 101 | 2026-11-28 02:08:56.432 | Flag / Remote Config Deleted: checkout_button_colour | Feature 14 |
| 102 | 2026-11-28 02:08:56.356 | Flag / Remote Config Deleted: checkout_button_colour | Feature state 14, Development |

What the linked history records show each write changed:

- Id 90 (02:06:21.097): feature 14 created (name=checkout_button_colour, default_enabled=False, is_archived=False).
- Id 91 (02:06:21.145): feature state 14 created (enabled=False).
- Id 92 (02:06:21.236): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 93 (02:06:21.328): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 94 (02:06:22.647): feature state 14: enabled False → True.
- Id 95 (02:06:35.451): feature state 14: no field changed.
- Id 96 (02:06:35.538): environment value for option 'green': percentage_allocation 50 → 0.
- Id 97 (02:06:35.572): environment value for option 'blue': percentage_allocation 50 → 100.
- Id 99 (02:06:52.041): feature 14: is_archived False → True.
- Id 101 (02:08:56.432): feature 14 deleted.
- Id 102 (02:08:56.356): feature state 14 deleted.

### Capture pass (feature 15) — 2026-11-28

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 103 | 2026-11-28 02:09:05.021 | New Flag / Remote Config created: checkout_button_colour | Feature 15 |
| 104 | 2026-11-28 02:09:05.062 | New Flag / Remote Config created: checkout_button_colour | Feature state 15, Development |
| 105 | 2026-11-28 02:09:05.127 | Multivariate option added to feature 'checkout_button_colour'. | Feature 15 |
| 106 | 2026-11-28 02:09:05.236 | Multivariate option added to feature 'checkout_button_colour'. | Feature 15 |
| 107 | 2026-11-28 02:09:06.630 | Flag state updated for feature: checkout_button_colour | Feature state 15, Development |
| 108 | 2026-11-28 02:10:44.604 | Flag state updated for feature: checkout_button_colour | Feature state 15, Development |
| 109 | 2026-11-28 02:10:44.710 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 15, Development |
| 110 | 2026-11-28 02:10:44.748 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 15, Development |
| 112 | 2026-11-28 02:35:58.008 | Flag / Remote Config Deleted: checkout_button_colour | Feature 15 |
| 113 | 2026-11-28 02:35:57.959 | Flag / Remote Config Deleted: checkout_button_colour | Feature state 15, Development |

What the linked history records show each write changed:

- Id 103 (02:09:05.021): feature 15 created (name=checkout_button_colour, default_enabled=False, is_archived=False).
- Id 104 (02:09:05.062): feature state 15 created (enabled=False).
- Id 105 (02:09:05.127): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 106 (02:09:05.236): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 107 (02:09:06.630): feature state 15: enabled False → True.
- Id 108 (02:10:44.604): feature state 15: no field changed.
- Id 109 (02:10:44.710): environment value for option 'green': percentage_allocation 50 → 0.
- Id 110 (02:10:44.748): environment value for option 'blue': percentage_allocation 50 → 100.
- Id 112 (02:35:58.008): feature 15 deleted.
- Id 113 (02:35:57.959): feature state 15 deleted.

### Capture pass (feature 16) — 2026-11-28

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 114 | 2026-11-28 02:36:19.380 | New Flag / Remote Config created: checkout_button_colour | Feature 16 |
| 115 | 2026-11-28 02:36:19.427 | New Flag / Remote Config created: checkout_button_colour | Feature state 16, Development |
| 116 | 2026-11-28 02:36:19.500 | Multivariate option added to feature 'checkout_button_colour'. | Feature 16 |
| 117 | 2026-11-28 02:36:19.564 | Multivariate option added to feature 'checkout_button_colour'. | Feature 16 |
| 118 | 2026-11-28 02:36:20.431 | Flag state updated for feature: checkout_button_colour | Feature state 16, Development |
| 119 | 2026-11-28 02:36:42.612 | Flag / Remote Config Deleted: checkout_button_colour | Feature 16 |
| 120 | 2026-11-28 02:36:42.563 | Flag / Remote Config Deleted: checkout_button_colour | Feature state 16, Development |

What the linked history records show each write changed:

- Id 114 (02:36:19.380): feature 16 created (name=checkout_button_colour, default_enabled=False, is_archived=False).
- Id 115 (02:36:19.427): feature state 16 created (enabled=False).
- Id 116 (02:36:19.500): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 117 (02:36:19.564): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 118 (02:36:20.431): feature state 16: enabled False → True.
- Id 119 (02:36:42.612): feature 16 deleted.
- Id 120 (02:36:42.563): feature state 16 deleted.

### Capture pass (feature 17) — 2026-11-28

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 121 | 2026-11-28 02:36:49.169 | New Flag / Remote Config created: checkout_button_colour | Feature 17 |
| 122 | 2026-11-28 02:36:49.186 | New Flag / Remote Config created: checkout_button_colour | Feature state 17, Development |
| 123 | 2026-11-28 02:36:49.224 | Multivariate option added to feature 'checkout_button_colour'. | Feature 17 |
| 124 | 2026-11-28 02:36:49.324 | Multivariate option added to feature 'checkout_button_colour'. | Feature 17 |
| 125 | 2026-11-28 02:36:50.562 | Flag state updated for feature: checkout_button_colour | Feature state 17, Development |
| 126 | 2026-11-28 02:36:55.983 | Flag state updated for feature: checkout_button_colour | Feature state 17, Development |
| 127 | 2026-11-28 02:36:56.065 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 17, Development |
| 128 | 2026-11-28 02:36:56.100 | Multivariate value changed for feature 'checkout_button_colour'. | Feature state 17, Development |
| 147 | 2026-11-28 04:11:56.367 | Flag / Remote Config Deleted: checkout_button_colour | Feature 17 |
| 148 | 2026-11-28 04:11:56.155 | Flag / Remote Config Deleted: checkout_button_colour | Feature state 17, Development |

What the linked history records show each write changed:

- Id 121 (02:36:49.169): feature 17 created (name=checkout_button_colour, default_enabled=False, is_archived=False).
- Id 122 (02:36:49.186): feature state 17 created (enabled=False).
- Id 123 (02:36:49.224): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 124 (02:36:49.324): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 125 (02:36:50.562): feature state 17: enabled False → True.
- Id 126 (02:36:55.983): feature state 17: no field changed.
- Id 127 (02:36:56.065): environment value for option 'green': percentage_allocation 50 → 0.
- Id 128 (02:36:56.100): environment value for option 'blue': percentage_allocation 50 → 100.
- Id 147 (04:11:56.367): feature 17 deleted.
- Id 148 (04:11:56.155): feature state 17 deleted.

### Video capture pass (feature 20) — 2026-11-28

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 150 | 2026-11-28 04:12:46.260 | New Flag / Remote Config created: checkout_button_colour | Feature 20 |
| 151 | 2026-11-28 04:12:46.274 | New Flag / Remote Config created: checkout_button_colour | Feature state 20, Development |
| 152 | 2026-11-28 04:12:46.308 | Multivariate option added to feature 'checkout_button_colour'. | Feature 20 |
| 153 | 2026-11-28 04:12:46.389 | Multivariate option added to feature 'checkout_button_colour'. | Feature 20 |
| 154 | 2026-11-28 04:12:47.257 | Flag state updated for feature: checkout_button_colour | Feature state 20, Development |
| 155 | 2026-11-28 04:12:50.655 | Flag state updated for feature: checkout_button_colour | Feature state 20, Development |
| 156 | 2026-11-28 04:12:51.102 | Flag / Remote Config updated: checkout_button_colour | Feature 20 |

What the linked history records show each write changed:

- Id 150 (04:12:46.260): feature 20 created (name=checkout_button_colour, default_enabled=False, is_archived=False).
- Id 151 (04:12:46.274): feature state 20 created (enabled=False).
- Id 152 (04:12:46.308): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 153 (04:12:46.389): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 154 (04:12:47.257): feature state 20: enabled False → True.
- Id 155 (04:12:50.655): feature state 20: enabled True → False.
- Id 156 (04:12:51.102): feature 20: is_archived False → True.

Notes on the main session (feature 10), from the records:

- Id 51 is the rollback of the apply: feature 10: is_archived False → True. The snapshot taken at apply time recorded that the flag did not exist beforehand, and at that time the app implemented rollback of an apply-created flag as an archive only. What that restored was the pre-apply situation in the flag list — no live flag under that name — but the flag's enabled state was left untouched. What that means for SDK clients is measured in the `signup_button_label` section below.
- Id 52, about two minutes later: feature state 10: no field changed. It changed nothing and restored nothing; in particular it did not restore the 50/50 split. It is consistent with a dashboard "Update Feature Value" save during the panel capture — that action rewrites the state with identical values — but the records do not identify which call produced this write, and this extract does not guess.
- On timing: the graduate's audit entries (ids 47–49, at 13:57:43.944, 13:57:44.223, 13:57:44.423) trail the feature-level option writes recorded in the option history (13:57:43.057, 13:57:43.238) by roughly a second. The two are different records of the same step: the option allocations are written first, and the environment values and their audit entries follow. Both sets of timestamps are printed from their own tables; neither is adjusted to match the other.
- Feature 13 is the end-to-end rollback proof from the recorded session: create, enable, graduate to green 0 / blue 100, then rollback — its linked records show the split going back to 50/50, because the snapshot was taken before the graduate ran.
- Feature 20 is the pass recorded for the current video cut, driven through the app with the fixed rollback: its last two entries are the rollback of the apply, and their linked records show the fixed order — the state write disables the flag first, the archive follows. The flags table at the end of the video shows the result: `checkout_button_colour` — Disabled (archived).

## Pre-fix measurement: `signup_button_label` (feature 18)

Run on 2026-11-28 with the pre-fix build, to settle what an archive-only rollback of an apply-created flag leaves behind. The copilot created the flag through its own API (20% rollout step, so enabled), then rolled the apply back. The rollback's only write is the final entry below:

### Audit entries

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 130 | 2026-11-28 04:06:25.452 | New Flag / Remote Config created: signup_button_label | Feature 18 |
| 131 | 2026-11-28 04:06:25.542 | New Flag / Remote Config created: signup_button_label | Feature state 18, Development |
| 132 | 2026-11-28 04:06:25.720 | Multivariate option added to feature 'signup_button_label'. | Feature 18 |
| 133 | 2026-11-28 04:06:25.819 | Multivariate option added to feature 'signup_button_label'. | Feature 18 |
| 134 | 2026-11-28 04:06:26.377 | Flag state updated for feature: signup_button_label | Feature state 18, Development |
| 135 | 2026-11-28 04:06:32.665 | Flag / Remote Config updated: signup_button_label | Feature 18 |

What the linked history records show each write changed:

- Id 130 (04:06:25.452): feature 18 created (name=signup_button_label, default_enabled=False, is_archived=False).
- Id 131 (04:06:25.542): feature state 18 created (enabled=False).
- Id 132 (04:06:25.720): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 133 (04:06:25.819): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 134 (04:06:26.377): feature state 18: enabled False → True.
- Id 135 (04:06:32.665): feature 18: is_archived False → True.

After that rollback, the environment's SDK flags endpoint (`GET /api/v1/flags/` with the environment key — what SDK clients receive) was queried, and re-queried when this extract was generated (2026-11-28 04:17:01.743 UTC): the flag is still returned, with `enabled: true`. So an archived flag that was on keeps being served, on. Archive-only rollback did not take the created flag out of service; that is the defect the verification pass below fixes.

## Post-fix verification: `hero_banner_colour` (feature 19)

The same lifecycle with the fixed build: create through the copilot's API, enable at the 20% rollout step, graduate the simulated winner (blue) to 100%, then roll the apply back from its snapshot. Rollback of a flag the apply created now disables the environment state first and archives the flag second — the last two entries below, in that order:

### Audit entries

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 136 | 2026-11-28 04:07:49.674 | New Flag / Remote Config created: hero_banner_colour | Feature 19 |
| 137 | 2026-11-28 04:07:49.700 | New Flag / Remote Config created: hero_banner_colour | Feature state 19, Development |
| 138 | 2026-11-28 04:07:49.745 | Multivariate option added to feature 'hero_banner_colour'. | Feature 19 |
| 139 | 2026-11-28 04:07:49.789 | Multivariate option added to feature 'hero_banner_colour'. | Feature 19 |
| 140 | 2026-11-28 04:07:50.377 | Flag state updated for feature: hero_banner_colour | Feature state 19, Development |
| 141 | 2026-11-28 04:07:54.270 | Flag state updated for feature: hero_banner_colour | Feature state 19, Development |
| 142 | 2026-11-28 04:07:54.382 | Multivariate value changed for feature 'hero_banner_colour'. | Feature state 19, Development |
| 143 | 2026-11-28 04:07:54.416 | Multivariate value changed for feature 'hero_banner_colour'. | Feature state 19, Development |
| 144 | 2026-11-28 04:07:58.789 | Flag state updated for feature: hero_banner_colour | Feature state 19, Development |
| 145 | 2026-11-28 04:07:59.201 | Flag / Remote Config updated: hero_banner_colour | Feature 19 |

What the linked history records show each write changed:

- Id 136 (04:07:49.674): feature 19 created (name=hero_banner_colour, default_enabled=False, is_archived=False).
- Id 137 (04:07:49.700): feature state 19 created (enabled=False).
- Id 138 (04:07:49.745): option 'green' created (string_value=green, default_percentage_allocation=50).
- Id 139 (04:07:49.789): option 'blue' created (string_value=blue, default_percentage_allocation=50).
- Id 140 (04:07:50.377): feature state 19: enabled False → True.
- Id 141 (04:07:54.270): feature state 19: no field changed.
- Id 142 (04:07:54.382): environment value for option 'green': percentage_allocation 50 → 0.
- Id 143 (04:07:54.416): environment value for option 'blue': percentage_allocation 50 → 100.
- Id 144 (04:07:58.789): feature state 19: enabled True → False.
- Id 145 (04:07:59.201): feature 19: is_archived False → True.

After the rollback, the SDK flags endpoint was queried (and re-queried at generation time, 2026-11-28 04:17:01.743 UTC): the flag is still listed, with `enabled: false` — present in the response as an archived record, but no longer served enabled to any client.

## What this proves

- The audit log and the history tables agree entry for entry: every change described above is the diff of the history record the audit row itself links to, and the full raw export (`docs/audit-export.json`) lets anyone re-run the diff.
- The writes that changed nothing are reported as no-ops, not dressed up as steps: audit ids 31, 34, 35, 47, 52, 61, 71, 72, 80, 83, 84, 95, 108, 126, 141 have linked history records whose diff is empty.
- Rollback semantics are stated as measured, in both directions: archive-only rollback left a created flag served enabled (feature 18); disable-then-archive rollback leaves it served disabled (feature 19). Both were checked against the SDK flags endpoint, not inferred from the admin API.
- The entries' timing and shape match the copilot's API call sequence, and the recorded sessions were driven through the API. Per the Actor note, that conclusion rests on the session record and the pattern of the writes, not on the author field alone.

*Note: this self-hosted build's Audit Log page in the web UI is Enterprise-gated, which is why this extract is taken from the audit records themselves (database/API) instead of a UI screenshot.*

## Appendix — remaining audit entries

Every audit row not shown above (instance provisioning, the seeded flags' own history, the stale-check archives of `holiday_sale_banner_2025` that fall inside the featured sessions' windows, and a dashboard login during the 2026-11-28 capture passes). The complete log is in `docs/audit-export.json`.

| ID | Timestamp (UTC) | Entry | Object |
|----|-----------------|-------|--------|
| 1 | 2026-11-27 08:34:17.823 | User `demo@example.com` logged in without 2FA. | — |
| 2 | 2026-11-27 08:34:18.300 | User `demo@example.com` logged in without 2FA. | — |
| 3 | 2026-11-27 08:34:24.029 | User `demo@example.com` logged in without 2FA. | — |
| 4 | 2026-11-27 08:34:25.714 | New Environment created: Development | Environment 1 |
| 5 | 2026-11-27 08:34:42.364 | User `demo@example.com` logged in without 2FA. | — |
| 6 | 2026-11-27 08:34:42.973 | New Flag / Remote Config created: new_checkout_flow | Feature state 1, Development |
| 7 | 2026-11-27 08:34:42.914 | New Flag / Remote Config created: new_checkout_flow | Feature 1 |
| 8 | 2026-11-27 08:34:43.265 | New Flag / Remote Config created: pricing_page_redesign | Feature 2 |
| 9 | 2026-11-27 08:34:43.337 | New Flag / Remote Config created: pricing_page_redesign | Feature state 2, Development |
| 10 | 2026-11-27 08:34:43.749 | New Flag / Remote Config created: recommendations_v2 | Feature 3 |
| 11 | 2026-11-27 08:34:43.833 | New Flag / Remote Config created: recommendations_v2 | Feature state 3, Development |
| 12 | 2026-11-27 08:34:44.151 | New Flag / Remote Config created: legacy_search_v1 | Feature state 4, Development |
| 13 | 2026-11-27 08:34:44.134 | New Flag / Remote Config created: legacy_search_v1 | Feature 4 |
| 14 | 2026-11-27 08:34:44.443 | New Flag / Remote Config created: old_promo_banner | Feature 5 |
| 15 | 2026-11-27 08:34:44.530 | New Flag / Remote Config created: old_promo_banner | Feature state 5, Development |
| 16 | 2026-11-27 08:34:44.843 | New Flag / Remote Config created: holiday_sale_banner_2025 | Feature 6 |
| 17 | 2026-11-27 08:34:44.855 | New Flag / Remote Config created: holiday_sale_banner_2025 | Feature state 6, Development |
| 18 | 2026-11-27 08:34:45.231 | New Flag / Remote Config created: beta_dashboard_access | Feature 7 |
| 19 | 2026-11-27 08:34:45.248 | New Flag / Remote Config created: beta_dashboard_access | Feature state 7, Development |
| 20 | 2026-11-27 08:35:29.824 | New Flag / Remote Config created: checkout_button_colour | Feature 8 |
| 21 | 2026-11-27 08:35:29.841 | New Flag / Remote Config created: checkout_button_colour | Feature state 8, Development |
| 22 | 2026-11-27 08:35:29.877 | Multivariate option added to feature 'checkout_button_colour'. | Feature 8 |
| 23 | 2026-11-27 08:35:30.040 | Multivariate option added to feature 'checkout_button_colour'. | Feature 8 |
| 24 | 2026-11-27 08:49:55.038 | User `demo@example.com` logged in without 2FA. | — |
| 25 | 2026-11-27 10:05:09.437 | Flag state updated for feature: checkout_button_colour | Feature state 8, Development |
| 40 | 2026-11-27 13:54:54.450 | Flag / Remote Config Deleted: checkout_button_colour | Feature 8 |
| 41 | 2026-11-27 13:54:54.325 | Flag / Remote Config Deleted: checkout_button_colour | Feature state 8, Development |
| 50 | 2026-11-27 13:57:57.833 | Flag / Remote Config updated: holiday_sale_banner_2025 | Feature 6 |
| 87 | 2026-11-28 02:04:31.593 | Flag / Remote Config updated: holiday_sale_banner_2025 | Feature 6 |
| 98 | 2026-11-28 02:06:46.152 | Flag / Remote Config updated: holiday_sale_banner_2025 | Feature 6 |
| 100 | 2026-11-28 02:08:56.121 | Flag / Remote Config updated: holiday_sale_banner_2025 | Feature 6 |
| 111 | 2026-11-28 02:20:56.699 | User `demo@example.com` logged in without 2FA. | — |
| 129 | 2026-11-28 02:37:22.622 | Flag / Remote Config updated: holiday_sale_banner_2025 | Feature 6 |
| 146 | 2026-11-28 04:11:55.533 | Flag / Remote Config updated: holiday_sale_banner_2025 | Feature 6 |
| 149 | 2026-11-28 04:12:41.905 | Flag / Remote Config updated: holiday_sale_banner_2025 | Feature 6 |
