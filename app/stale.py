"""Stale-flag detection.

Each flag is a plain ``dict`` such as::

    {
        "name": "old_checkout_banner",
        "created_at": "2026-05-01T00:00:00Z",
        "last_evaluated_at": "2026-06-10T00:00:00Z",
        "enabled": True,
        "rollout_percentage": 100,
        "full_rollout_since": "2026-10-01T00:00:00Z",
        "winner": "treatment",
    }

Timestamps may be ISO-8601 strings, ``datetime`` / ``date`` objects, or
epoch seconds. Durations may instead be given directly with fields such as
``days_at_full_rollout`` or ``days_disabled``.

Scoring is deterministic and capped at 100:

- older than 90 days with no evaluations in the last 30 days: +60
- at 100% rollout for more than 14 days (the experiment is decided): +50
- disabled for more than 30 days: +50
- partial signals (old alone, or quiet alone) score lower, so a fresh,
  actively evaluated flag scores 0.

When a flag carries no evaluation data at all — the live Flagsmith
case, whose feature payloads have no evaluation counts or
last-evaluated timestamps — quiet is inferred from age alone and the
reason says "no evaluation data recorded" rather than claiming an
evaluation history that was never measured.

Standard library only.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

__all__ = ["analyse_flags", "analyse_stale_flags", "analyze_flags", "analyse"]

_OLD_DAYS = 90
_QUIET_DAYS = 30
_FULL_ROLLOUT_DAYS = 14
_DISABLED_DAYS = 30

_SCORE_OLD_AND_QUIET = 60
_SCORE_DECIDED = 50
_SCORE_DISABLED = 50
_SCORE_PARTIAL = 15


def _first(flag: dict, *keys: str) -> Any:
    for key in keys:
        if key in flag and flag[key] is not None:
            return flag[key]
    return None


def _parse_time(value: Any) -> datetime | None:
    """Parse a timestamp into an aware UTC datetime, or return ``None``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif isinstance(value, (int, float)):
        try:
            parsed = datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _days_between(moment: datetime | None, now: datetime) -> float | None:
    if moment is None:
        return None
    return (now - moment).total_seconds() / 86400.0


def _duration_days(flag: dict, day_keys: tuple[str, ...], since_keys: tuple[str, ...],
                   now: datetime, fallback: datetime | None = None) -> float | None:
    """Resolve a duration in days from an explicit count or a start time."""
    for key in day_keys:
        raw = flag.get(key)
        if raw is not None and not isinstance(raw, bool):
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
    for key in since_keys:
        days = _days_between(_parse_time(flag.get(key)), now)
        if days is not None:
            return days
    return _days_between(fallback, now)


def _recent_evaluations(flag: dict) -> float | None:
    raw = _first(
        flag,
        "evaluations_last_30d",
        "evaluation_count_last_30d",
        "recent_evaluations",
        "evaluations_30d",
    )
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _rollout_percentage(flag: dict) -> float | None:
    raw = _first(flag, "rollout_percentage", "traffic_percentage", "rollout", "percentage")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _last_modified(flag: dict) -> datetime | None:
    """Last-edit time, recognising the Flagsmith field name directly."""
    return _parse_time(
        _first(flag, "last_modified", "last_modified_at", "updated_at", "updated")
    )


