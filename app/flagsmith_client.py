"""Flagsmith REST API client with an in-memory demo fallback.

The client talks to a Flagsmith instance over its public REST API when
``FLAGSMITH_API_TOKEN`` is set, and otherwise (or when
``FLAGSMITH_DEMO_MODE=1``) serves the same interface from a seeded
in-memory store so the whole flow can be run and tested with no account,
no network and no spend.

Configuration (environment variables):

- ``FLAGSMITH_API_URL`` -- base URL, e.g. ``https://app.flagsmith.com/api/v1``
  (default) or the base URL of a self-hosted instance.
- ``FLAGSMITH_API_TOKEN`` -- API token sent as ``Authorization: Token <token>``.
- ``FLAGSMITH_PROJECT_ID`` -- default project id used when a call does not
  pass one explicitly.
- ``FLAGSMITH_ENVIRONMENT_ID`` -- default environment id used when a call
  does not pass one explicitly.
- ``FLAGSMITH_DEMO_MODE`` -- ``1``/``true`` forces the demo store.

Every public method returns plain ``dict`` / ``list[dict]`` values so callers
can serialise results directly to JSON.

Stale-flag analysis is defined solely by :mod:`app.stale` (``analyse_flags``);
this module does not label flags as stale itself.
"""

from __future__ import annotations

import copy
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULT_API_URL = "https://app.flagsmith.com/api/v1"

_ALLOCATION_KEYS = (
    "default_percentage_allocation",
    "allocation_percent",
    "allocation",
    "weight",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _q(value: Any) -> str:
    """Quote an identifier for safe interpolation into a URL path."""
    return urllib.parse.quote(str(value), safe="")


def _validate_api_url(api_url: str) -> None:
    parsed = urllib.parse.urlparse(api_url)
    if parsed.scheme == "https":
        return
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}:
        return
    raise FlagsmithError(
        "FLAGSMITH_API_URL must use https unless the host is "
        f"localhost/127.0.0.1 (got {api_url!r})"
    )


def _typed_feature_state_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"type": "boolean", "boolean_value": value}
    if isinstance(value, int):
        return {"type": "integer", "integer_value": value}
    if isinstance(value, float) and float(value).is_integer():
        return {"type": "integer", "integer_value": int(value)}
    return {"type": "unicode", "string_value": str(value)}


def _raw_allocation(variant: dict[str, Any]) -> float | None:
    for key in _ALLOCATION_KEYS:
        raw = variant.get(key)
        if raw is not None and not isinstance(raw, bool):
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return None


def _resolve_allocations(variants: list[dict[str, Any]]) -> list[float]:
    """Return numeric allocations summing to 100 (never None).

    Accepts weight under any known key. If weights are missing, split
    evenly; if partially missing, share the remainder evenly among the
    missing ones; otherwise normalise proportionally to 100.
    """
    n = len(variants)
    if n == 0:
        return []
    raw = [_raw_allocation(v) for v in variants]
    if all(v is None for v in raw):
        allocs = [100.0 / n] * n
    elif any(v is None for v in raw):
        known_sum = sum(v for v in raw if v is not None)
        missing = sum(1 for v in raw if v is None)
        remainder = 100.0 - known_sum
        if remainder <= 0:
            allocs = [100.0 / n] * n
        else:
            fill = remainder / missing
            allocs = [float(v) if v is not None else fill for v in raw]  # type: ignore[arg-type]
    else:
        total = sum(v for v in raw if v is not None)
        if total <= 0:
            allocs = [100.0 / n] * n
        else:
            allocs = [float(v) * 100.0 / total for v in raw]  # type: ignore[arg-type]
    # Round to 2dp and fix drift on the last entry so the sum is exactly 100.
    rounded = [round(a, 2) for a in allocs]
    drift = round(100.0 - sum(rounded), 2)
    if rounded:
        rounded[-1] = round(rounded[-1] + drift, 2)
    # Present integral values as ints for cleanliness, still numeric.
    return [int(a) if float(a).is_integer() else a for a in rounded]  # type: ignore[return-value]


