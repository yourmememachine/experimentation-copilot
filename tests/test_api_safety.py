"""API-level safety tests (handlers, demo mode, fresh store per test).

Covers the enforcement properties the unit tests cannot see:
- an over-limit traffic plan is not allowed without approval, and an
  unapproved apply is refused before anything is written;
- a plan with a structural guardrail block (no success metric) cannot
  be applied even WITH approval;
- a refused apply leaves the flag store byte-for-byte unchanged
  (no partial mutation);
- a valid plan applies end to end;
- snapshot -> change -> rollback restores the previous state;
- archiving requires approval and only ever touches flags the stale
  check marks safe to remove.
"""
import copy

import pytest

import app.main as m

PROMPT_OK = ("Test a new pricing banner colour green vs blue for 20% "
             "of users, success is checkout_completed")
PROMPT_95 = ("Test a new checkout button colour green vs blue for 95% "
             "of users, success is checkout_completed")
PROMPT_NO_METRIC = ("Test a new checkout button colour green vs blue "
                    "for 20% of users")


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(m, "is_demo_mode", lambda: True)
    m._CLIENT = None
    m._plans.clear()
    m._snapshots.clear()
    m._results.clear()
    m._store["flags"] = copy.deepcopy(m.DEMO_FLAGS)
    yield
    m._CLIENT = None
    m._plans.clear()
    m._snapshots.clear()
    m._results.clear()


def _state():
    return copy.deepcopy(m.list_flags())


def _flag(name):
    return m._find_flag(name)


def _allocations(flag):
    opts = flag.get("multivariate_options") or []
    if opts:
        return sorted((str(o.get("string_value") or o.get("value")),
                       o.get("default_percentage_allocation")) for o in opts)
    return sorted((v.get("name"), v.get("weight"))
                  for v in flag.get("variants") or [])


def _make_plan(prompt):
    status, payload = m.h_plan({"prompt": prompt})
    assert status == 200, payload
    return payload


# ---------- guardrails at apply time ----------

def test_over_limit_plan_is_not_allowed_without_approval():
    payload = _make_plan(PROMPT_95)
    g = payload["guardrails"]
    assert g["allowed"] is False
    assert g["requires_approval"] is True


def test_unapproved_apply_is_refused_and_mutates_nothing():
    payload = _make_plan(PROMPT_OK)
    before = _state()
    status, resp = m.h_apply({"plan_id": payload["plan_id"]})
    assert status == 400
    assert _state() == before


def test_over_limit_apply_without_approval_is_refused():
    payload = _make_plan(PROMPT_95)
    before = _state()
    status, resp = m.h_apply({"plan_id": payload["plan_id"]})
    assert status == 400
    assert _state() == before


def test_no_metric_plan_cannot_apply_even_with_approval():
    payload = _make_plan(PROMPT_NO_METRIC)
    assert payload["guardrails"]["blocks"], payload["guardrails"]
    before = _state()
    status, resp = m.h_apply({"plan_id": payload["plan_id"], "approved": True})
    assert status == 422
    assert "guardrails blocked" in resp["error"]
    assert _state() == before


def test_valid_plan_applies_end_to_end():
    payload = _make_plan(PROMPT_OK)
    name = payload["plan"]["flag_name"]
    assert _flag(name) is None
    status, resp = m.h_apply({"plan_id": payload["plan_id"], "approved": True})
    assert status == 200, resp
    assert resp["applied"] is True
    flag = _flag(name)
    assert flag is not None
    assert flag["enabled"] is True  # 20% traffic -> first rollout step on


# ---------- rollback ----------

def test_rollback_of_create_restores_previous_absence():
    payload = _make_plan(PROMPT_OK)
    name = payload["plan"]["flag_name"]
    status, resp = m.h_apply({"plan_id": payload["plan_id"], "approved": True})
    assert status == 200, resp
    assert _flag(name) is not None
    status, resp = m.h_rollback({"snapshot_id": resp["snapshot_id"],
                                  "approved": True})
    assert status == 200, resp
    after = _flag(name)
    assert after is None or after.get("is_archived") is True


def test_rollback_restores_state_before_graduate():
    name = "checkout_button_colour"
    before = _flag(name)
    assert before is not None
    before_allocs = _allocations(before)
    assert before_allocs and len(set(a[1] for a in before_allocs)) == 1  # 50/50
    status, resp = m.h_graduate({"flag_name": name, "winner": "blue",
                                  "approved": True})
    assert status == 200, resp
    mid = _flag(name)
    assert _allocations(mid) != before_allocs  # rollout actually changed it
    status, resp = m.h_rollback({"snapshot_id": resp["snapshot_id"],
                                  "approved": True})
    assert status == 200, resp
    after = _flag(name)
    assert _allocations(after) == before_allocs
    assert bool(after.get("enabled")) == bool(before.get("enabled"))
    assert bool(after.get("is_archived", False)) == bool(before.get("is_archived", False))


def test_rollback_requires_approval():
    payload = _make_plan(PROMPT_OK)
    status, resp = m.h_apply({"plan_id": payload["plan_id"], "approved": True})
    assert status == 200, resp
    status, resp = m.h_rollback({"snapshot_id": resp["snapshot_id"]})
    assert status == 400


# ---------- safe archival ----------

def test_archive_requires_approval():
    status, resp = m.h_archive({"flag_name": "holiday_sale_banner_2025"})
    assert status == 400
    assert not _flag("holiday_sale_banner_2025").get("is_archived")


def test_archive_refuses_active_flag_even_with_approval():
    before = _state()
    status, resp = m.h_archive({"flag_name": "checkout_button_colour",
                                "approved": True})
    assert status == 400
    assert "safe to remove" in resp["error"]
    assert _state() == before


def test_archive_allows_flag_marked_safe_to_remove():
    status, resp = m.h_archive({"flag_name": "holiday_sale_banner_2025",
                                "approved": True})
    assert status == 200, resp
    assert resp["archived"] is True
    assert _flag("holiday_sale_banner_2025").get("is_archived") is True