def _analyse_one(flag: dict, now: datetime) -> dict:
    name = _first(flag, "name", "key", "flag_name", "flag_key")
    label = name if isinstance(name, str) and name.strip() else flag

    created = _parse_time(
        _first(flag, "created_at", "created_date", "created", "creation_time")
    )
    age_days = _days_between(created, now)

    last_evaluated = _parse_time(
        _first(flag, "last_evaluated_at", "last_evaluation_at", "last_evaluated")
    )
    days_since_evaluation = _days_between(last_evaluated, now)
    recent = _recent_evaluations(flag)

    if recent is not None:
        quiet = recent <= 0
        quiet_basis = "count"
    elif last_evaluated is not None:
        quiet = days_since_evaluation is not None and days_since_evaluation > _QUIET_DAYS
        quiet_basis = "last_evaluated"
    else:
        # No evaluation data recorded at all. Quiet is inferred from the
        # absence of data once the flag is not new, and the reasons below
        # say so instead of claiming a measured evaluation history —
        # live Flagsmith feature payloads carry no evaluation counts or
        # last-evaluated timestamps, so this is the branch live mode
        # always takes.
        quiet = age_days is not None and age_days > _QUIET_DAYS
        quiet_basis = "no_data"
    old = age_days is not None and age_days > _OLD_DAYS

    reasons: list[str] = []
    score = 0

    if old and quiet:
        score += _SCORE_OLD_AND_QUIET
        if quiet_basis == "no_data":
            reasons.append(
                f"Older than {_OLD_DAYS} days with no evaluation data "
                f"recorded."
            )
        else:
            reasons.append(
                f"Older than {_OLD_DAYS} days with no evaluations in the last "
                f"{_QUIET_DAYS} days."
            )
    else:
        if old:
            score += _SCORE_PARTIAL
            reasons.append(f"Older than {_OLD_DAYS} days.")
        if quiet and age_days is not None and age_days > _QUIET_DAYS:
            score += _SCORE_PARTIAL
            if quiet_basis == "no_data":
                reasons.append("No evaluation data recorded.")
            else:
                reasons.append(f"No evaluations in the last {_QUIET_DAYS} days.")

    # Decided experiment: sitting at 100% rollout for over two weeks.
    # The full bonus requires an explicit since-field (full_rollout_since
    # or a day count); a last-edit or created timestamp alone only earns
    # a partial score with a "verify" reason.
    winner = _first(flag, "winner", "winning_variant", "multivariate_winner", "winner_variant")
    rollout = _rollout_percentage(flag)
    full_rollout_days = None
    if rollout is not None and rollout >= 100:
        full_rollout_days = _duration_days(
            flag,
            ("days_at_full_rollout", "full_rollout_days"),
            ("full_rollout_since", "full_rollout_at", "rollout_completed_at",
             "winner_declared_at"),
            now,
        )
    decided = full_rollout_days is not None and full_rollout_days > _FULL_ROLLOUT_DAYS
    if decided:
        score += _SCORE_DECIDED
        detail = f"At 100% rollout for more than {_FULL_ROLLOUT_DAYS} days"
        if winner:
            detail += f"; winning variant is {winner!r}"
        reasons.append(detail + " — the experiment is decided.")
    elif rollout is not None and rollout >= 100:
        fallback_days = _days_between(_last_modified(flag) or created, now)
        if fallback_days is not None and fallback_days > _FULL_ROLLOUT_DAYS:
            score += _SCORE_PARTIAL
            reasons.append(
                "At 100% rollout, but no explicit full-rollout start was "
                "recorded, so how long it has been at 100% is unverified."
            )

    # Switched off and left off. As above, the full bonus requires an
    # explicit disabled_since / disabled_days; timestamps alone verify.
    enabled = flag.get("enabled", True)
    disabled_long = False
    if enabled is False:
        disabled_days = _duration_days(
            flag,
            ("days_disabled", "disabled_days"),
            ("disabled_since", "disabled_at"),
            now,
        )
        disabled_long = disabled_days is not None and disabled_days > _DISABLED_DAYS
        if disabled_long:
            score += _SCORE_DISABLED
            reasons.append(f"Disabled for more than {_DISABLED_DAYS} days.")
        else:
            fallback_days = _days_between(_last_modified(flag) or created, now)
            if fallback_days is not None and fallback_days > _DISABLED_DAYS:
                score += _SCORE_PARTIAL
                reasons.append(
                    "Disabled, but no explicit disabled-since date was "
                    "recorded, so how long it has been disabled is "
                    "unverified."
                )

    score = min(score, 100)

    if decided:
        action = "rollout_winner"
    elif (old and quiet) or disabled_long:
        action = "archive"
    else:
        action = "keep"

    return {
        "flag": label,
        "score": score,
        "reasons": reasons,
        "recommended_action": action,
        # Archiving is safe when nothing has evaluated the flag recently or
        # it has been switched off for a long time. A decided experiment is
        # not safe to delete outright: its winning variant still has to be
        # rolled out in code first, so removing the flag could change
        # behaviour for anyone not yet on that variant's path.
        "safe_to_remove": action == "archive",
    }


def analyse_flags(flags: list[dict], now: datetime | None = None) -> list[dict]:
    """Score every flag in ``flags`` for staleness.

    Returns one entry per flag — ``{"flag", "score", "reasons",
    "recommended_action", "safe_to_remove"}`` — sorted by score
    descending, then by flag name, so the output order is deterministic
    for a given input. ``now`` defaults to the current UTC time; pass it
    explicitly for reproducible results.
    """
    if now is None:
        moment = datetime.now(timezone.utc)
    else:
        moment = _parse_time(now) or datetime.now(timezone.utc)

    results = [_analyse_one(flag, moment) for flag in flags if isinstance(flag, dict)]
    results.sort(key=lambda entry: (-entry["score"], str(entry["flag"])))
    return results


# Spelling aliases for callers that use the other convention.
analyse_stale_flags = analyse_flags
analyze_flags = analyse_flags
analyse = analyse_flags