def _analyse_stale(flags: list[dict[str, Any]]) -> list[Any]:
    """Delegate stale analysis to app.stale if importable, else unlabelled."""
    analyse = None
    try:
        from app.stale import analyse_flags as analyse  # type: ignore[no-redef]
    except Exception:
        try:
            from stale import analyse_flags as analyse  # type: ignore[no-redef]
        except Exception:
            analyse = None
    if analyse is not None:
        return list(analyse(flags))
    # No stale labelling here: stale.py is the single definition.
    return list(flags)


class FlagsmithError(RuntimeError):
    """Raised when a live Flagsmith API call fails."""


# ---------------------------------------------------------------------------
# Demo store
# ---------------------------------------------------------------------------


def _seed_flags() -> list[dict[str, Any]]:
    now = _utcnow()

    def days_ago(days: int) -> str:
        return _iso(now - timedelta(days=days))

    return [
        {
            "id": 1, "name": "checkout_button_colour",
            "description": "Controls the primary checkout button colour.",
            "type": "MULTIVARIATE", "project": 1, "default_enabled": False,
            "is_archived": False, "tags": ["checkout", "experiment"],
            "created_date": days_ago(12), "last_modified": days_ago(1),
            "enabled": True, "value": "blue",
            "multivariate_options": [
                {"id": 11, "type": "unicode", "value": "blue", "default_percentage_allocation": 50},
                {"id": 12, "type": "unicode", "value": "green", "default_percentage_allocation": 50},
            ],
            "num_evaluations": 18420,
        },
        {
            "id": 2, "name": "new_checkout_flow",
            "description": "Single-page checkout flow replacing the legacy steps.",
            "type": "STANDARD", "project": 1, "default_enabled": False,
            "is_archived": False, "tags": ["checkout"],
            "created_date": days_ago(45), "last_modified": days_ago(3),
            "enabled": True, "value": None, "multivariate_options": [],
            "num_evaluations": 9210,
        },
        {
            "id": 3, "name": "pricing_page_redesign",
            "description": "Redesigned pricing page with annual-plan emphasis.",
            "type": "STANDARD", "project": 1, "default_enabled": False,
            "is_archived": False, "tags": ["pricing", "experiment"],
            "created_date": days_ago(30), "last_modified": days_ago(6),
            "enabled": False, "value": None, "multivariate_options": [],
            "num_evaluations": 3105,
        },
        {
            "id": 4, "name": "recommendations_v2",
            "description": "Second-generation product recommendations rail.",
            "type": "STANDARD", "project": 1, "default_enabled": True,
            "is_archived": False, "tags": ["discovery"],
            "created_date": days_ago(60), "last_modified": days_ago(2),
            "enabled": True, "value": None, "multivariate_options": [],
            "num_evaluations": 44780,
        },
        {
            "id": 5, "name": "legacy_search_v1",
            "description": "Legacy search backend kept during the v2 migration.",
            "type": "STANDARD", "project": 1, "default_enabled": False,
            "is_archived": False, "tags": ["search", "legacy"],
            "created_date": days_ago(240), "last_modified": days_ago(187),
            "enabled": False, "value": None, "multivariate_options": [],
            "num_evaluations": 0,
        },
        {
            "id": 6, "name": "old_promo_banner",
            "description": "Promotional banner from a finished campaign.",
            "type": "STANDARD", "project": 1, "default_enabled": False,
            "is_archived": False, "tags": ["marketing", "campaign"],
            "created_date": days_ago(210), "last_modified": days_ago(164),
            "enabled": False, "value": "spring_sale", "multivariate_options": [],
            "num_evaluations": 12,
        },
        {
            "id": 7, "name": "holiday_sale_banner_2025",
            "description": "Holiday 2025 sale banner; campaign ended.",
            "type": "STANDARD", "project": 1, "default_enabled": False,
            "is_archived": False, "tags": ["marketing", "campaign"],
            "created_date": days_ago(330), "last_modified": days_ago(298),
            "enabled": False, "value": None, "multivariate_options": [],
            "num_evaluations": 0,
        },
        {
            "id": 8, "name": "beta_dashboard_access",
            "description": "Grants access to the beta dashboard for opted-in users.",
            "type": "STANDARD", "project": 1, "default_enabled": False,
            "is_archived": False, "tags": ["beta"],
            "created_date": days_ago(20), "last_modified": days_ago(20),
            "enabled": True, "value": None, "multivariate_options": [],
            "num_evaluations": 640,
        },
    ]


