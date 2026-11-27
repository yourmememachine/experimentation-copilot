"""Live-client route tests against a fake transport.

Current Flagsmith removed the flat ``/features/{id}/`` JSON routes (they
now serve the web UI) and rejects partial feature-state writes. These
tests pin the client to the routes that exist: project-nested feature
reads/writes, the filterable ``/features/featurestates/`` collection for
state reads, and full-object PUTs for state writes.
"""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.flagsmith_client import FlagsmithClient

FEATURE = {
    "id": 8,
    "name": "checkout_button_colour",
    "project": 1,
    "type": "MULTIVARIATE",
    "description": "desc",
    "default_enabled": False,
    "is_archived": False,
    "multivariate_options": [
        {"id": 1, "type": "unicode", "string_value": "green",
         "default_percentage_allocation": 50},
        {"id": 2, "type": "unicode", "string_value": "blue",
         "default_percentage_allocation": 50},
    ],
}

STATE = {
    "id": 8,
    "feature": 8,
    "environment": 1,
    "enabled": False,
    "live_from": "2026-11-27T08:35:29Z",
    "feature_state_value": {"type": "unicode", "string_value": None,
                            "integer_value": None, "boolean_value": None},
    "multivariate_feature_state_values": [
        {"id": 1, "multivariate_feature_option": 1, "percentage_allocation": 50.0},
        {"id": 2, "multivariate_feature_option": 2, "percentage_allocation": 50.0},
    ],
    "feature_segment": None,
    "identity": None,
}


class FakeTransport:
    """Replacement for FlagsmithClient._request recording every call."""

    def __init__(self, state=STATE):
        self.calls = []
        self.state = state

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, copy.deepcopy(payload)))
        if method == "GET" and path.startswith("features/featurestates/"):
            return [copy.deepcopy(self.state)] if self.state else []
        if method == "GET" and path.startswith("projects/1/features/8"):
            return copy.deepcopy(FEATURE)
        if method == "GET" and path.startswith("projects/1/features/"):
            item = copy.deepcopy(FEATURE)
            item["environment_feature_state"] = {"id": 8, "enabled": True}
            return [item]
        if method == "PUT" and path == "features/featurestates/8/":
            return copy.deepcopy(payload)
        if method == "POST" and path == "features/featurestates/":
            out = copy.deepcopy(payload)
            out["id"] = 99
            return out
        if method == "PUT" and path == "projects/1/features/8/":
            merged = copy.deepcopy(FEATURE)
            merged.update(payload or {})
            return merged
        raise AssertionError(f"unexpected call: {method} {path}")


def make_client(state=STATE):
    client = FlagsmithClient(
        api_url="http://127.0.0.1:8000/api/v1",
        api_token="test-token",
        project_id=1,
        environment_id=1,
        demo_mode=False,
    )
    transport = FakeTransport(state=state)
    client._request = transport
    return client, transport


def paths(transport):
    return [(m, p) for m, p, _ in transport.calls]


def test_get_flag_uses_project_nested_route():
    client, transport = make_client()
    flag = client.get_flag(8)
    assert flag["name"] == "checkout_button_colour"
    assert ("GET", "projects/1/features/8/?environment=1") in paths(transport)
    assert not any(p.startswith("features/8") for _, p in paths(transport))


def test_list_flags_merges_environment_enabled():
    client, transport = make_client()
    (flag,) = client.list_flags()
    assert ("GET", "projects/1/features/?environment=1") in paths(transport)
    assert flag["enabled"] is True
    assert flag["environment_feature_state_id"] == 8


def test_set_flag_state_puts_full_object_preserving_mv_values():
    client, transport = make_client()
    result = client.set_flag_state(8, True)
    assert ("GET", "features/featurestates/?feature=8&environment=1") in paths(transport)
    put = next(c for c in transport.calls if c[0] == "PUT")
    assert put[1] == "features/featurestates/8/"
    payload = put[2]
    assert payload["enabled"] is True
    assert payload["feature"] == 8 and payload["environment"] == 1
    # The multivariate values ride along untouched — a partial payload
    # is what the current API rejects.
    assert payload["multivariate_feature_state_values"] == \
        STATE["multivariate_feature_state_values"]
    assert payload["feature_state_value"] == STATE["feature_state_value"]
    assert result["enabled"] is True


def test_set_flag_state_posts_when_no_state_exists():
    client, transport = make_client(state=None)
    result = client.set_flag_state(8, True)
    post = next(c for c in transport.calls if c[0] == "POST")
    assert post[1] == "features/featurestates/"
    assert post[2]["feature"] == 8 and post[2]["environment"] == 1
    assert post[2]["enabled"] is True
    assert result["id"] == 99


def test_update_feature_uses_project_nested_route():
    client, transport = make_client()
    client.update_feature(8, description="new desc")
    put = next(c for c in transport.calls if c[0] == "PUT")
    assert put[1] == "projects/1/features/8/"
    assert put[2]["description"] == "new desc"


def test_archive_flag_goes_through_nested_update():
    client, transport = make_client()
    client.archive_flag(8)
    put = next(c for c in transport.calls if c[0] == "PUT")
    assert put[1] == "projects/1/features/8/"
    assert put[2]["is_archived"] is True


def test_set_variant_allocations_updates_feature_and_env_state():
    client, transport = make_client()
    client.set_variant_allocations("checkout_button_colour",
                                   {"green": 0, "blue": 100})
    puts = [c for c in transport.calls if c[0] == "PUT"]
    feature_put = next(c for c in puts if c[1] == "projects/1/features/8/")
    allocs = {o["string_value"]: o["default_percentage_allocation"]
              for o in feature_put[2]["multivariate_options"]}
    assert allocs == {"green": 0, "blue": 100}
    state_put = next(c for c in puts if c[1] == "features/featurestates/8/")
    env_allocs = {mv["multivariate_feature_option"]: mv["percentage_allocation"]
                  for mv in state_put[2]["multivariate_feature_state_values"]}
    # Option 1 is green, option 2 is blue.
    assert env_allocs == {1: 0, 2: 100}
