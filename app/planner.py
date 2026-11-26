"""Rule-based natural-language prompt to experiment plan parser.

Deterministic and dependency-free: the same prompt always produces the
same plan, and no external service is called. The parser recognises three
intents -- creating an experiment, cleaning up stale flags, and toggling
a flag -- and falls back to a plain flag-creation plan for anything else.

Example:
    >>> plan = parse_prompt(
    ...     "Test a new checkout button colour green vs blue "
    ...     "for 20% of users, success is checkout_completed"
    ... )
    >>> plan["flag_name"]
    'checkout_button_colour'
    >>> plan["traffic_percent"]
    20
    >>> plan["success_metric"]
    'checkout_completed'
"""

from __future__ import annotations

import re
from typing import Any

_STOPWORDS = {
    "a", "an", "the", "new", "test", "testing", "try", "please", "for",
    "of", "users", "user", "to", "with", "and", "or", "on", "in", "is",
    "success", "experiment", "run", "create", "add", "make", "launch",
    "roll", "rollout", "out", "my", "our", "we", "want", "i", "show",
    "give", "vs", "versus", "v", "a/b", "ab",
}
_COLOUR_WORDS = {
    "red", "blue", "green", "yellow", "orange", "purple", "pink", "black",
    "white", "grey", "gray", "teal", "indigo", "violet",
}
_HIGH_RISK_SURFACES = ("checkout", "payment", "pay", "billing", "auth",
                       "login", "signup", "sign_up", "pricing", "purchase")
_REVENUE_METRICS = ("checkout", "purchase", "payment", "revenue", "order",
                    "conversion", "signup", "sign_up", "subscription")


def _snake(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return re.sub(r"_+", "_", text)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:_[a-z0-9]+)*", text.lower())


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


_TRAFFIC_AUDIENCE = r"(?:users|traffic|audience|customers|visitors|people|signups|sign-ups|sessions)"


def _extract_traffic(text: str) -> int | float | None:
    """Extract a traffic share only when the prompt ties it to an audience.

    A bare ``N%`` (for example a discount, a conversion rate, or a score)
    is not a rollout share, so it only counts when it sits next to words
    such as "of users / traffic / audience / customers" or in a phrase
    like "roll out to N%". Values above 100 are returned unchanged so
    validation can flag them as an error instead of silently passing
    them through; values below 1 are clamped up to 1.
    """
    patterns = [
        rf"(\d+(?:\.\d+)?)\s*%\s+of\s+(?:the\s+)?{_TRAFFIC_AUDIENCE}\b",
        rf"(\d+(?:\.\d+)?)\s*percent\s+of\s+(?:the\s+)?{_TRAFFIC_AUDIENCE}\b",
        rf"\broll(?:ing|ed)?\s*out\s+to\s+(\d+(?:\.\d+)?)\s*%",
        rf"\brollout\s+to\s+(\d+(?:\.\d+)?)\s*%",
        rf"\bto\s+(\d+(?:\.\d+)?)\s*%\s+of\s+(?:the\s+)?{_TRAFFIC_AUDIENCE}\b",
        rf"(\d+(?:\.\d+)?)\s*%\s+(?:of\s+)?(?:the\s+)?(?:total\s+)?traffic\b",
        rf"(\d+(?:\.\d+)?)\s*%\s+{_TRAFFIC_AUDIENCE}\b",
        rf"(\d+(?:\.\d+)?)\s*%\s+rollout\b",
    ]
    match = None
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            break
    if not match:
        return None
    value = float(match.group(1))
    if value < 1:
        value = 1.0
    return int(value) if float(value).is_integer() else value