def _seed_segments() -> list[dict[str, Any]]:
    return [
        {"id": 1, "name": "beta_users", "description": "Opted-in beta users.", "project": 1, "rules": []},
        {"id": 2, "name": "canada_users", "description": "Users in Canada.", "project": 1, "rules": []},
        {"id": 3, "name": "internal_staff", "description": "Internal staff accounts.", "project": 1, "rules": []},
    ]


class DemoStore:
    """In-memory implementation of the Flagsmith client interface."""

    def __init__(self) -> None:
        self._flags: list[dict[str, Any]] = _seed_flags()
        self._segments: list[dict[str, Any]] = _seed_segments()
        self._next_flag_id = max(f["id"] for f in self._flags) + 1
        self._next_option_id = 100

    def list_flags(self, project_id: int | None = None, environment_id: int | None = None, **_: Any) -> list[dict[str, Any]]:
        flags = self._flags
        if project_id is not None:
            flags = [f for f in flags if f.get("project") == project_id]
        return copy.deepcopy(flags)

    def get_flag(self, flag_id: int | str, **_: Any) -> dict[str, Any]:
        for flag in self._flags:
            if flag["id"] == flag_id or flag["name"] == str(flag_id):
                return copy.deepcopy(flag)
        raise FlagsmithError(f"flag not found: {flag_id!r}")

    def list_stale_flags(self, project_id: int | None = None, **_: Any) -> list[Any]:
        return _analyse_stale(self.list_flags(project_id=project_id))

    def list_segments(self, project_id: int | None = None, **_: Any) -> list[dict[str, Any]]:
        segments = self._segments
        if project_id is not None:
            segments = [s for s in segments if s.get("project") == project_id]
        return copy.deepcopy(segments)

    def list_projects(self, **_: Any) -> list[dict[str, Any]]:
        return [{"id": 1, "name": "Default Project", "organisation": 1}]

    def list_environments(self, project_id: int | None = None, **_: Any) -> list[dict[str, Any]]:
        envs = [
            {"id": 1, "name": "Development", "project": project_id or 1, "api_key": "demo-development-key"},
            {"id": 2, "name": "Production", "project": project_id or 1, "api_key": "demo-production-key"},
        ]
        return [{k: v for k, v in e.items() if k != "api_key"} for e in envs]

    def create_feature(self, name: str, project_id: int | None = None, description: str = "", default_enabled: bool = False, tags: list[str] | None = None, **_: Any) -> dict[str, Any]:
        if any(f["name"] == name for f in self._flags):
            raise FlagsmithError(f"feature already exists: {name!r}")
        flag: dict[str, Any] = {
            "id": self._next_flag_id, "name": name, "description": description,
            "type": "STANDARD", "project": project_id or 1,
            "default_enabled": default_enabled, "is_archived": False,
            "tags": list(tags or []), "created_date": _iso(_utcnow()),
            "last_modified": _iso(_utcnow()), "enabled": default_enabled,
            "value": None, "multivariate_options": [], "num_evaluations": 0,
        }
        self._next_flag_id += 1
        self._flags.append(flag)
        return copy.deepcopy(flag)

    def create_multivariate_feature(self, name: str, project_id: int | None = None, description: str = "", variants: list[dict[str, Any]] | None = None, default_enabled: bool = False, tags: list[str] | None = None, **_: Any) -> dict[str, Any]:
        flag = self.create_feature(name, project_id=project_id, description=description, default_enabled=default_enabled, tags=tags)
        variants = list(variants or [])
        allocations = _resolve_allocations(variants)
        options: list[dict[str, Any]] = []
        for variant, allocation in zip(variants, allocations):
            value = variant.get("value", variant.get("name"))
            options.append({"id": self._next_option_id, "type": "unicode", "value": str(value), "default_percentage_allocation": allocation})
            self._next_option_id += 1
        stored = next(f for f in self._flags if f["id"] == flag["id"])
        stored["type"] = "MULTIVARIATE"
        stored["multivariate_options"] = options
        if options:
            stored["value"] = options[0]["value"]
        return copy.deepcopy(stored)

    def set_variant_allocations(self, flag_name_or_id: int | str, allocations: dict[str, float], **_: Any) -> dict[str, Any]:
        for flag in self._flags:
            if flag["id"] == flag_name_or_id or flag["name"] == str(flag_name_or_id):
                options = flag.get("multivariate_options") or []
                for opt in options:
                    key = str(opt.get("value"))
                    if key in allocations:
                        opt["default_percentage_allocation"] = allocations[key]
                    elif str(opt.get("id")) in allocations:
                        opt["default_percentage_allocation"] = allocations[str(opt.get("id"))]
                flag["last_modified"] = _iso(_utcnow())
                return copy.deepcopy(flag)
        raise FlagsmithError(f"flag not found: {flag_name_or_id!r}")

    def set_flag_state(self, feature_id: int | str, enabled: bool, environment_id: int | None = None, value: Any = None, **_: Any) -> dict[str, Any]:
        for flag in self._flags:
            if flag["id"] == feature_id or flag["name"] == str(feature_id):
                flag["enabled"] = bool(enabled)
                if value is not None:
                    flag["value"] = value
                flag["last_modified"] = _iso(_utcnow())
                result = copy.deepcopy(flag)
                result["environment"] = environment_id
                return result
        raise FlagsmithError(f"flag not found: {feature_id!r}")

    def update_feature(self, flag_id: int | str, **changes: Any) -> dict[str, Any]:
        for flag in self._flags:
            if flag["id"] == flag_id or flag["name"] == str(flag_id):
                for key in ("name", "description", "is_archived", "default_enabled", "tags", "project", "multivariate_options"):
                    if key in changes:
                        flag[key] = changes[key]
                flag["last_modified"] = _iso(_utcnow())
                return copy.deepcopy(flag)
        raise FlagsmithError(f"flag not found: {flag_id!r}")

    def archive_flag(self, flag_id: int | str, **_: Any) -> dict[str, Any]:
        return self.update_feature(flag_id, is_archived=True)

    def health_check(self, **_: Any) -> dict[str, Any]:
        return {"status": "ok", "mode": "demo", "flags": len(self._flags)}


