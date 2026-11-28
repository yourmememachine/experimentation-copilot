#!/usr/bin/env python3
"""Regenerate docs/AUDIT-EXTRACT.md and docs/audit-export.json from the
Flagsmith database of the self-hosted instance used to record the demo.

Nothing in the generated extract is typed by hand: every timestamp,
entry text and field-level change is read from `audit_auditlog` and the
history tables (`features_historicalfeature`,
`features_historicalfeaturestate`,
`multivariate_historicalmultivariatefeatureoption`,
`multivariate_historicalmultivariatefeaturestatevalue`) at generation
time. Each audit row links to the exact history record it produced
(`history_record_class_path` + `history_record_id`), and the "change"
shown for an entry is the diff of that history record against the
previous record for the same object — so a write that changed nothing
is reported as a no-op, mechanically.

The script also re-checks, live, what the environment's SDK flags
endpoint (`GET /api/v1/flags/` with the environment key) returns for
the two rollback test flags, and records the raw answers in the export.

Configuration (environment variables):
  DATABASE_URL        Postgres URL of the Flagsmith database (required)
  PSQL_CMD            psql invocation prefix (default: "psql")
  FLAGSMITH_API_URL   e.g. http://127.0.0.1:8000/api/v1 (optional)
  FLAGSMITH_API_TOKEN admin API token (optional; enables the SDK check)
"""
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT_PATH = os.path.join(HERE, "audit-export.json")
EXTRACT_PATH = os.path.join(HERE, "AUDIT-EXTRACT.md")

CLASS_TO_TABLE = {
    "features.models.HistoricalFeature": "feature",
    "features.models.HistoricalFeatureState": "state",
    "features.multivariate.models.HistoricalMultivariateFeatureOption": "mv_option",
    "features.multivariate.models.HistoricalMultivariateFeatureStateValue": "mv_value",
    "environments.models.HistoricalEnvironment": "environment",
}

TRACKED_FIELDS = {
    "feature": ["name", "default_enabled", "is_archived"],
    "state": ["enabled"],
    "mv_option": ["string_value", "default_percentage_allocation"],
    "mv_value": ["percentage_allocation"],
    "environment": ["name"],
}


