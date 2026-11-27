"""Simulation significance gate tests.

The reviewer caught the old simulator naming a "winner" from noise
(56/500 vs 60/500, p ~ 0.7). The winner recommendation is now gated on
a two-proportion z-test at alpha 0.05, and the simulated variants have
a real deterministic effect size so a conclusive run is conclusive.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main as main
from app.main import _two_proportion_p_value, _variants_of, h_simulate


def test_p_value_for_clear_effect_is_small():
    # The reviewer's example of a real effect: 45/500 vs 75/500.
    p = _two_proportion_p_value(45, 500, 75, 500)
    assert 0.001 < p < 0.01


def test_p_value_for_noise_is_large():
    # The old video's "winner": 56/500 vs 60/500 is pure noise.
    p = _two_proportion_p_value(56, 500, 60, 500)
    assert p > 0.5


def test_significant_run_recommends_winner_with_p_value():
    status, result = h_simulate(
        {"flag_name": "checkout_button_colour", "visitors": 1000})
    assert status == 200
    assert result["verdict_reason"] == "significant"
    assert result["significant"] is True
    assert result["recommended_winner"] == "green"
    assert result["compared_against"] == "blue"
    assert result["p_value"] is not None and result["p_value"] < 0.05


def test_noise_run_is_inconclusive_not_a_winner():
    original = main._variant_rate
    main._variant_rate = lambda flag, var, is_control=False: 0.12
    try:
        status, result = h_simulate(
            {"flag_name": "checkout_button_colour", "visitors": 1000})
    finally:
        main._variant_rate = original
    assert status == 200
    assert result["recommended_winner"] == "inconclusive"
    assert result["verdict_reason"] == "not_significant"
    assert result["significant"] is False
    assert result["p_value"] is not None and result["p_value"] >= 0.05


def test_low_sample_run_is_inconclusive():
    status, result = h_simulate(
        {"flag_name": "checkout_button_colour", "visitors": 60})
    assert status == 200
    assert result["total_conversions"] < 30
    assert result["recommended_winner"] == "inconclusive"
    assert result["verdict_reason"] == "insufficient_conversions"


def test_variants_of_reads_live_flagsmith_option_names():
    # Live Flagsmith options name the variant in "string_value", not
    # "value" — both variants used to collapse to the name "variant".
    flag = {"multivariate_options": [
        {"string_value": "green", "default_percentage_allocation": 50.0},
        {"string_value": "blue", "default_percentage_allocation": 50.0},
    ]}
    variants = _variants_of(flag)
    assert [v["name"] for v in variants] == ["green", "blue"]
    assert [v["allocation"] for v in variants] == [50.0, 50.0]
