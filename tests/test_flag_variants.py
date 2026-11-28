"""Flags-table variant naming (live Flagsmith payloads).

Live Flagsmith multivariate options name the variant in ``string_value``
and carry the split in ``default_percentage_allocation`` — they have no
``value``/``weight`` keys. The /api/flags payload must therefore ship a
canonical ``variants`` list (name + allocation) per multivariate flag,
or the UI's flags table renders bare percentages ("50%, 50%") that hide
which variant holds which share — including which one won after a
graduation ("0%, 100%").
"""
import app.main as m


class _StubClient:
    def __init__(self, flags):
        self._flags = flags

    def list_flags(self, **_):
        return [dict(f) for f in self._flags]


def _live_mv_flag(allocations):
    return {
        "id": 8,
        "name": "checkout_button_colour",
        "enabled": True,
        "type": "MULTIVARIATE",
        "description": "Test a new checkout button colour",
        "multivariate_options": [
            {"id": 1, "type": "unicode", "string_value": name,
             "default_percentage_allocation": alloc}
            for name, alloc in allocations
        ],
    }


def _payload_with(flags, monkeypatch):
    monkeypatch.setattr(m, "is_demo_mode", lambda: False)
    m._CLIENT = _StubClient(flags)
    try:
        return m.h_flags()
    finally:
        m._CLIENT = None


def test_live_options_become_named_variants(monkeypatch):
    payload = _payload_with(
        [_live_mv_flag([("green", 50.0), ("blue", 50.0)])], monkeypatch)
    (flag,) = payload["flags"]
    assert flag["variants"] == [
        {"name": "green", "allocation": 50.0},
        {"name": "blue", "allocation": 50.0},
    ]


def test_graduated_allocations_keep_their_names(monkeypatch):
    payload = _payload_with(
        [_live_mv_flag([("green", 0.0), ("blue", 100.0)])], monkeypatch)
    (flag,) = payload["flags"]
    assert flag["variants"] == [
        {"name": "green", "allocation": 0.0},
        {"name": "blue", "allocation": 100.0},
    ]


def test_boolean_flag_gets_no_invented_variants(monkeypatch):
    boolean = {"id": 3, "name": "new_checkout_flow", "enabled": True,
               "type": "STANDARD", "description": "", "multivariate_options": []}
    payload = _payload_with([boolean], monkeypatch)
    (flag,) = payload["flags"]
    assert "variants" not in flag