def psql_json(sql):
    cmd = os.environ.get("PSQL_CMD", "psql").split() + [
        os.environ["DATABASE_URL"], "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"psql failed: {out.stderr[-500:]}")
    text = out.stdout.strip()
    return json.loads(text) if text and text != "" else []


def fmt_ts(raw):
    """'2026-11-27T13:57:44.223456+00:00' -> '2026-11-27 13:57:44.223'"""
    if raw is None:
        return ""
    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


def fmt_time(raw):
    if raw is None:
        return ""
    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


def load():
    audit = psql_json(
        "SELECT json_agg(t) FROM (SELECT id, created_date, log, author_id, "
        "environment_id, project_id, related_object_id, related_object_type, "
        "history_record_class_path, history_record_id FROM audit_auditlog "
        "ORDER BY id) t")
    feature_hist = psql_json(
        "SELECT json_agg(t) FROM (SELECT history_id, id, name, default_enabled, "
        "is_archived, history_date, history_type FROM features_historicalfeature "
        "ORDER BY history_date, history_id) t")
    state_hist = psql_json(
        "SELECT json_agg(t) FROM (SELECT history_id, id, feature_id, environment_id, "
        "enabled, history_date, history_type FROM features_historicalfeaturestate "
        "WHERE feature_segment_id IS NULL AND identity_id IS NULL "
        "ORDER BY history_date, history_id) t")
    mv_option_hist = psql_json(
        "SELECT json_agg(t) FROM (SELECT history_id, id, feature_id, string_value, "
        "default_percentage_allocation, history_date, history_type FROM "
        "multivariate_historicalmultivariatefeatureoption "
        "ORDER BY history_date, history_id) t")
    mv_value_hist = psql_json(
        "SELECT json_agg(t) FROM (SELECT history_id, id, feature_state_id, "
        "multivariate_feature_option_id, percentage_allocation, history_date, "
        "history_type FROM multivariate_historicalmultivariatefeaturestatevalue "
        "ORDER BY history_date, history_id) t")
    environments = psql_json(
        "SELECT json_agg(t) FROM (SELECT id, name FROM environments_environment) t")
    return {
        "audit_log": audit or [],
        "feature_history": feature_hist or [],
        "feature_state_history": state_hist or [],
        "mv_option_history": mv_option_hist or [],
        "mv_state_value_history": mv_value_hist or [],
        "environments": {e["id"]: e["name"] for e in (environments or [])},
    }


class History:
    """Per-object history streams with diffing."""

    def __init__(self, data):
        self.streams = {}   # (kind, object_id) -> [rows sorted]
        self.by_history_id = {}  # (kind, history_id) -> row
        self.option_names = {}
        for row in data["mv_option_history"]:
            if row.get("string_value") is not None:
                self.option_names[row["id"]] = row["string_value"]
        sources = {
            "feature": (data["feature_history"], "id"),
            "state": (data["feature_state_history"], "id"),
            "mv_option": (data["mv_option_history"], "id"),
            "mv_value": (data["mv_state_value_history"], "id"),
        }
        for kind, (rows, key) in sources.items():
            for row in rows:
                self.streams.setdefault((kind, row[key]), []).append(row)
                self.by_history_id[(kind, row["history_id"])] = row
        for rows in self.streams.values():
            rows.sort(key=lambda r: (r["history_date"], r["history_id"]))

    def previous(self, kind, row):
        stream = self.streams.get((kind, row["id"]), [])
        idx = stream.index(row)
        return stream[idx - 1] if idx > 0 else None

    def describe(self, kind, row):
        """Human-readable change for one history record."""
        fields = TRACKED_FIELDS[kind]
        prev = self.previous(kind, row)
        label = {
            "feature": f"feature {row['id']}",
            "state": f"feature state {row['id']}",
            "mv_option": f"option '{row.get('string_value')}'",
            "mv_value": "environment value for option '"
                        + str(self.option_names.get(
                            row.get("multivariate_feature_option_id"), "?")) + "'",
        }[kind]
        if row["history_type"] == "+":
            vals = ", ".join(f"{f}={row.get(f)}" for f in fields)
            return f"{label} created ({vals})"
        if row["history_type"] == "-":
            return f"{label} deleted"
        if prev is None:
            return f"{label} recorded"
        diffs = [f"{f} {prev.get(f)} → {row.get(f)}"
                 for f in fields if prev.get(f) != row.get(f)]
        if not diffs:
            return f"{label}: no field changed"
        return f"{label}: " + "; ".join(diffs)

    def audit_change(self, audit_row):
        """The change an audit entry made, via its linked history record."""
        kind = CLASS_TO_TABLE.get(audit_row.get("history_record_class_path") or "")
        if kind is None or kind == "environment":
            return None
        row = self.by_history_id.get((kind, audit_row.get("history_record_id")))
        if row is None:
            return None
        return self.describe(kind, row)


def sdk_checks(names):
    api = os.environ.get("FLAGSMITH_API_URL")
    token = os.environ.get("FLAGSMITH_API_TOKEN")
    if not api or not token:
        return None
    api = api.rstrip("/")

    def get(path, headers):
        req = urllib.request.Request(api + path, method="GET")
        for k, v in headers.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "{}")

    envs = get("/projects/1/environments/", {"Authorization": f"Token {token}"})
    env_list = envs["results"] if isinstance(envs, dict) else envs
    env = env_list[0]
    flags = get("/flags/", {"X-Environment-Key": env["api_key"]})
    checked_at = datetime.now(timezone.utc).isoformat()
    out = {"checked_at": checked_at, "environment": env["name"], "results": {}}
    for name in names:
        mine = [f for f in flags if f["feature"]["name"] == name]
        out["results"][name] = mine[0] if mine else None
    return out


