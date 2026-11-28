"""Planner edge cases and stale-flag since-field rules."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.planner import parse_prompt, validate_plan
from app.stale import analyse_flags

NOW = datetime(2026, 11, 26, tzinfo=timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


def variant_values(plan):
    return [v["value"] for v in plan["variants"]]


# --- traffic extraction ---------------------------------------------------


def test_bare_percent_is_not_traffic():
    plan = parse_prompt(
        "Test a new checkout button colour green vs blue, "
        "the discount is 20%, success is checkout_completed"
    )
    assert plan["traffic_percent"] is None


def test_percent_of_users_is_traffic():
    plan = parse_prompt(
        "Test a new checkout button colour green vs blue "
        "for 20% of users, success is checkout_completed"
    )
    assert plan["traffic_percent"] == 20
    assert "traffic_percent" in plan["explicit_fields"]
    assert "traffic_percent" not in plan["inferred_fields"]


def test_roll_out_to_percent_is_traffic():
    plan = parse_prompt(
        "Test a new checkout button colour green vs blue, "
        "roll out to 30%, success is checkout_completed"
    )
    assert plan["traffic_percent"] == 30


def test_traffic_above_100_is_a_validation_error():
    plan = parse_prompt(
        "Test a new checkout button colour green vs blue "
        "for 150% of users, success is checkout_completed"
    )
    assert plan["traffic_percent"] == 150
    assert any("between 0 and 100" in w for w in validate_plan(plan))


def test_default_traffic_is_marked_inferred():
    plan = parse_prompt(
        "Test a new checkout button colour green vs blue, "
        "success is checkout_completed"
    )
    assert plan["traffic_percent"] is None
    assert "traffic_percent" in plan["inferred_fields"]


# --- variants ---------------------------------------------------------------


def test_three_variants_split_on_every_vs():
    plan = parse_prompt(
        "Test a new checkout button colour red vs blue vs green "
        "for 20% of users, success is checkout_completed"
    )
    assert variant_values(plan) == ["red", "blue", "green"]
    assert abs(sum(v["allocation_percent"] for v in plan["variants"]) - 100) < 0.5


def test_variant_is_never_named_colour():
    plan = parse_prompt(
        "Test a new checkout button green colour vs blue colour "
        "for 20% of users, success is checkout_completed"
    )
    assert "colour" not in variant_values(plan)
    assert "color" not in variant_values(plan)
    assert variant_values(plan) == ["green", "blue"]


def test_two_variants_still_work():
    plan = parse_prompt(
        "Test a new checkout button colour green vs blue "
        "for 20% of users, success is checkout_completed"
    )
    assert variant_values(plan) == ["green", "blue"]


# --- toggle -------------------------------------------------------------------


def test_bare_toggle_leaves_state_unspecified():
    plan = parse_prompt("Toggle dark_mode")
    assert plan["intent"] == "toggle_flag"
    assert plan["target_enabled"] is None
    assert plan["traffic_percent"] is None
    assert "unspecified" in plan["description"]


def test_explicit_disable_still_sets_state():
    plan = parse_prompt("Disable dark_mode")
    assert plan["target_enabled"] is False
    assert plan["traffic_percent"] == 0


# --- unknown prompts and metrics ----------------------------------------------


def test_empty_prompt_is_unknown_with_no_flag_name():
    plan = parse_prompt("")
    assert plan["intent"] == "unknown"
    assert not plan.get("flag_name")


def test_gibberish_prompt_is_unknown_with_no_flag_name():
    plan = parse_prompt("asdf qwer zxcv plugh")
    assert plan["intent"] == "unknown"
    assert not plan.get("flag_name")


def test_no_metric_is_invented():
    plan = parse_prompt(
        "Test a new checkout button colour green vs blue for 20% of users"
    )
    assert plan["success_metric"] is None
    assert "success_metric" not in plan["inferred_fields"]
    assert any(
        g["id"] == "missing_success_metric" for g in plan["guardrails"]
    )


def test_explicit_metric_is_marked_explicit():
    plan = parse_prompt(
        "Test a new checkout button colour green vs blue "
        "for 20% of users, success is checkout_completed"
    )
    assert plan["success_metric"] == "checkout_completed"
    assert "success_metric" in plan["explicit_fields"]


# --- stale: Flagsmith field names and since-fields -----------------------------


def test_flagsmith_created_date_and_last_modified_are_recognised():
    flags = [{
        "name": "flagsmith_shaped",
        "created_date": iso(200),
        "last_modified": iso(60),
        "last_evaluated_at": iso(60),
        "enabled": True,
        "rollout_percentage": 10,
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["score"] >= 60
    assert entry["recommended_action"] == "archive"


def test_full_rollout_without_since_field_only_scores_partial():
    flags = [{
        "name": "maybe_decided",
        "created_date": iso(60),
        "last_modified": iso(30),
        "last_evaluated_at": iso(0),
        "enabled": True,
        "rollout_percentage": 100,
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "keep"
    assert entry["score"] == 15
    assert any("is unverified" in reason for reason in entry["reasons"])


def test_full_rollout_with_explicit_since_gets_full_bonus():
    flags = [{
        "name": "decided",
        "created_date": iso(60),
        "last_modified": iso(30),
        "last_evaluated_at": iso(0),
        "enabled": True,
        "rollout_percentage": 100,
        "full_rollout_since": iso(30),
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "rollout_winner"
    assert entry["score"] >= 50


def test_full_rollout_with_day_count_gets_full_bonus():
    flags = [{
        "name": "decided_by_count",
        "created_at": iso(60),
        "last_evaluated_at": iso(0),
        "enabled": True,
        "rollout_percentage": 100,
        "days_at_full_rollout": 30,
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "rollout_winner"


def test_disabled_without_since_field_only_scores_partial():
    flags = [{
        "name": "maybe_disabled_long",
        "created_date": iso(80),
        "last_modified": iso(40),
        "last_evaluated_at": iso(0),
        "enabled": False,
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "keep"
    assert entry["safe_to_remove"] is False
    assert entry["score"] == 15
    assert any("is unverified" in reason for reason in entry["reasons"])


def test_disabled_with_day_count_gets_full_bonus():
    flags = [{
        "name": "disabled_by_count",
        "created_at": iso(80),
        "last_evaluated_at": iso(0),
        "enabled": False,
        "disabled_days": 45,
    }]
    (entry,) = analyse_flags(flags, now=NOW)
    assert entry["recommended_action"] == "archive"
    assert entry["safe_to_remove"] is True