# ---------------------------------------------------------------------------
# Live client
# ---------------------------------------------------------------------------


class FlagsmithClient:
    """Client for the Flagsmith REST API, with a demo fallback."""

    def __init__(self, api_url: str | None = None, api_token: str | None = None, project_id: int | None = None, environment_id: int | None = None, demo_mode: bool | None = None, timeout: float = 15.0) -> None:
        self.api_url = (api_url or os.environ.get("FLAGSMITH_API_URL") or DEFAULT_API_URL).rstrip("/")
        _validate_api_url(self.api_url)
        self.api_token = api_token if api_token is not None else os.environ.get("FLAGSMITH_API_TOKEN")
        self.project_id = project_id or _env_int("FLAGSMITH_PROJECT_ID")
        self.environment_id = environment_id or _env_int("FLAGSMITH_ENVIRONMENT_ID")
        if demo_mode is None:
            demo_mode = _truthy(os.environ.get("FLAGSMITH_DEMO_MODE"))
        self.demo_mode = bool(demo_mode or not self.api_token)
        self.timeout = timeout
        self._store = DemoStore() if self.demo_mode else None

    # -- transport -----------------------------------------------------
    def _request_once(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"Token {self.api_token}")
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                body = resp.read().decode()
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode(errors="replace")
            except Exception:
                detail = str(exc)
            raise FlagsmithError(f"Flagsmith API {method} {url} failed: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise FlagsmithError(f"Flagsmith API {method} {url} failed: {exc}") from exc
        if not body:
            return {}
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError) as exc:
            raise FlagsmithError(f"Flagsmith API {method} {url} returned non-JSON body: {body[:500]!r}") from exc

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        # Absolute URLs (pagination `next`) are used verbatim; relative
        # paths are resolved against the configured base URL.
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = f"{self.api_url}/{path.lstrip('/')}"
        parsed = self._request_once(method, url, payload)
        if isinstance(parsed, dict) and "results" in parsed:
            results: list[Any] = list(parsed.get("results") or [])
            next_url = parsed.get("next")
            while next_url:
                page = self._request_once("GET", str(next_url))
                if not isinstance(page, dict) or "results" not in page:
                    raise FlagsmithError(f"Flagsmith API pagination page was not a paginated list: {str(page)[:500]!r}")
                results.extend(page.get("results") or [])
                next_url = page.get("next")
            return results
        return parsed

    def _project(self, project_id: int | None) -> int:
        resolved = project_id or self.project_id
        if resolved is None:
            raise FlagsmithError("project_id is required (or set FLAGSMITH_PROJECT_ID)")
        return resolved

    # -- reads ---------------------------------------------------------
    def list_flags(self, project_id: int | None = None, environment_id: int | None = None) -> list[dict[str, Any]]:
        if self._store is not None:
            return self._store.list_flags(project_id=project_id, environment_id=environment_id)
        result = self._request("GET", f"projects/{_q(self._project(project_id))}/features/")
        return list(result) if isinstance(result, list) else [result]

    def get_flag(self, flag_id: int | str) -> dict[str, Any]:
        if self._store is not None:
            return self._store.get_flag(flag_id)
        if isinstance(flag_id, int) or str(flag_id).isdigit():
            return dict(self._request("GET", f"features/{_q(flag_id)}/"))
        for flag in self.list_flags():
            if flag.get("name") == str(flag_id):
                return flag
        raise FlagsmithError(f"flag not found: {flag_id!r}")

    def list_stale_flags(self, project_id: int | None = None) -> list[Any]:
        if self._store is not None:
            return self._store.list_stale_flags(project_id=project_id)
        return _analyse_stale(self.list_flags(project_id=project_id))

    def list_segments(self, project_id: int | None = None) -> list[dict[str, Any]]:
        if self._store is not None:
            return self._store.list_segments(project_id=project_id)
        result = self._request("GET", f"projects/{_q(self._project(project_id))}/segments/")
        return list(result) if isinstance(result, list) else [result]

    def list_projects(self) -> list[dict[str, Any]]:
        if self._store is not None:
            return self._store.list_projects()
        result = self._request("GET", "projects/")
        return list(result) if isinstance(result, list) else [result]

    def list_environments(self, project_id: int | None = None) -> list[dict[str, Any]]:
        if self._store is not None:
            return self._store.list_environments(project_id=project_id)
        result = self._request("GET", f"projects/{_q(self._project(project_id))}/environments/")
        items = list(result) if isinstance(result, list) else [result]
        return [{k: v for k, v in item.items() if k != "api_key"} if isinstance(item, dict) else item for item in items]

    # -- writes --------------------------------------------------------
    def create_feature(self, name: str, project_id: int | None = None, description: str = "", default_enabled: bool = False, tags: list[str] | None = None) -> dict[str, Any]:
        if self._store is not None:
            return self._store.create_feature(name, project_id=project_id, description=description, default_enabled=default_enabled, tags=tags)
        # Tags are omitted: the API expects tag IDs, not {"label": ...}.
        payload = {"name": name, "project": self._project(project_id), "description": description, "default_enabled": default_enabled, "type": "STANDARD"}
        return dict(self._request("POST", f"projects/{_q(self._project(project_id))}/features/", payload))

    def create_multivariate_feature(self, name: str, project_id: int | None = None, description: str = "", variants: list[dict[str, Any]] | None = None, default_enabled: bool = False, tags: list[str] | None = None) -> dict[str, Any]:
        if self._store is not None:
            return self._store.create_multivariate_feature(name, project_id=project_id, description=description, variants=variants, default_enabled=default_enabled, tags=tags)
        variants = list(variants or [])
        allocations = _resolve_allocations(variants)
        options = []
        for variant, allocation in zip(variants, allocations):
            options.append({"type": "unicode", "string_value": str(variant.get("value", variant.get("name"))), "default_percentage_allocation": allocation})
        payload = {"name": name, "project": self._project(project_id), "description": description, "default_enabled": default_enabled, "type": "MULTIVARIATE", "multivariate_options": options}
        return dict(self._request("POST", f"projects/{_q(self._project(project_id))}/features/", payload))

    def set_variant_allocations(self, flag_name_or_id: int | str, allocations: dict[str, float]) -> dict[str, Any]:
        if self._store is not None:
            return self._store.set_variant_allocations(flag_name_or_id, allocations)
        feature = self.get_flag(flag_name_or_id)
        existing = feature.get("multivariate_options") or []
        rebuilt = []
        for opt in existing:
            if not isinstance(opt, dict):
                continue
            value = opt.get("value", opt.get("string_value"))
            key = str(value)
            alloc = allocations.get(key, opt.get("default_percentage_allocation"))
            if alloc is None:
                alloc = 0
            entry: dict[str, Any] = {"type": opt.get("type", "unicode"), "default_percentage_allocation": alloc}
            if entry["type"] == "integer":
                try:
                    entry["integer_value"] = int(value)
                except (TypeError, ValueError):
                    entry["string_value"] = str(value)
            elif entry["type"] == "boolean":
                entry["boolean_value"] = str(value).lower() in {"true", "1", "yes"}
            else:
                entry["string_value"] = str(value)
            if "id" in opt:
                entry["id"] = opt["id"]
            rebuilt.append(entry)
        return self.update_feature(feature.get("id", flag_name_or_id), multivariate_options=rebuilt)

    def set_flag_state(self, feature_id: int | str, enabled: bool, environment_id: int | None = None, value: Any = None) -> dict[str, Any]:
        if self._store is not None:
            return self._store.set_flag_state(feature_id, enabled, environment_id=environment_id, value=value)
        env = environment_id or self.environment_id
        if env is None:
            raise FlagsmithError("environment_id is required (or set FLAGSMITH_ENVIRONMENT_ID)")
        feature = self.get_flag(feature_id)
        fid = feature.get("id", feature_id)
        existing_states = self._request("GET", f"environments/{_q(env)}/featurestates/")
        existing = None
        if isinstance(existing_states, list):
            for state in existing_states:
                if isinstance(state, dict) and str(state.get("feature")) == str(fid):
                    existing = state
                    break
        payload: dict[str, Any] = {"feature": fid, "environment": env, "enabled": bool(enabled), "live_from": _iso(_utcnow())}
        if value is not None:
            payload["feature_state_value"] = _typed_feature_state_value(value)
        if existing is not None and existing.get("id") is not None:
            return dict(self._request("PUT", f"environments/{_q(env)}/featurestates/{_q(existing['id'])}/", payload))
        return dict(self._request("POST", f"environments/{_q(env)}/featurestates/", payload))

    def update_feature(self, flag_id: int | str, **changes: Any) -> dict[str, Any]:
        if self._store is not None:
            return self._store.update_feature(flag_id, **changes)
        feature = self.get_flag(flag_id)
        fid = feature.get("id", flag_id)
        # Explicit writable payload only -- never re-send the read-back object.
        payload: dict[str, Any] = {}
        for key in ("name", "description", "default_enabled", "is_archived", "project"):
            if key in changes:
                payload[key] = changes[key]
            elif key in feature:
                payload[key] = feature[key]
        if "multivariate_options" in changes:
            payload["multivariate_options"] = changes["multivariate_options"]
        return dict(self._request("PUT", f"features/{_q(fid)}/", payload))

    def archive_flag(self, flag_id: int | str) -> dict[str, Any]:
        return self.update_feature(flag_id, is_archived=True)

    def health_check(self) -> dict[str, Any]:
        if self._store is not None:
            return self._store.health_check()
        projects = self.list_projects()
        return {"status": "ok", "mode": "live", "projects": len(projects)}


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw and re.fullmatch(r"\d+", raw.strip()):
        return int(raw.strip())
    return None


def get_client(**kwargs: Any) -> FlagsmithClient:
    """Convenience factory reading configuration from the environment."""
    return FlagsmithClient(**kwargs)


__all__ = ["DEFAULT_API_URL", "DemoStore", "FlagsmithClient", "FlagsmithError", "get_client"]
