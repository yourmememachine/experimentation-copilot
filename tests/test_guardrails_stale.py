"""Tests for the guardrail engine and stale-flag detection."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.guardrails import evaluate
from app.stale import analyse_flags

NOW = datetime(2026, 11, 26, tzinfo=timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


def valid_plan(**overrides):
    plan = {
        "name": "checkout_redesign_v2",
        "kind": "experiment",
        "traffic_percentage": 25,
        "metric": "checkout_conversion",
        "hypothesis": "A shorter checkout raises conversion.",
        "rollback_plan": {"flag_state_before": {"enabled": False}},
        "variants": [
            {"name": "control", "weight": 50},
            {"name": "treatment", "weight": 50},
        ],
    }
    plan.update(overrides)
    return plan


# --- guardrails ---------------------------------------------------------


def test_valid_plan_in_development_is_allowed():
    result = evaluate(valid_plan(), environment="development")
    assert result["allowed"] is True
    assert result["blocks"] == []
    assert result["requires_approval"] is False


def test_production_plan_without_approval_is_blocked():
    result = evaluate(valid_plan(), environment="production", approved=False)
    assert result["allowed"] is False
    assert result["requires_approval"] is True
    assert any("approval" in block.lower() for block in result["blocks"])


def test_production_plan_with_approval_is_allowed():
    result = evaluate(valid_plan(), environment="production", approved=True)
    assert result["allowed"] is True
    assert result["requires_approval"] is False


def test_production_proposal_only_warns_instead_of_blocking():
    result = evaluate(valid_plan(dry_run=True), environment="production")
    assert result["allowed"] is True
    assert result["requires_approval"] is True
    assert result["warnings"]


def test_traffic_above_50_warns_but_does_not_block():
    result = evaluate(
        valid_plan(traffic_percentage=60), environment="development"
    )
    assert result["allowed"] is True
    assert any("60" in warning for warning in result["warnings"])


def test_traffic_above_90_blocks_without_approval():
    result = evaluate(
        valid_plan(traffic_percentage=95), environment="development"
    )
    assert result["allowed"] is False
    assert result["requires_approval"] is True


def test_traffic_above_90_with_approval_only_warns():
    result = evaluate(
        valid_plan(traffic_percentage=95),
        environment="development",
        approved=True,
    )
    assert result["allowed"] is True
    assert result["warnings"]


def test_experiment_without_metric_is_blocked():
    plan = valid_plan()
    del plan["metric"]
    result = evaluate(plan, environment="development")
    assert result["allowed"] is False
    assert any("metric" in block.lower() for block in result["blocks"])


def test_experiment_without_hypothesis_is_blocked():
    plan = valid_plan(hypothesis="  ")
    result = evaluate(plan, environment="development")
    assert result["allowed"] is False
    assert any("hypothesis" in block.lower() for block in result["blocks"])


def test_plain_flag_plan_does_not_need_metric_or_hypothesis():
    plan = {
        "name": "dark_mode",
        "kind": "flag",
        "traffic_percentage": 10,
        "rollback_plan": {"enabled": False},
    }
    result = evaluate(plan, environment="development")
    assert result["allowed"] is True


def test_missing_rollback_plan_is_blocked():
    plan = valid_plan()
    del plan["rollback_plan"]
    result = evaluate(plan, environment="development")
    assert result["allowed"] is False
    assert any("rollback" in block.lower() for block in result["blocks"])


def test_previous_state_snapshot_counts_as_rollback_plan():
    plan = valid_plan()
    del plan["rollback_plan"]
    plan["previous_state"] = {"enabled": True, "traffic_percentage": 5}
    result = evaluate(plan, environment="development")
    assert result["allowed"] is True


def test_bad_flag_name_is_blocked():
    result = evaluate(valid_plan(name="Bad Name!"), environment="development")
    assert result["allowed"] is False
    assert any("naming convention" in block for block in result["blocks"])


def test_missing_flag_name_is_blocked():
    plan = valid_plan()
    del plan["name"]
    result = evaluate(plan, environment="development")
    assert result["allowed"] is False


def test_multivariate_weights_must_sum_to_100():
    plan = valid_plan(
        variants=[{"name": "a", "weight": 40}, {"name": "b", "weight": 40}]
    )
    result = evaluate(plan, environment="development")
    assert result["allowed"] is False
    assert any("sum to 100" in block for block in result["blocks"])


def test_multivariate_weights_as_mapping_sum_to_100():
    plan = valid_plan(variants={"control": 70, "treatment": 30})
    result = evaluate(plan, environment="development")
    assert result["allowed"] is True


# --- stale-flag detection -----------------------------------------------


def test_fresh_active_flag_is_kept():
    flags = [{
        "name": "new_banner",
        "created_at": iso(5),
        "last_evaluated_at": iso(0),
        "enabled": True,
        "rollout_percentage": 20,
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["flag"] == "new_banner"
    assert entry["score"] == 0
    assert entry["recommended_action"] == "keep"
    assert entry["safe_to_remove"] is False


def test_old_flag_with_no_recent_evaluations_is_archived():
    flags = [{
        "name": "forgotten_flag",
        "created_at": iso(200),
        "last_evaluated_at": iso(45),
        "evaluations_last_30d": 0,
        "enabled": True,
        "rollout_percentage": 10,
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["score"] >= 60
    assert entry["recommended_action"] == "archive"
    assert entry["safe_to_remove"] is True
    assert entry["reasons"]


def test_old_flag_still_evaluated_is_not_archived():
    flags = [{
        "name": "old_but_active",
        "created_at": iso(200),
        "last_evaluated_at": iso(1),
        "evaluations_last_30d": 500,
        "enabled": True,
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "keep"
    assert entry["safe_to_remove"] is False


def test_full_rollout_for_over_14_days_is_decided():
    flags = [{
        "name": "finished_experiment",
        "created_at": iso(60),
        "last_evaluated_at": iso(0),
        "enabled": True,
        "rollout_percentage": 100,
        "full_rollout_since": iso(30),
        "winner": "treatment",
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "rollout_winner"
    assert entry["safe_to_remove"] is False
    assert any("100% rollout" in reason for reason in entry["reasons"])


def test_full_rollout_recently_completed_is_kept():
    flags = [{
        "name": "just_decided",
        "created_at": iso(30),
        "last_evaluated_at": iso(0),
        "enabled": True,
        "rollout_percentage": 100,
        "full_rollout_since": iso(3),
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "keep"


def test_disabled_for_over_30_days_is_archived():
    flags = [{
        "name": "switched_off",
        "created_at": iso(80),
        "last_evaluated_at": iso(40),
        "enabled": False,
        "disabled_since": iso(40),
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "archive"
    assert entry["safe_to_remove"] is True


def test_recently_disabled_flag_is_kept():
    flags = [{
        "name": "paused_flag",
        "created_at": iso(80),
        "last_evaluated_at": iso(2),
        "enabled": False,
        "disabled_since": iso(2),
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "keep"


def test_results_are_sorted_by_score_then_name_deterministically():
    flags = [
        {"name": "fresh", "created_at": iso(2), "last_evaluated_at": iso(0),
         "enabled": True},
        {"name": "stale_b", "created_at": iso(200),
         "last_evaluated_at": iso(60), "enabled": True},
        {"name": "stale_a", "created_at": iso(200),
         "last_evaluated_at": iso(60), "enabled": True},
    ]
    first = analyse_flags(flags, now=NOW)
    second = analyse_flags(list(reversed(flags)), now=NOW)
    assert [entry["flag"] for entry in first] == ["stale_a", "stale_b", "fresh"]
    assert first == second


def test_never_evaluated_old_flag_is_stale():
    flags = [{
        "name": "never_used",
        "created_at": iso(120),
        "last_evaluated_at": None,
        "enabled": True,
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "archive"
    assert entry["score"] <= 100


def test_flag_without_evaluation_data_does_not_claim_an_evaluation_history():
    # Live Flagsmith feature payloads carry no evaluation counts and no
    # last-evaluated timestamp. The scorer must not present the absence
    # of that data as a measured "no evaluations in the last 30 days".
    flags = [{
        "name": "live_shaped_flag",
        "created_date": iso(210),
        "enabled": True,
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "archive"
    assert any("no evaluation data recorded" in reason
               for reason in entry["reasons"])
    assert not any("no evaluations in the last" in reason
                   for reason in entry["reasons"])


def test_unverified_disabled_duration_is_a_caveat_not_an_instruction():
    # The card may mark a flag safe to remove on the old-and-quiet
    # signal while noting the disabled duration is unverified; the
    # caveat must not read as an instruction to verify before archiving.
    flags = [{
        "name": "switched_off_unrecorded",
        "created_at": iso(200),
        "last_evaluated_at": iso(45),
        "evaluations_last_30d": 0,
        "enabled": False,
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["safe_to_remove"] is True
    assert any("how long it has been disabled is unverified" in reason
               for reason in entry["reasons"])
    assert not any("before archiving" in reason for reason in entry["reasons"])
