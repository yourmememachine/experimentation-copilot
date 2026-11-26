"""Guardrail engine for experiment and feature-flag plans.

A *plan* is a plain ``dict`` describing a proposed change, for example::

    {
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

Field aliases are accepted for the common spellings (``rollout_percentage``
for ``traffic_percentage``, ``previous_state`` / ``snapshot`` for
``rollback_plan``, ``variations`` for ``variants``, and so on) so plans built
by hand, by a prompt parser, or from an existing flag payload all evaluate
the same way.

:func:`evaluate` never raises for a malformed plan: problems are reported in
the returned ``blocks`` / ``warnings`` lists instead. Standard library only.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["evaluate"]

# Lowercase words separated by single underscores or hyphens, starting with
# a letter: ``checkout_redesign_v2`` and ``new-onboarding`` pass, while
# ``Bad Name!``, ``9lives`` and ``double__under`` do not.
_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$")
_NAME_MIN_LENGTH = 3
_NAME_MAX_LENGTH = 64

_TRAFFIC_WARN_THRESHOLD = 50
_TRAFFIC_BLOCK_THRESHOLD = 90

_PRODUCTION = "production"


def _first(plan: dict, *keys: str) -> Any:
    """Return the first present, non-``None`` value among ``keys``."""
    for key in keys:
        if key in plan and plan[key] is not None:
            return plan[key]
    return None


def _is_truthy_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_content(value: Any) -> bool:
    """True for a non-empty string, mapping, sequence, or any other value."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) > 0
    return True


def _traffic_percentage(plan: dict) -> float | None:
    raw = _first(
        plan,
        "traffic_percentage",
        "rollout_percentage",
        "traffic_percent",
        "rollout_percent",
        "percentage",
        "traffic",
        "rollout",
    )
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _variant_weights(plan: dict) -> list[float] | None:
    """Extract multivariate weights, or ``None`` if the plan has none.

    Accepts a list of numbers, a list of mappings with a
    ``weight`` / ``percentage`` / ``allocation`` value, or a mapping of
    variant name to either a number or such a mapping.
    """
    raw = _first(plan, "variants", "variations", "multivariate", "arms")
    if raw is None:
        return None
    items: list[Any]
    if isinstance(raw, dict):
        items = list(raw.values())
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        return []
    weights: list[float] = []
    for item in items:
        value: Any = item
        if isinstance(item, dict):
            value = _first(item, "weight", "percentage", "allocation", "traffic_percentage")
        if isinstance(value, bool):
            return []
        try:
            weights.append(float(value))
        except (TypeError, ValueError):
            return []
    return weights


def _is_experiment(plan: dict) -> bool:
    if plan.get("is_experiment"):
        return True
    kind = _first(plan, "kind", "type", "plan_type", "action")
    if isinstance(kind, str) and "experiment" in kind.strip().lower():
        return True
    if isinstance(kind, str) and kind.strip().lower() in {"ab_test", "a/b_test", "multivariate"}:
        return True
    return _first(plan, "variants", "variations", "multivariate", "arms") is not None