def _extract_metric(text: str) -> str | None:
    patterns = [
        r"success\s+(?:is|metric\s+is|means)\s+([a-z][a-z0-9_]*)",
        r"success\s+metric\s*[:=]?\s*([a-z][a-z0-9_]*)",
        r"measured\s+by\s+([a-z][a-z0-9_]*)",
        r"metric\s+is\s+([a-z][a-z0-9_]*)",
        r"optimise\s+for\s+([a-z][a-z0-9_]*)",
        r"optimize\s+for\s+([a-z][a-z0-9_]*)",
        r"goal\s+is\s+([a-z][a-z0-9_]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    # A bare snake_case event name anywhere in the prompt is the metric.
    for token in _tokens(text):
        if "_" in token and token not in {"sign_up"}:
            return token
    return None


def _variant_from_side(segment: str, *, is_last: bool) -> str | None:
    """Resolve one side of a ``vs`` comparison to a single variant value.

    A side that resolves to just the word colour/color falls back to the
    preceding meaningful token, so a variant is never literally named
    "colour" or "color".
    """
    if is_last:
        segment = re.split(
            r"\bfor\b|\bto\b|\bwith\b|,|\.|success|traffic", segment
        )[0].strip()
    words = _tokens(segment)
    if not words:
        return None
    if is_last:
        if words[0] in {"colour", "color"}:
            return words[1] if len(words) > 1 else None
        return words[0]
    if "colour" in words or "color" in words:
        idx = max(i for i, w in enumerate(words) if w in {"colour", "color"})
        if idx + 1 < len(words):
            return words[idx + 1]
        # The side ends in (or is) the word colour/color: fall back to
        # the preceding meaningful token.
        for candidate in reversed(words[:idx]):
            if candidate not in _STOPWORDS:
                return candidate
        return None
    return words[-1]


def _extract_variants(text: str) -> list[str]:
    """Extract the compared values from an ``X vs Y [vs Z ...]`` phrase."""
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
    if len(quoted) >= 2 and re.search(r"\bvs\.?\b|\bversus\b", text):
        values = [q.strip() for q in quoted]
        values = [v for v in values if v.lower() not in {"colour", "color"}]
        return list(dict.fromkeys(values)) if len(values) >= 2 else []

    parts = re.split(r"\s+(?:vs\.?|versus)\s+", text)
    if len(parts) < 2:
        return []
    variants: list[str] = []
    for index, part in enumerate(parts):
        value = _variant_from_side(part, is_last=index == len(parts) - 1)
        if value and value not in {"colour", "color"} and value not in variants:
            variants.append(value)
    return variants if len(variants) >= 2 else []


def _derive_flag_name(text: str, variants: list[str]) -> str:
    """Build a snake_case flag name from the subject of the prompt."""
    subject = re.split(r"\bvs\.?\b|\bversus\b", text)[0]
    subject = re.split(
        r",|\bfor\s+\d|\bsuccess\b", subject
    )[0]
    words: list[str] = []
    for word in _tokens(subject):
        if word in _STOPWORDS or word in variants:
            continue
        if "_" in word:  # event names are metrics, not flag subjects
            continue
        words.append(word)
    # Keep the name short and stable: at most four meaningful words.
    words = words[:4]
    if not words:
        words = ["feature", "experiment"]
    return _snake("_".join(words))


def _extract_flag_reference(text: str) -> str | None:
    """Find an explicit flag name (snake_case) or a quoted name."""
    quoted = re.findall(r"['\"]([a-z][a-z0-9_ ]+)['\"]", text)
    if quoted:
        return _snake(quoted[0])
    for token in _tokens(text):
        if "_" in token:
            return token
    return None


# ---------------------------------------------------------------------------
# Guardrails and rollout
# ---------------------------------------------------------------------------


def _guardrails(
    flag_name: str,
    traffic: int | float | None,
    metric: str | None,
    variants: list[str],
) -> list[dict[str, Any]]:
    guardrails: list[dict[str, Any]] = []

    def add(rule_id: str, name: str, severity: str, description: str, action: str) -> None:
        guardrails.append({
            "id": rule_id, "name": name, "severity": severity,
            "description": description, "action": action, "triggered": True,
        })

    if traffic is not None and traffic > 50:
        add("high_traffic_share", "High traffic share", "warning",
            f"Requested share is {traffic}%, above the 50% caution threshold.",
            "Start at 5-10% and ramp in stages instead of launching at full share.")
    elif traffic is not None and traffic > 25:
        add("staged_rollout_required", "Staged rollout required", "info",
            f"Requested share is {traffic}%, so a staged ramp is required.",
            "Ramp through each rollout step and check the guardrail metric at each step.")
    if metric is None:
        add("missing_success_metric", "Missing success metric", "warning",
            "No success metric or event was named in the prompt.",
            "Pick a primary event before launch so the result can be judged.")
    if metric and any(k in metric for k in _REVENUE_METRICS):
        add("revenue_affecting_experiment", "Revenue-affecting experiment", "warning",
            f"Success metric '{metric}' touches checkout or revenue.",
            "Add an error-rate and revenue kill switch; stop automatically on a drop.")
        add("kill_switch_required", "Kill switch required", "warning",
            "A revenue-affecting test must be stoppable in one step.",
            "Keep the flag off-switch ready and name an owner for the stop decision.")
    if any(k in flag_name for k in _HIGH_RISK_SURFACES):
        add("high_risk_surface", "High-risk surface", "info",
            f"Flag '{flag_name}' affects a high-risk surface.",
            "Require a staged rollout and monitor errors during the first step.")
    if len(variants) >= 2:
        add("minimum_runtime", "Minimum runtime", "info",
            "Experiments need enough observations before a winner is called.",
            "Run for at least 7 days or until each variant has enough events, whichever is later.")
    if traffic is not None and traffic <= 5:
        add("low_traffic_share", "Low traffic share", "info",
            f"Requested share is only {traffic}%; results will accumulate slowly.",
            "Expect a longer runtime before the success metric is conclusive.")
    return guardrails


def _rollout_steps(traffic: int | float | None) -> list[dict[str, Any]]:
    target = traffic if traffic is not None else 10
    stages: list[int | float] = []
    for candidate in (5, target, 50, 100):
        value = int(candidate) if float(candidate).is_integer() else candidate
        if not stages or value > stages[-1]:
            if value <= 100:
                stages.append(value)
        if value == 100:
            break
    steps: list[dict[str, Any]] = []
    for index, share in enumerate(stages, start=1):
        if index == 1:
            note = "Internal / canary step: enable for a small share and check errors."
            hold = "at least 24 hours"
        elif share == target:
            note = f"Experiment step: hold at the requested {share}% share and collect the success metric."
            hold = "at least 7 days or until each variant has enough events"
        elif share == 100:
            note = "Full rollout: ship the winning variant to everyone, then clean up the flag."
            hold = "until the losing variant is removed"
        else:
            note = f"Ramp step: widen to {share}% after the guardrail check passes."
            hold = "at least 48 hours"
        steps.append({
            "step": index, "traffic_percent": share,
            "description": note, "hold": hold,
        })
    return steps


_KNOWN_WORDS = _STOPWORDS | _COLOUR_WORDS | {
    "flag", "feature", "experiment", "toggle", "enable", "disable",
    "enabled", "disabled", "activate", "deactivate", "switch", "stale",
    "cleanup", "clean", "archive", "old", "unused", "checkout", "button",
    "colour", "color", "dark", "mode", "banner", "dashboard", "search",
    "pricing", "payment", "onboarding", "homepage", "header", "footer",
    "page", "flow", "redesign", "variant", "variants", "traffic",
    "metric", "hypothesis", "rollout", "audience", "customers",
    "visitors", "conversion", "retention", "activation", "revenue",
}


def _looks_like_gibberish(lowered: str) -> bool:
    """True when a prompt carries no recognisable intent or vocabulary."""
    tokens = _tokens(lowered)
    if not tokens:
        return True
    if any("_" in token for token in tokens):
        return False
    if re.search(r"\bvs\.?\b|\bversus\b|\d", lowered):
        return False
    return not any(token in _KNOWN_WORDS for token in tokens)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_prompt(text: str) -> dict[str, Any]:
    """Parse a natural-language prompt into a structured experiment plan.

    Returns a plain dict. The ``intent`` field is one of
    ``create_experiment``, ``stale_cleanup``, ``toggle_flag``,
    ``create_flag`` or ``unknown``. Experiment plans include ``flag_name``,
    ``variants``, ``traffic_percent``, ``success_metric``, ``hypothesis``,
    ``rollout_steps`` and ``guardrails``.
    """
    raw = (text or "").strip()
    lowered = raw.lower()

    base: dict[str, Any] = {"raw_prompt": raw, "intent": "unknown"}

    # -- empty or gibberish ----------------------------------------------
    if not raw or _looks_like_gibberish(lowered):
        base.update({
            "intent": "unknown",
            "description": "The prompt could not be understood.",
            "hypothesis": "",
            "variants": [],
            "traffic_percent": None,
            "traffic_percentage": None,
            "success_metric": None,
            "success_event": None,
            "metric": None,
            "rollout_steps": [],
            "guardrails": [],
            "explicit_fields": [],
            "inferred_fields": [],
        })
        base["warnings"] = validate_plan(base)
        return base

    # -- stale cleanup --------------------------------------------------
    if any(k in lowered for k in (
        "stale", "clean up", "cleanup", "clean-up", "unused flag",
        "old flags", "audit flags", "archive old",
    )):
        base.update({
            "intent": "stale_cleanup",
            "flag_name": _extract_flag_reference(lowered) or "",
            "description": "Review flags that have not changed recently and "
                           "are receiving little or no traffic, then archive them.",
            "hypothesis": "",
            "variants": [],
            "traffic_percent": None,
            "traffic_percentage": None,
            "success_metric": None,
            "success_event": None,
            "metric": None,
            "rollout_steps": [
                {"step": 1, "traffic_percent": 0,
                 "description": "List stale flags with age and evaluation counts.",
                 "hold": "until reviewed"},
                {"step": 2, "traffic_percent": 0,
                 "description": "Confirm each stale flag is unreferenced, then archive it.",
                 "hold": "until the list is empty"},
            ],
            "guardrails": [{
                "id": "archive_requires_review", "name": "Archive requires review",
                "severity": "warning",
                "description": "Archiving is hard to reverse for SDK clients still reading the flag.",
                "action": "Check references before archiving any flag.",
                "triggered": True,
            }],
            "cleanup": {"stale_after_days": 90, "action": "archive"},
            "explicit_fields": [],
            "inferred_fields": ["cleanup"],
        })
        base["warnings"] = validate_plan(base)
        return base

    # -- flag toggle ------------------------------------------------------
    toggle_match = re.search(
        r"\b(turn on|turn off|enable|disable|activate|deactivate|toggle|switch on|switch off)\b",
        lowered,
    )
    experiment_hint = bool(
        re.search(r"\bvs\.?\b|\bversus\b|\btest\b|\bexperiment\b", lowered)
    )
    if toggle_match and not experiment_hint:
        phrase = toggle_match.group(1)
        if phrase == "toggle":
            # A bare "toggle X" names no target state: leave it genuinely
            # unspecified instead of treating it as a disable.
            target_state: bool | None = None
        else:
            target_state = phrase in {"turn on", "enable", "activate", "switch on"}
        flag_name = _extract_flag_reference(lowered) or _derive_flag_name(
            re.sub(r"\b(flag|feature)\b", "", lowered), []
        )
        if target_state is None:
            description = (
                f"Toggle flag '{flag_name}' (target state unspecified: "
                "the prompt does not say whether it should end up on or off)."
            )
            step_description = (
                f"Confirm whether '{flag_name}' should be enabled or "
                "disabled, then set it in the target environment."
            )
            toggle_traffic: int | None = None
            inferred: list[str] = []
            explicit: list[str] = ["flag_name"]
        else:
            description = f"Set flag '{flag_name}' to " \
                          f"{'enabled' if target_state else 'disabled'}."
            step_description = (
                f"Set '{flag_name}' to "
                f"{'enabled' if target_state else 'disabled'} in the target environment."
            )
            toggle_traffic = 100 if target_state else 0
            inferred = ["traffic_percent"]
            explicit = ["flag_name", "target_enabled"]
        base.update({
            "intent": "toggle_flag",
            "flag_name": flag_name,
            "description": description,
            "hypothesis": "",
            "variants": [],
            "traffic_percent": toggle_traffic,
            "traffic_percentage": toggle_traffic,
            "success_metric": None,
            "success_event": None,
            "metric": None,
            "target_enabled": target_state,
            "rollout_steps": [
                {"step": 1,
                 "traffic_percent": toggle_traffic,
                 "description": step_description,
                 "hold": "until verified"},
            ],
            "guardrails": _guardrails(flag_name, None, None, []),
            "explicit_fields": explicit,
            "inferred_fields": inferred,
        })
        base["warnings"] = validate_plan(base)
        return base

    # -- experiment / flag creation ---------------------------------------
    variants_raw = _extract_variants(lowered)
    traffic = _extract_traffic(lowered)
    metric = _extract_metric(lowered)
    flag_name = _derive_flag_name(lowered, variants_raw)
    is_experiment = bool(variants_raw) or experiment_hint

    variants: list[dict[str, Any]] = []
    if len(variants_raw) >= 2:
        # Default to an even split of the experiment traffic.
        share = round(100 / len(variants_raw), 2)
        remainder = round(100 - share * (len(variants_raw) - 1), 2)
        for index, value in enumerate(variants_raw):
            allocation = remainder if index == 0 else share
            variants.append({
                "name": "control" if index == 0 else f"variant_{chr(96 + index)}",
                "value": value,
                "allocation_percent": allocation,
                "default_percentage_allocation": allocation,
                "is_control": index == 0,
            })
    elif is_experiment:
        variants = [
            {"name": "control", "value": "off", "allocation_percent": 50,
             "default_percentage_allocation": 50, "is_control": True},
            {"name": "variant_a", "value": "on", "allocation_percent": 50,
             "default_percentage_allocation": 50, "is_control": False},
        ]

    if len(variants_raw) >= 2:
        hypothesis = (
            f"If users see the {flag_name.replace('_', ' ')} variant "
            f"'{variants_raw[1]}' instead of '{variants_raw[0]}', then "
            f"{metric or 'the primary success metric'} will improve because "
            f"the change is easier to notice and act on."
        )
    elif is_experiment:
        hypothesis = (
            f"If '{flag_name.replace('_', ' ')}' is enabled for the test group, "
            f"then {metric or 'the primary success metric'} will improve "
            f"compared with the control group."
        )
    else:
        hypothesis = ""

    # Which fields the prompt actually supplied, and which are defaults
    # this parser filled in. A missing success metric is never invented:
    # it stays empty so the guardrails can block on it.
    explicit_fields: list[str] = []
    inferred_fields: list[str] = []
    if traffic is not None:
        explicit_fields.append("traffic_percent")
    elif is_experiment:
        inferred_fields.append("traffic_percent")
    if metric is not None:
        explicit_fields.append("success_metric")
    if len(variants_raw) >= 2:
        explicit_fields.append("variants")
    elif is_experiment:
        inferred_fields.append("variants")
    if hypothesis:
        inferred_fields.append("hypothesis")

    base.update({
        "intent": "create_experiment" if is_experiment else "create_flag",
        "flag_name": flag_name,
        "description": raw,
        "hypothesis": hypothesis,
        "explicit_fields": explicit_fields,
        "inferred_fields": inferred_fields,
        "variants": variants,
        "control_variant": variants[0]["value"] if variants else None,
        "traffic_percent": traffic,
        "traffic_percentage": traffic,
        "success_metric": metric,
        "success_event": metric,
        "metric": metric,
        "rollout_steps": _rollout_steps(traffic) if is_experiment else [
            {"step": 1, "traffic_percent": traffic if traffic is not None else 0,
             "description": f"Create '{flag_name}' disabled, wire it into the code, then enable it.",
             "hold": "until verified"},
        ],
        "guardrails": _guardrails(flag_name, traffic, metric, variants_raw),
    })
    base["warnings"] = validate_plan(base)
    return base


def validate_plan(plan: dict[str, Any]) -> list[str]:
    """Return a list of human-readable warnings for a plan (empty if clean)."""
    warnings: list[str] = []
    if not isinstance(plan, dict):
        return ["plan must be a dict"]

    intent = plan.get("intent", "")
    flag_name = plan.get("flag_name") or ""

    if intent != "stale_cleanup":
        if not flag_name:
            warnings.append("flag_name is missing")
        elif not re.fullmatch(r"[a-z][a-z0-9_]*", flag_name):
            warnings.append(
                f"flag_name '{flag_name}' is not valid snake_case"
            )
        elif len(flag_name) > 64:
            warnings.append("flag_name is longer than 64 characters")

    traffic = plan.get("traffic_percent", plan.get("traffic_percentage"))
    if traffic is not None:
        if not isinstance(traffic, (int, float)) or not 0 <= traffic <= 100:
            warnings.append("traffic_percent must be between 0 and 100")

    variants = plan.get("variants") or []
    if intent == "create_experiment":
        if len(variants) < 2:
            warnings.append("an experiment needs at least two variants")
        else:
            allocations = [
                v.get("allocation_percent", v.get("default_percentage_allocation"))
                for v in variants if isinstance(v, dict)
            ]
            if allocations and all(isinstance(a, (int, float)) for a in allocations):
                if abs(sum(allocations) - 100) > 0.5:
                    warnings.append(
                        "variant allocations must sum to 100% "
                        f"(got {sum(allocations)})"
                    )
        if not plan.get("success_metric") and not plan.get("metric"):
            warnings.append("no success metric set; the result cannot be judged")
        if not plan.get("hypothesis"):
            warnings.append("hypothesis is missing")
        if traffic is None:
            warnings.append("traffic_percent is not set; a default share should be chosen")

    if intent == "toggle_flag" and "target_enabled" not in plan:
        warnings.append("toggle plan does not state the target state")

    if intent in {"create_experiment", "create_flag", "toggle_flag"}:
        if not plan.get("rollout_steps"):
            warnings.append("rollout_steps is empty")

    return warnings


__all__ = ["parse_prompt", "validate_plan"]