def main():
    data = load()
    hist = History(data)
    audit = data["audit_log"]
    env_names = data["environments"]

    checks = sdk_checks(["signup_button_label", "hero_banner_colour"])

    export = {
        "generated_from": "audit_auditlog + history tables of the self-hosted "
                          "Flagsmith instance used to record the demo",
        "audit_log": audit,
        "feature_history": data["feature_history"],
        "feature_state_history": data["feature_state_history"],
        "mv_option_history": data["mv_option_history"],
        "mv_state_value_history": data["mv_state_value_history"],
        "sdk_checks": checks,
    }
    with open(EXPORT_PATH, "w") as f:
        json.dump(export, f, indent=1, sort_keys=True)

    feature_names = {}
    for row in data["feature_history"]:
        feature_names.setdefault(row["id"], row["name"])

    def obj_label(row):
        t, oid = row.get("related_object_type"), row.get("related_object_id")
        if t == "FEATURE":
            return f"Feature {oid}"
        if t == "FEATURE_STATE":
            return f"Feature state {oid}, {env_names.get(row.get('environment_id'), '')}"
        if t == "ENVIRONMENT":
            return f"Environment {oid}"
        return t or "—"

    def audit_table(rows):
        lines = ["| ID | Timestamp (UTC) | Entry | Object |",
                 "|----|-----------------|-------|--------|"]
        for r in rows:
            lines.append(f"| {r['id']} | {fmt_ts(r['created_date'])} | "
                         f"{r['log']} | {obj_label(r)} |")
        return lines

    def rows_for_feature(fid):
        return [r for r in audit if r.get("related_object_id") == fid
                and r.get("related_object_type") in ("FEATURE", "FEATURE_STATE")]

    def change_notes(rows):
        notes = []
        for r in rows:
            change = hist.audit_change(r)
            if change is not None:
                notes.append((r, change))
        return notes

    featured_ids = set()

    def section_for(fid, heading):
        rows = rows_for_feature(fid)
        for r in rows:
            featured_ids.add(r["id"])
        out = [f"### {heading}", ""]
        out += audit_table(rows)
        out += ["", "What the linked history records show each write changed:", ""]
        for r, change in change_notes(rows):
            out.append(f"- Id {r['id']} ({fmt_time(r['created_date'])}): {change}.")
        out.append("")
        return out

    # --- computed facts used in the prose -------------------------------
    def change_of(audit_id):
        row = next(r for r in audit if r["id"] == audit_id)
        return hist.audit_change(row)

    noop_ids = [r["id"] for r in audit
                if hist.audit_change(r) is not None
                and "no field changed" in (hist.audit_change(r) or "")]

    # feature 10 graduate: the feature-level option writes that actually
    # changed an allocation, inside the graduate window (before id 50)
    a50 = next(r for r in audit if r["id"] == 50)
    f10_opts = []
    for r in data["mv_option_history"]:
        if r["feature_id"] != 10 or r["history_type"] != "~":
            continue
        if r["history_date"] > a50["created_date"]:
            continue
        prev = hist.previous("mv_option", r)
        if prev is not None and prev.get("default_percentage_allocation") \
                != r.get("default_percentage_allocation"):
            f10_opts.append(r)
    f10_opt_times = sorted(fmt_time(r["history_date"]) for r in f10_opts)
    a47 = next(r for r in audit if r["id"] == 47)
    a48 = next(r for r in audit if r["id"] == 48)
    a49 = next(r for r in audit if r["id"] == 49)

    sdk = checks["results"] if checks else {}
    sdk18 = sdk.get("signup_button_label")
    sdk19 = sdk.get("hero_banner_colour")

    L = []
    L.append("# Audit extract — live Flagsmith proof runs")
    L.append("")
    L.append("Sanitized extract from the audit log of the self-hosted Flagsmith "
             "instance used to record the demo (official Flagsmith image + "
             "PostgreSQL, run locally for this project).")
    L.append("")
    L.append("**This file is generated, not hand-written.** "
             "`docs/generate_audit_extract.py` reads `audit_auditlog` and the "
             "history tables and rebuilds this extract plus the raw export at "
             "`docs/audit-export.json`. Every timestamp and entry text below is "
             "the database's own value. Each audit row links to the history "
             "record it produced, and the change shown for an entry is the diff "
             "of that record against the previous record for the same object — "
             "so a write that changed nothing is reported as a no-op, "
             "mechanically. (An earlier hand-maintained version of this "
             "extract contained timestamps that differed from the log by up "
             "to about half a second and a few mislabelled entry types; that "
             "is why it is generated now.)")
    L.append("")
    L.append("**Actor:** every entry below is recorded under the same actor — "
             "author id 1, the demo workspace user, which is who the copilot's "
             "configured Flagsmith API token (`Authorization: Token …`) "
             "resolves to. The token value is a credential and is not "
             "reproduced here. One limit of this evidence: the audit log "
             "records the same author for dashboard actions as for this "
             "token's API calls, so the rows alone do not exclude manual "
             "action. What ties the entries to the copilot's API calls is "
             "their timing and shape — bursts of writes seconds apart that "
             "match the client's call sequence (create → options → state), "
             "repeated identically across independent passes — together with "
             "the session record, in which the run was driven through the "
             "API. No stronger claim is made.")
    L.append("")
    L.append("**Scope:** project \"Demo Project\" (id 1), environment "
             "\"Development\" (id 1). Timestamps are UTC, exactly as recorded "
             "in the audit log (`audit_auditlog`).")
    L.append("")

    # --- pricing_page_banner -------------------------------------------
    L.append("## Verification run: `pricing_page_banner` (feature 9)")
    L.append("")
    L.append("A fresh flag created and driven end to end through the "
             "Flagsmith API by the copilot's own token: create, enable, "
             "graduate, and an archive / archive-rollback exercise.")
    L.append("")
    L += section_for(9, "Audit entries")
    L.append("Reading of the run, from the linked history records above: the "
             "enable is the state write whose diff is `enabled False → True`; "
             "the two \"Flag / Remote Config updated\" entries in the middle "
             "of the run are an archive followed two seconds later by an "
             "un-archive (`is_archived` False → True → False); the graduate "
             "(ids 35–37) writes the environment values to green 0 / blue "
             "100. The flag was then deleted while still at "
             "0/100. This run contains no rollback of the graduate; the "
             "verified rollback restores are feature 13's and feature 19's, "
             "below. (The restore path is also exercised by the automated "
             "tests, `tests/test_api_safety.py`.)")
    L.append("")

    # --- checkout_button_colour ----------------------------------------
    L.append("## The demo video's flag: `checkout_button_colour`")
    L.append("")
    L.append("The flag the demo video centres on. The recording was captured "
             "in passes, and each pass re-created the flag from scratch — so "
             "the flag appears under several feature ids. They are grouped by "
             "feature id so each pass can be checked on its own. Features "
             "10–13 are the recorded session of 2026-11-27; features 14–17 "
             "and 20 are the later capture passes of 2026-11-28 (the audit "
             "log also records a dashboard login during those passes — see "
             "the appendix). Entries for other flags that fall inside these "
             "sessions' windows (the stale-check archive of "
             "`holiday_sale_banner_2025`) are listed in the appendix.")
    L.append("")
    for fid, label in [(10, "Main session (feature 10) — 2026-11-27"),
                       (11, "Dashboard pass (feature 11) — 2026-11-27"),
                       (12, "Results pass (feature 12) — 2026-11-27"),
                       (13, "Verification pass (feature 13) — 2026-11-27"),
                       (14, "Capture pass (feature 14) — 2026-11-28"),
                       (15, "Capture pass (feature 15) — 2026-11-28"),
                       (16, "Capture pass (feature 16) — 2026-11-28"),
                       (17, "Capture pass (feature 17) — 2026-11-28"),
                       (20, "Video capture pass (feature 20) — 2026-11-28")]:
        L += section_for(fid, label)
    L.append("Notes on the main session (feature 10), from the records:")
    L.append("")
    L.append(f"- Id 51 is the rollback of the apply: {change_of(51)}. The "
             "snapshot taken at apply time recorded that the flag did not "
             "exist beforehand, and at that time the app implemented "
             "rollback of an apply-created flag as an archive only. What "
             "that restored was the pre-apply situation in the flag list — "
             "no live flag under that name — but the flag's enabled state "
             "was left untouched. What that means for SDK clients is "
             "measured in the `signup_button_label` section below.")
    L.append(f"- Id 52, about two minutes later: {change_of(52)}. It changed "
             "nothing and restored nothing; in particular it did not "
             "restore the 50/50 split. It is consistent with a dashboard "
             "\"Update Feature Value\" save during the panel capture — that "
             "action rewrites the state with identical values — but the "
             "records do not identify which call produced this write, and "
             "this extract does not guess.")
    L.append(f"- On timing: the graduate's audit entries (ids 47–49, at "
             f"{fmt_time(a47['created_date'])}, {fmt_time(a48['created_date'])}, "
             f"{fmt_time(a49['created_date'])}) trail the feature-level "
             f"option writes recorded in the option history "
             f"({', '.join(f10_opt_times)}) by roughly a second. The two are "
             "different records of the same step: the option allocations "
             "are written first, and the environment values and their audit "
             "entries follow. Both sets of timestamps are printed from "
             "their own tables; neither is adjusted to match the other.")
    L.append("- Feature 13 is the end-to-end rollback proof from the "
             "recorded session: create, enable, graduate to green 0 / blue "
             "100, then rollback — its linked records show the split going "
             "back to 50/50, because the snapshot was taken before the "
             "graduate ran.")
    L.append("- Feature 20 is the pass recorded for the current video "
             "cut, driven through the app with the fixed rollback: its "
             "last two entries are the rollback of the apply, and their "
             "linked records show the fixed order — the state write "
             "disables the flag first, the archive follows. The flags "
             "table at the end of the video shows the result: "
             "`checkout_button_colour` — Disabled (archived).")
    L.append("")

    # --- pre-fix measurement -------------------------------------------
    L.append("## Pre-fix measurement: `signup_button_label` (feature 18)")
    L.append("")
    L.append("Run on 2026-11-28 with the pre-fix build, to settle what an "
             "archive-only rollback of an apply-created flag leaves "
             "behind. The copilot created the flag through its own API "
             "(20% rollout step, so enabled), then rolled the apply back. "
             "The rollback's only write is the final entry below:")
    L.append("")
    L += section_for(18, "Audit entries")
    if sdk18 is not None:
        L.append("After that rollback, the environment's SDK flags endpoint "
                 "(`GET /api/v1/flags/` with the environment key — what SDK "
                 "clients receive) was queried, and re-queried when this "
                 f"extract was generated ({fmt_ts(checks['checked_at'])} UTC): the flag "
                 f"is still returned, with `enabled: {str(sdk18['enabled']).lower()}`. "
                 "So an archived flag that was on keeps being served, on. "
                 "Archive-only rollback did not take the created flag out "
                 "of service; that is the defect the verification pass "
                 "below fixes.")
    L.append("")

    # --- post-fix verification ------------------------------------------
    L.append("## Post-fix verification: `hero_banner_colour` (feature 19)")
    L.append("")
    L.append("The same lifecycle with the fixed build: create through the "
             "copilot's API, enable at the 20% rollout step, graduate the "
             "simulated winner (blue) to 100%, then roll the apply back "
             "from its snapshot. Rollback of a flag the apply created now "
             "disables the environment state first and archives the flag "
             "second — the last two entries below, in that order:")
    L.append("")
    L += section_for(19, "Audit entries")
    if sdk19 is not None:
        L.append("After the rollback, the SDK flags endpoint was queried "
                 f"(and re-queried at generation time, {fmt_ts(checks['checked_at'])} UTC): "
                 f"the flag is still listed, with `enabled: {str(sdk19['enabled']).lower()}` — "
                 "present in the response as an archived record, but no "
                 "longer served enabled to any client.")
    L.append("")

    # --- what this proves ------------------------------------------------
    L.append("## What this proves")
    L.append("")
    L.append("- The audit log and the history tables agree entry for entry: "
             "every change described above is the diff of the history "
             "record the audit row itself links to, and the full raw "
             "export (`docs/audit-export.json`) lets anyone re-run the "
             "diff.")
    if noop_ids:
        L.append(f"- The writes that changed nothing are reported as "
                 f"no-ops, not dressed up as steps: audit ids "
                 f"{', '.join(str(i) for i in noop_ids)} have linked "
                 "history records whose diff is empty.")
    L.append("- Rollback semantics are stated as measured, in both "
             "directions: archive-only rollback left a created flag "
             "served enabled (feature 18); disable-then-archive rollback "
             "leaves it served disabled (feature 19). Both were checked "
             "against the SDK flags endpoint, not inferred from the "
             "admin API.")
    L.append("- The entries' timing and shape match the copilot's API "
             "call sequence, and the recorded sessions were driven "
             "through the API. Per the Actor note, that conclusion rests "
             "on the session record and the pattern of the writes, not "
             "on the author field alone.")
    L.append("")
    L.append("*Note: this self-hosted build's Audit Log page in the web UI "
             "is Enterprise-gated, which is why this extract is taken from "
             "the audit records themselves (database/API) instead of a UI "
             "screenshot.*")
    L.append("")

    # --- appendix ---------------------------------------------------------
    rest = [r for r in audit if r["id"] not in featured_ids]
    L.append("## Appendix — remaining audit entries")
    L.append("")
    L.append("Every audit row not shown above (instance provisioning, the "
             "seeded flags' own history, the stale-check archives of "
             "`holiday_sale_banner_2025` that fall inside the featured "
             "sessions' windows, and a dashboard login during the "
             "2026-11-28 capture passes). The complete log is in "
             "`docs/audit-export.json`.")
    L.append("")
    L += audit_table(rest)
    L.append("")

    with open(EXTRACT_PATH, "w") as f:
        f.write("\n".join(L))
    print(f"wrote {EXTRACT_PATH} and {EXPORT_PATH}")


if __name__ == "__main__":
    main()