def evaluate(plan: dict, *, environment: str = "production", approved: bool = False) -> dict:
    """Evaluate ``plan`` against every guardrail rule.

    Parameters
    ----------
    plan:
        The proposed experiment/flag change, as a plain dict.
    environment:
        Target environment name. ``"production"`` (any casing) is the
        guarded environment; other names are treated as non-production.
    approved:
        Whether a human has explicitly approved applying this plan.

    Returns
    -------
    dict
        ``{"allowed": bool, "blocks": [...], "warnings": [...],
        "requires_approval": bool}``. ``allowed`` is True only when
        ``blocks`` is empty. A plan that is a proposal only (``dry_run`` or
        ``propose_only`` set) is never blocked by the production rule, but
        still reports ``requires_approval`` for production.
    """
    blocks: list[str] = []
    warnings: list[str] = []
    requires_approval = False

    if not isinstance(plan, dict):
        return {
            "allowed": False,
            "blocks": ["Plan must be a mapping describing the proposed change."],
            "warnings": [],
            "requires_approval": False,
        }

    env_value = _first(plan, "environment", "target_environment")
    env = str(env_value if env_value is not None else environment).strip().lower()
    is_production = env == _PRODUCTION
    proposal_only = bool(plan.get("dry_run") or plan.get("propose_only"))

    # Rule 1: never auto-apply to production without explicit human approval.
    if is_production and not approved:
        requires_approval = True
        if proposal_only:
            warnings.append(
                "Production plan is proposal-only: a human must approve it "
                "before it can be applied."
            )
        else:
            blocks.append(
                "Production changes require explicit human approval before "
                "they can be applied."
            )

    # Rule 2: traffic cap — warn above 50%, block above 90% without approval.
    traffic = _traffic_percentage(plan)
    if traffic is not None:
        if traffic < 0 or traffic > 100:
            blocks.append(f"Traffic percentage must be between 0 and 100 (got {traffic:g}).")
        elif traffic > _TRAFFIC_BLOCK_THRESHOLD:
            if approved:
                warnings.append(
                    f"Traffic is {traffic:g}%, above the "
                    f"{_TRAFFIC_BLOCK_THRESHOLD}% cap; proceeding only because "
                    "the plan is approved."
                )
            else:
                requires_approval = True
                blocks.append(
                    f"Traffic of {traffic:g}% exceeds the "
                    f"{_TRAFFIC_BLOCK_THRESHOLD}% cap and requires explicit "
                    "human approval."
                )
        elif traffic > _TRAFFIC_WARN_THRESHOLD:
            warnings.append(
                f"Traffic is {traffic:g}%, above the "
                f"{_TRAFFIC_WARN_THRESHOLD}% warning threshold."
            )

    # Rule 3: an experiment needs a metric and a hypothesis first.
    if _is_experiment(plan):
        if not _is_truthy_text(_first(plan, "metric", "success_metric", "primary_metric")):
            blocks.append("Experiments require a metric before they can be created.")
        if not _is_truthy_text(_first(plan, "hypothesis", "experiment_hypothesis")):
            blocks.append("Experiments require a hypothesis before they can be created.")

    # Rule 4: every change needs a rollback plan (previous-state snapshot).
    rollback = _first(plan, "rollback_plan", "rollback", "previous_state", "snapshot")
    if not _has_content(rollback):
        blocks.append(
            "A rollback plan is required: include a snapshot of the previous "
            "state so the change can be reverted."
        )

    # Rule 5: flag naming convention.
    name = _first(plan, "name", "flag_name", "key", "flag_key")
    if not _is_truthy_text(name):
        blocks.append("A flag name is required.")
    else:
        name = name.strip()
        if len(name) < _NAME_MIN_LENGTH or len(name) > _NAME_MAX_LENGTH:
            blocks.append(
                f"Flag name {name!r} must be between {_NAME_MIN_LENGTH} and "
                f"{_NAME_MAX_LENGTH} characters long."
            )
        elif not _NAME_RE.match(name):
            blocks.append(
                f"Flag name {name!r} does not follow the naming convention: "
                "lowercase letters, digits, single underscores or hyphens, "
                "starting with a letter."
            )

    # Rule 6: multivariate weights must sum to 100.
    weights = _variant_weights(plan)
    if weights is not None:
        if not weights:
            blocks.append("Multivariate plans must define at least one variant with a weight.")
        elif any(weight < 0 for weight in weights):
            blocks.append("Multivariate variant weights cannot be negative.")
        elif abs(sum(weights) - 100.0) > 0.01:
            blocks.append(
                f"Multivariate weights must sum to 100 (got {sum(weights):g})."
            )

    return {
        "allowed": not blocks,
        "blocks": blocks,
        "warnings": warnings,
        "requires_approval": requires_approval,
    }
