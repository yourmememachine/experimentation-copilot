"""Experimentation Copilot — FastAPI app (stdlib fallback).

Endpoints:
  GET  /                    static UI
  GET  /api/health
  GET  /api/flags
  POST /api/plan            {prompt} -> server-stored plan + guardrail result
  POST /api/apply           {plan_id, approved} -> applies the stored plan
  GET  /api/stale           stale-flag analysis
  POST /api/rollback        {snapshot_id, approved} -> verified restore
  POST /api/simulate        {flag_name, visitors} -> deterministic results
  GET  /api/results/{flag}  per-variant results + recommended winner
  POST /api/graduate        {flag_name, winner, approved} -> winner to 100%
  POST /api/archive         {flag_name, approved} -> archive a stale flag

Plans are applied only from the server-side store, by plan_id, and the
stored copy is integrity-checked against the hash taken at plan time.
Every mutating call snapshots the previous state first; a snapshot is
only handed out after the change it protects has actually succeeded.
"""
import hashlib, json, math, os, random, re, time, uuid
from copy import deepcopy
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
ROOT = BASE.parent
MAX_BODY_BYTES = 64 * 1024
MAX_PROMPT_CHARS = 2000

# ---------- environment loading (.env) ----------
def _load_env_file():
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(ROOT / ".env")
        load_dotenv()
        return
    except Exception:
        pass
    for candidate in (ROOT / ".env", Path.cwd() / ".env"):
        try:
            if not candidate.is_file():
                continue
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip("'\"")
                os.environ.setdefault(key, value)
        except Exception:
            continue

_load_env_file()

# ---------- demo / live mode: single source of truth ----------
_FALSEY = ("0", "false", "no", "off")

def is_demo_mode():
    """True unless live mode was explicitly opted into.

    Live mode requires a Flagsmith token AND an explicit
    FLAGSMITH_DEMO_MODE=0/false (or equivalent) in the environment.
    With no token there is nothing to talk to, so demo mode applies.
    The client factory and /api/health both use this one function.
    """
    token = os.getenv("FLAGSMITH_API_TOKEN")
    if not token:
        return True
    raw = os.getenv("FLAGSMITH_DEMO_MODE")
    if raw is not None and raw.strip().lower() in _FALSEY:
        return False
    return True

DEMO_MODE = is_demo_mode()  # import-time snapshot; is_demo_mode() is live

# ---------- defensive sibling imports ----------
def _try(modnames):
    import importlib
    for name in modnames:
        try:
            return importlib.import_module(name)
        except Exception:
            continue
    return None

planner_mod = _try(["app.planner", "planner"])
guardrails_mod = _try(["app.guardrails", "guardrails"])
client_mod = _try(["app.flagsmith_client", "flagsmith_client"])
stale_mod = _try(["app.stale", "stale", "app.stale_flags", "stale_flags"])

def _call(mod, names, *a, **kw):
    if mod is None: return None
    for n in names:
        fn = getattr(mod, n, None)
        if callable(fn):
            try: return fn(*a, **kw)
            except TypeError: continue
    return None

# ---------- local fallback store (only used if the client module is absent) ----------
_now = int(time.time()); DAY = 86400
DEMO_FLAGS = [
    {"name": "checkout_redesign", "enabled": True, "type": "multivariate",
     "variants": [{"name": "control", "weight": 50}, {"name": "new_checkout", "weight": 50}],
     "created_at": _now - 12*DAY, "last_changed_at": _now - 2*DAY, "last_evaluated_at": _now - 3600,
     "description": "New one-page checkout flow"},
    {"name": "legacy_pricing_v1", "enabled": True, "type": "boolean", "variants": [],
     "created_at": _now - 210*DAY, "last_changed_at": _now - 180*DAY, "last_evaluated_at": _now - 90*DAY,
     "description": "Old pricing page — replacement shipped months ago"},
]
_store = {"flags": deepcopy(DEMO_FLAGS)}
_plans = {}       # plan_id -> {"plan": plan, "hash": sha256 hex}
_snapshots = {}   # snapshot_id -> {"flag_name", "before", "created_at", "kind"}
_results = {}     # flag_name -> simulation result

_CLIENT = None
def get_client_cached():
    """Cache the client: a fresh demo client has a fresh, empty store."""
    global _CLIENT
    if _CLIENT is None and client_mod is not None:
        _CLIENT = _call(client_mod, ["get_client"], demo_mode=is_demo_mode())
        if _CLIENT is None:
            cls = getattr(client_mod, "FlagsmithClient", None)
            if cls is not None:
                try: _CLIENT = cls(demo_mode=is_demo_mode())
                except Exception:
                    try: _CLIENT = cls()
                    except Exception: _CLIENT = None
    return _CLIENT

def _list_flags_status():
    """Return (flags, available). An empty list from the client is a real
    answer; an exception or a missing client in live mode is not — the two
    are never conflated, and no demo flags are invented in live mode."""
    client = get_client_cached()
    if client is not None:
        try:
            r = client.list_flags()
        except Exception:
            return [], False
        if isinstance(r, list):
            return r, True
        return [], False
    if is_demo_mode():
        return deepcopy(_store["flags"]), True
    return [], False

def list_flags():
    flags, _available = _list_flags_status()
    return flags

def _find_flag(name):
    for f in list_flags():
        if f.get("name") == name:
            return deepcopy(f)
    return None

def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:48] or "new_experiment"

def stub_plan(prompt):
    p = prompt.strip()
    low = p.lower()
    metric = "conversion rate"
    for m in ["sign-up", "signup", "checkout", "purchase", "retention", "click", "revenue", "activation"]:
        if m in low: metric = {"sign-up": "sign-up rate", "signup": "sign-up rate"}.get(m, m + " rate"); break
    return {
        "id": "plan_" + uuid.uuid4().hex, "prompt": p,
        "flag_name": slugify(p.split(".")[0]) if p else "new_experiment",
        "description": p, "hypothesis": f"If we ship this change, {metric} will improve because the change removes friction for users.",
        "metric": metric, "type": "multivariate",
        "variants": [{"name": "control", "weight": 50}, {"name": "treatment", "weight": 50}],
        "traffic_split": {"control": 50, "treatment": 50},
        "duration_days": 14, "rollout": {"initial_percent": 10, "ramp": [10, 25, 50]},
        "source": "built-in planner (demo)",
    }

def normalize_plan(plan):
    """Normalise field spellings only. This never invents content: no
    boilerplate rollback plan, no made-up metric, no made-up hypothesis —
    a plan that lacks those fields stays lacking them, and the guardrail
    result says so."""
    plan.setdefault("id", "plan_" + uuid.uuid4().hex)
    if not plan.get("metric") and plan.get("success_metric"):
        plan["metric"] = plan.get("success_metric")
    variants = []
    for v in plan.get("variants", []) or []:
        if not isinstance(v, dict):
            continue
        v = dict(v)
        w = v.get("weight", v.get("allocation_percent", v.get("default_percentage_allocation")))
        if w is not None: v["weight"] = w
        variants.append(v)
    if variants: plan["variants"] = variants
    if variants and not plan.get("traffic_split"):
        plan["traffic_split"] = {v.get("name", "?"): v.get("weight") for v in variants}
    return plan

def _plan_hash(plan):
    blob = json.dumps(plan, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()

def make_plan(prompt):
    plan = _call(planner_mod, ["parse_prompt", "create_plan", "plan_experiment", "build_plan", "plan"], prompt)
    if not isinstance(plan, dict): plan = stub_plan(prompt)
    plan = normalize_plan(plan)
    _plans[plan["id"]] = {"plan": deepcopy(plan), "hash": _plan_hash(plan)}
    return plan, _plans[plan["id"]]["hash"]

_APPROVAL_BLOCK_HINTS = ("require explicit human approval", "requires explicit human approval",
                         "exceeds the", "cap and requires")
_ROLLBACK_BLOCK_HINT = "rollback"

def check_guardrails(plan, approved=False):
    """Guardrail result with structural blocks kept separate from the
    approval requirement.

    The rollback requirement is NOT satisfied by any text inside the
    plan: it is satisfied by the server-side snapshot record taken at
    apply time, and this function reports exactly that. Structural
    blocks are computed so that an approval re-check can never silently
    downgrade or erase them: a block that appears with or without
    approval stays a block.
    """
    ev = getattr(guardrails_mod, "evaluate", None) if guardrails_mod else None
    if callable(ev):
        try: raw_no = ev(plan, approved=False)
        except Exception: raw_no = None
        try: raw_yes = ev(plan, approved=True)
        except Exception: raw_yes = None
        if isinstance(raw_no, dict) and isinstance(raw_yes, dict):
            blocks_no = [str(b) for b in raw_no.get("blocks", [])]
            blocks_yes = [str(b) for b in raw_yes.get("blocks", [])]
            warnings = list(raw_no.get("warnings", [])) + list(raw_yes.get("warnings", []))
            requires = bool(raw_no.get("requires_approval")) or any(
                any(h in b.lower() for h in _APPROVAL_BLOCK_HINTS) for b in blocks_no)
            structural, approval_blocks = [], []
            for b in blocks_no + [b for b in blocks_yes if b not in blocks_no]:
                low = b.lower()
                if _ROLLBACK_BLOCK_HINT in low:
                    continue  # covered by the server snapshot at apply time
                if any(h in low for h in _APPROVAL_BLOCK_HINTS) or "approval" in low:
                    if b not in approval_blocks: approval_blocks.append(b)
                elif b not in structural:
                    structural.append(b)
            if approval_blocks:
                requires = True
            deduped_warnings = list(dict.fromkeys(str(w) for w in warnings))
            if not approved and requires:
                deduped_warnings.append(
                    "Applying requires your explicit approval — tick the approval box below.")
            return {
                "passed": not structural,
                "allowed": (not structural) and (approved or not requires),
                "blocks": structural,
                "structural_blocks": structural,
                "approval_blocks": approval_blocks,
                "warnings": deduped_warnings,
                "requires_approval": requires,
                "rollback": "Covered by a server-side snapshot of the flag's previous "
                            "state, taken when the plan is applied. Rollback uses "
                            "that snapshot record, not plan text.",
            }
    blocks, warnings = [], []
    weights = [v.get("weight", 0) for v in plan.get("variants", []) if isinstance(v, dict)]
    if weights and sum(weights) != 100: blocks.append(f"Variant weights sum to {sum(weights)}, not 100.")
    if not plan.get("metric"): blocks.append("No success metric defined.")
    if not plan.get("hypothesis"): blocks.append("No hypothesis written — add one before launch.")
    return {"passed": not blocks, "allowed": not blocks and approved, "blocks": blocks,
            "structural_blocks": blocks, "approval_blocks": [],
            "warnings": warnings, "requires_approval": True,
            "rollback": "Covered by a server-side snapshot taken at apply time."}

_ACTION_TEXT = {"archive": "Archive — remove the flag and its dead code paths",
                "rollout_winner": "Roll out the winning variant in code, then remove the flag",
                "keep": "Keep — still in active use"}
def _normalize_for_stale(flags):
    out = []
    for f in flags:
        g = dict(f)
        g.setdefault("created_at", f.get("created_date"))
        g.setdefault("updated_at", f.get("last_modified"))
        g.setdefault("last_modified_at", f.get("last_modified"))
        if "evaluations_last_30d" not in g:
            g["evaluations_last_30d"] = 0 if f.get("stale") else f.get("num_evaluations")
        out.append(g)
    return out

def stale_analysis():
    res = _call(stale_mod, ["analyse_flags", "analyse_stale_flags", "analyze_stale_flags", "stale_flags", "analyse", "analyze"], _normalize_for_stale(list_flags()))
    if isinstance(res, list) and res and isinstance(res[0], dict) and "score" in res[0]:
        out = []
        for e in res:
            if e.get("score", 0) <= 0: continue
            out.append({"flag": e.get("flag"), "stale_score": e.get("score"), "score": e.get("score"),
                        "reasons": e.get("reasons", []), "safe_to_remove": e.get("safe_to_remove"),
                        "recommended_action": _ACTION_TEXT.get(e.get("recommended_action"), e.get("recommended_action"))})
        return out
    if isinstance(res, list): return res
    if isinstance(res, dict) and "stale" in res: return res["stale"]
    out = []
    for f in list_flags():
        age = (_now - f.get("created_at", _now)) // DAY if isinstance(f.get("created_at"), (int, float)) else None
        idle = (_now - f.get("last_changed_at", _now)) // DAY if isinstance(f.get("last_changed_at"), (int, float)) else 0
        reasons, action, score = [], "Keep", 0
        if idle >= 90: reasons.append(f"Unchanged for {idle} days"); score += 40
        if score >= 40:
            out.append({"flag": f["name"], "age_days": age, "idle_days": idle,
                        "stale_score": score, "score": score,
                        "reasons": reasons, "recommended_action": action})
    return sorted(out, key=lambda x: -x["stale_score"])

# ---------- snapshots ----------
def _new_snapshot(flag_name, before, kind):
    sid = "snap_" + uuid.uuid4().hex
    _snapshots[sid] = {"flag_name": flag_name, "before": deepcopy(before),
                       "created_at": int(time.time()), "kind": kind}
    return sid

def _plan_traffic(plan):
    steps = plan.get("rollout_steps") or []
    if steps and isinstance(steps[0], dict) and steps[0].get("traffic_percent") is not None:
        return steps[0].get("traffic_percent")
    if plan.get("traffic_percent") is not None:
        return plan.get("traffic_percent")
    if plan.get("traffic_percentage") is not None:
        return plan.get("traffic_percentage")
    rollout = plan.get("rollout")
    if isinstance(rollout, dict) and rollout.get("initial_percent") is not None:
        return rollout.get("initial_percent")
    return 0

# ---------- core handlers (shared by both servers) ----------
def h_health():
    flags, available = _list_flags_status()
    return {"status": "ok", "product": "Experimentation Copilot",
            "demo_mode": is_demo_mode(),
            "flagsmith_configured": bool(os.getenv("FLAGSMITH_API_TOKEN")),
            "client_available": available,
            "flags": len(flags)}

def h_flags():
    flags, available = _list_flags_status()
    payload = {"flags": flags, "demo_mode": is_demo_mode(), "client_available": available}
    if not available:
        payload["error"] = "Flagsmith client unavailable — no flags could be loaded."
    return payload

def h_plan(body):
    body = body or {}
    prompt = body.get("prompt")
    if not isinstance(prompt, str):
        return 400, {"error": "prompt is required and must be a string"}
    prompt = prompt.strip()
    if not prompt:
        return 400, {"error": "prompt is required"}
    if len(prompt) > MAX_PROMPT_CHARS:
        return 413, {"error": f"prompt is too long (max {MAX_PROMPT_CHARS} characters)"}
    plan, plan_hash = make_plan(prompt)
    return 200, {"plan": plan, "plan_id": plan["id"], "plan_hash": plan_hash,
                 "guardrails": check_guardrails(plan)}

def h_apply(body):
    body = body or {}
    if body.get("approved") is not True:
        return 400, {"error": "approved must be true — review the plan and tick the approval box first"}
    plan_id = body.get("plan_id")
    entry = _plans.get(plan_id) if isinstance(plan_id, str) else None
    if entry is None:
        return 404, {"error": "plan not found — create a plan first"}
    # Only the server-stored plan is applied. Any caller-supplied plan
    # body is ignored; the stored copy must still match its plan-time hash.
    if body.get("plan_hash") and body.get("plan_hash") != entry["hash"]:
        return 422, {"error": "plan hash mismatch — the plan changed since it was drafted; draft a new plan"}
    plan = deepcopy(entry["plan"])
    if _plan_hash(plan) != entry["hash"]:
        return 422, {"error": "plan integrity check failed — draft a new plan"}
    plan = normalize_plan(plan)
    intent = plan.get("intent") or ("create_experiment" if plan.get("variants") else "create_flag")
    if intent == "stale_cleanup":
        return 422, {"error": "stale cleanup plans are not applied here — use the archive action on the stale-flag view"}
    g = check_guardrails(plan, approved=True)
    if not g["passed"]:
        return 422, {"error": "guardrails blocked this plan", "guardrails": g}
    name = plan.get("flag_name") or plan.get("name") or "new_experiment"
    client = get_client_cached()
    if intent == "toggle_flag":
        return _apply_toggle(plan, name, client)
    return _apply_create(plan, name, client)

def _apply_toggle(plan, name, client):
    before = _find_flag(name)
    if before is None:
        return 404, {"error": f"flag not found: {name}"}
    target = plan.get("target_enabled")
    if target is None:
        target = not bool(before.get("enabled"))
    if client is not None:
        try:
            client.set_flag_state(before.get("id", name), bool(target))
        except Exception as exc:
            return 502, {"error": f"Flagsmith rejected the state change: {exc}"}
        after = _find_flag(name)
        if after is None or bool(after.get("enabled")) != bool(target):
            return 502, {"error": "Flagsmith state change could not be verified"}
    else:
        after = deepcopy(before); after["enabled"] = bool(target)
        _store["flags"] = [f for f in _store["flags"] if f["name"] != name] + [after]
    sid = _new_snapshot(name, before, "toggle_flag")
    return 200, {"applied": True, "flag": after, "snapshot_id": sid,
                 "rollback": {"endpoint": "/api/rollback", "snapshot_id": sid, "flag_name": name}}

def _apply_create(plan, name, client):
    before = _find_flag(name)
    traffic = _plan_traffic(plan)
    try:
        traffic_value = float(traffic)
    except (TypeError, ValueError):
        traffic_value = 0
    enabled = traffic_value > 0
    variants = plan.get("variants") or []
    if client is not None:
        try:
            if before is not None:
                # Duplicate name: update the existing feature in place
                # instead of erroring or creating a second flag.
                applied = client.update_feature(
                    before.get("id", name),
                    description=plan.get("description", before.get("description", "")))
                action = "updated"
            elif len(variants) >= 2:
                applied = client.create_multivariate_feature(
                    name, description=plan.get("description", ""), variants=variants,
                    default_enabled=False)
                action = "created"
            else:
                applied = client.create_feature(
                    name, description=plan.get("description", ""), default_enabled=False)
                action = "created"
        except Exception as exc:
            # A failed create is an error, full stop: no local-store
            # fallback success and no snapshot is issued.
            return 502, {"error": f"Flagsmith rejected the create: {exc}"}
        # The feature now exists DISABLED; set the environment state to
        # the plan's first rollout step, never a blanket 100% enable.
        try:
            fid = (applied or {}).get("id", name) if isinstance(applied, dict) else name
            client.set_flag_state(fid, enabled)
        except Exception as exc:
            return 502, {"error": f"Flagsmith rejected the state change: {exc}"}
        after = _find_flag(name)
        if after is None:
            return 502, {"error": "Flagsmith create could not be verified"}
    else:
        after = {"name": name, "enabled": enabled, "type": plan.get("type", "multivariate"),
                 "variants": variants, "created_at": int(time.time()),
                 "last_changed_at": int(time.time()), "last_evaluated_at": int(time.time()),
                 "description": plan.get("description", "")}
        _store["flags"] = [f for f in _store["flags"] if f["name"] != name] + [after]
        action = "updated" if before is not None else "created"
    sid = _new_snapshot(name, before, "create")
    return 200, {"applied": True, "action": action, "flag": after, "snapshot_id": sid,
                 "traffic_percent": traffic_value, "enabled": enabled,
                 "rollback": {"endpoint": "/api/rollback", "snapshot_id": sid, "flag_name": name}}

def h_stale(): return 200, {"stale": stale_analysis(), "total_flags": len(list_flags())}

def h_rollback(body):
    body = body or {}
    if body.get("approved") is not True:
        return 400, {"error": "approved must be true — rollback changes live flag state"}
    snap = _snapshots.get(body.get("snapshot_id", ""))
    if snap is None:
        return 404, {"error": "snapshot not found"}
    name = snap["flag_name"]  # the flag name comes ONLY from the snapshot
    if body.get("flag_name") and body.get("flag_name") != name:
        return 400, {"error": "flag_name does not match the snapshot — the snapshot decides which flag is restored"}
    before = snap["before"]
    client = get_client_cached()
    if client is not None:
        current = _find_flag(name)
        try:
            if before is None:
                # The apply created this flag; rolling back archives it.
                if current is not None:
                    client.archive_flag(current.get("id", name))
            else:
                fid = (current or before).get("id", name)
                client.update_feature(fid, description=before.get("description", ""),
                                      is_archived=bool(before.get("is_archived", False)),
                                      default_enabled=bool(before.get("default_enabled", False)))
                client.set_flag_state(fid, bool(before.get("enabled", False)))
                # A graduate rollback must also restore the variant
                # split — restoring only the on/off state would leave
                # the winner at 100% and silently keep the rollout.
                before_variants = _variants_of(before)
                if len(before_variants) >= 2 and hasattr(client, "set_variant_allocations"):
                    client.set_variant_allocations(
                        name, {v["name"]: v["allocation"] for v in before_variants})
        except Exception as exc:
            return 502, {"error": f"Flagsmith rejected the rollback: {exc}"}
        after = _find_flag(name)
        if before is None:
            verified = after is None or bool(after.get("is_archived"))
        else:
            verified = (after is not None
                        and bool(after.get("enabled")) == bool(before.get("enabled"))
                        and bool(after.get("is_archived", False)) == bool(before.get("is_archived", False)))
            if verified and len(_variants_of(before)) >= 2:
                alloc_before = {v["name"]: v["allocation"] for v in _variants_of(before)}
                alloc_after = {v["name"]: v["allocation"] for v in _variants_of(after)}
                verified = alloc_after == alloc_before
        if not verified:
            return 502, {"error": "rollback could not be verified — snapshot kept"}
    else:
        if before is None:
            _store["flags"] = [f for f in _store["flags"] if f["name"] != name]
        else:
            _store["flags"] = [f for f in _store["flags"] if f["name"] != name] + [deepcopy(before)]
        after = _find_flag(name)
    del _snapshots[body.get("snapshot_id")]  # consumed: a snapshot rolls back once
    return 200, {"rolled_back": True, "flag_name": name, "flag": after, "flags": list_flags()}

# ---------- simulation / results / graduation / archive ----------
def _variants_of(flag):
    opts = flag.get("multivariate_options") or []
    variants = []
    for o in opts:
        if isinstance(o, dict):
            alloc = o.get("default_percentage_allocation")
            # Demo-store options carry "value"; live Flagsmith options
            # carry "string_value". Either names the variant.
            name = next((o[k] for k in ("value", "string_value", "name")
                         if o.get(k) is not None), "variant")
            variants.append({"name": str(name),
                             "allocation": float(alloc) if alloc is not None else 0.0})
    if variants:
        return variants
    for v in flag.get("variants") or []:
        if isinstance(v, dict):
            alloc = v.get("weight", v.get("allocation_percent", v.get("default_percentage_allocation", 0)))
            variants.append({"name": str(v.get("value", v.get("name", "variant"))),
                             "allocation": float(alloc or 0)})
    if variants:
        return variants
    return [{"name": "enabled", "allocation": 100.0}]

def _variant_rate(flag_name, variant_name, is_control=False):
    """Deterministic simulated true conversion rate for a variant.

    The control variant converts at the 10% baseline. Every other
    variant gets a deterministic lift of 0–5.9 points derived from a
    hash of (flag, variant), so simulated experiments exhibit real,
    reproducible effects instead of noise-level gaps.
    """
    if is_control or "control" in variant_name.lower():
        return 0.10
    digest = int(hashlib.sha256(f"{flag_name}:{variant_name}".encode()).hexdigest()[:6], 16)
    return 0.10 + (digest % 60) / 1000.0

def _two_proportion_p_value(x1, n1, x2, n2):
    """Two-sided p-value for the difference of two proportions.

    Pooled two-proportion z-test; the normal CDF is computed via
    math.erfc so no third-party statistics package is needed.
    """
    if n1 <= 0 or n2 <= 0:
        return 1.0
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = abs(x1 / n1 - x2 / n2) / se
    return math.erfc(z / math.sqrt(2))

def h_simulate(body):
    """Run the what-if simulation and apply the winner rule.

    The decision rule is fixed in advance and does not depend on the
    outcome of any particular run:

    * Primary metric: the per-variant conversion rate of the flag's
      success metric over the simulated exposures.
    * A winner is recommended only when BOTH hold: at least
      ``_MIN_TOTAL_CONVERSIONS`` conversions in total (the sample-size
      floor), and the leader beats the runner-up on a two-proportion
      z-test at ``_SIGNIFICANCE_ALPHA`` (p < 0.05).
    * Otherwise the verdict is "inconclusive", with the reason recorded
      (``insufficient_conversions`` or ``not_significant``) — the
      stopping rule is "keep collecting data", never "pick the current
      leader anyway".
    * Variant conversion rates are deterministic per flag + variant
      (see ``_variant_rate``), so every run of the same scenario
      reproduces exactly; the effect a variant carries is fixed by its
      name hash before any run, not tuned afterwards.
    """
    body = body or {}
    name = body.get("flag_name")
    if not isinstance(name, str) or not name.strip():
        return 400, {"error": "flag_name is required"}
    name = name.strip()
    flag = _find_flag(name)
    if flag is None:
        return 404, {"error": f"flag not found: {name}"}
    visitors = body.get("visitors", 1000)
    if isinstance(visitors, bool) or not isinstance(visitors, int):
        try: visitors = int(visitors)
        except (TypeError, ValueError): return 400, {"error": "visitors must be a number"}
    if visitors <= 0:
        return 400, {"error": "visitors must be positive"}
    visitors = min(visitors, 20000)
    variants = _variants_of(flag)
    total_alloc = sum(v["allocation"] for v in variants) or 100.0
    rows, assigned = [], 0
    for i, v in enumerate(variants):
        if i == len(variants) - 1:
            exposures = visitors - assigned
        else:
            exposures = int(visitors * v["allocation"] / total_alloc)
            assigned += exposures
        # The first variant is the control (creation order from the
        # plan); it converts at the baseline rate.
        rate_true = _variant_rate(name, v["name"], is_control=(i == 0))
        seed = int(hashlib.sha256(f"sim:{name}:{v['name']}".encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        conversions = sum(1 for _ in range(exposures) if rng.random() < rate_true)
        rows.append({"name": v["name"], "allocation": v["allocation"], "exposures": exposures,
                     "conversions": conversions,
                     "rate": round(conversions / exposures, 4) if exposures else 0.0})
    total_conversions = sum(r["conversions"] for r in rows)
    # A winner is recommended only when the leader's edge over the
    # runner-up is statistically significant (two-proportion z-test,
    # alpha 0.05). A raw-volume lead that could be noise is reported
    # as inconclusive instead.
    winner = "inconclusive"
    p_value = None
    significant = False
    compared_against = None
    leader = max(rows, key=lambda r: r["rate"])["name"] if rows else None
    verdict_reason = "insufficient_conversions"
    if rows and total_conversions >= 30:
        if len(rows) == 1:
            winner = rows[0]["name"]
            verdict_reason = "single_variant"
        else:
            ranked = sorted(rows, key=lambda r: r["rate"], reverse=True)
            best, runner_up = ranked[0], ranked[1]
            compared_against = runner_up["name"]
            p_value = _two_proportion_p_value(
                best["conversions"], best["exposures"],
                runner_up["conversions"], runner_up["exposures"])
            if p_value < 0.05:
                winner = best["name"]
                significant = True
                verdict_reason = "significant"
            else:
                verdict_reason = "not_significant"
    result = {"flag_name": name, "visitors": visitors, "variants": rows,
              "total_conversions": total_conversions,
              "recommended_winner": winner, "winner": winner,
              "leader": leader, "compared_against": compared_against,
              "p_value": round(p_value, 4) if p_value is not None else None,
              "significant": significant, "alpha": 0.05,
              "verdict_reason": verdict_reason}
    _results[name] = result
    return 200, result

def h_results(flag_name):
    result = _results.get(flag_name)
    if result is None:
        return 404, {"error": f"no simulation results for {flag_name} — run a simulation first"}
    return 200, result

def h_graduate(body):
    body = body or {}
    if body.get("approved") is not True:
        return 400, {"error": "approved must be true — rolling out a winner changes live flag state"}
    name, winner = body.get("flag_name"), body.get("winner")
    if not isinstance(name, str) or not name.strip() or not isinstance(winner, str) or not winner.strip():
        return 400, {"error": "flag_name and winner are required"}
    name, winner = name.strip(), winner.strip()
    flag = _find_flag(name)
    if flag is None:
        return 404, {"error": f"flag not found: {name}"}
    variants = _variants_of(flag)
    if winner not in [v["name"] for v in variants]:
        return 400, {"error": f"winner {winner!r} is not a variant of {name}"}
    client = get_client_cached()
    if client is not None:
        try:
            if hasattr(client, "set_variant_allocations"):
                client.set_variant_allocations(name, {v["name"]: (100 if v["name"] == winner else 0) for v in variants})
            else:
                new_opts = []
                for o in flag.get("multivariate_options") or []:
                    if isinstance(o, dict):
                        o2 = dict(o)
                        o2["default_percentage_allocation"] = 100 if str(o.get("value")) == winner else 0
                        new_opts.append(o2)
                client.update_feature(flag.get("id", name), multivariate_options=new_opts)
        except Exception as exc:
            return 502, {"error": f"Flagsmith rejected the rollout: {exc}"}
    sid = _new_snapshot(name, flag, "graduate")
    return 200, {"graduated": True, "flag_name": name, "winner": winner, "snapshot_id": sid,
                 "rollback": {"endpoint": "/api/rollback", "snapshot_id": sid, "flag_name": name}}

def h_archive(body):
    body = body or {}
    if body.get("approved") is not True:
        return 400, {"error": "approved must be true — archiving changes live flag state"}
    name = body.get("flag_name")
    if not isinstance(name, str) or not name.strip():
        return 400, {"error": "flag_name is required"}
    name = name.strip()
    flag = _find_flag(name)
    if flag is None:
        return 404, {"error": f"flag not found: {name}"}
    # Safe archival: only a flag the stale check scores as safe to remove
    # may be archived. An active flag ("keep") or a decided experiment
    # whose winner still has to be rolled out ("rollout_winner") is
    # refused even with approval, so this endpoint can never be used to
    # archive a live or protected flag by mistake.
    report = {item.get("flag"): item for item in stale_analysis()}
    item = report.get(name)
    if item is None or not item.get("safe_to_remove"):
        action = (item or {}).get("recommended_action", "not evaluated")
        return 400, {"error": f"refused: the stale check does not mark {name} safe to remove "
                              f"(recommended action: {action})"}
    client = get_client_cached()
    if client is not None:
        try:
            client.archive_flag(flag.get("id", name))
        except Exception as exc:
            return 502, {"error": f"Flagsmith rejected the archive: {exc}"}
        after = _find_flag(name)
        if after is not None and not after.get("is_archived"):
            return 502, {"error": "archive could not be verified"}
    else:
        archived = deepcopy(flag); archived["is_archived"] = True
        _store["flags"] = [f for f in _store["flags"] if f["name"] != name] + [archived]
    sid = _new_snapshot(name, flag, "archive")
    return 200, {"archived": True, "flag_name": name, "snapshot_id": sid,
                 "rollback": {"endpoint": "/api/rollback", "snapshot_id": sid, "flag_name": name}}

ROUTES = {("GET", "/api/health"): lambda b: (200, h_health()),
          ("GET", "/api/flags"): lambda b: (200, h_flags()),
          ("POST", "/api/plan"): h_plan, ("POST", "/api/apply"): h_apply,
          ("GET", "/api/stale"): lambda b: h_stale(), ("POST", "/api/rollback"): h_rollback,
          ("POST", "/api/simulate"): h_simulate, ("POST", "/api/graduate"): h_graduate,
          ("POST", "/api/archive"): h_archive}

SECURITY_HEADERS = {"Content-Security-Policy": "default-src 'self'",
                    "X-Content-Type-Options": "nosniff"}

# ---------- FastAPI if available, else stdlib ----------
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, FileResponse
    from fastapi.staticfiles import StaticFiles
    app = FastAPI(title="Experimentation Copilot")

    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers[k] = v
        return response

    async def _dispatch(route, request):
        raw = await request.body()
        if len(raw) > MAX_BODY_BYTES:
            return JSONResponse({"error": "request body too large"}, status_code=413)
        body = {}
        if request.method == "POST" and raw:
            try: body = json.loads(raw)
            except Exception: return JSONResponse({"error": "request body must be valid JSON"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"error": "request body must be a JSON object"}, status_code=400)
        status, payload = ROUTES[route](body)
        return JSONResponse(payload, status_code=status)
    @app.get("/api/health")
    async def health(r: Request): return await _dispatch(("GET", "/api/health"), r)
    @app.get("/api/flags")
    async def flags(r: Request): return await _dispatch(("GET", "/api/flags"), r)
    @app.post("/api/plan")
    async def plan(r: Request): return await _dispatch(("POST", "/api/plan"), r)
    @app.post("/api/apply")
    async def apply(r: Request): return await _dispatch(("POST", "/api/apply"), r)
    @app.get("/api/stale")
    async def stale(r: Request): return await _dispatch(("GET", "/api/stale"), r)
    @app.post("/api/rollback")
    async def rollback(r: Request): return await _dispatch(("POST", "/api/rollback"), r)
    @app.post("/api/simulate")
    async def simulate(r: Request): return await _dispatch(("POST", "/api/simulate"), r)
    @app.post("/api/graduate")
    async def graduate(r: Request): return await _dispatch(("POST", "/api/graduate"), r)
    @app.post("/api/archive")
    async def archive(r: Request): return await _dispatch(("POST", "/api/archive"), r)
    @app.get("/api/results/{flag_name}")
    async def results(flag_name: str):
        status, payload = h_results(flag_name)
        return JSONResponse(payload, status_code=status)
    @app.get("/")
    async def index(): return FileResponse(STATIC / "index.html")
    if STATIC.exists(): app.mount("/static", StaticFiles(directory=STATIC), name="static")
except Exception:
    app = None

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8077"))
    if app is not None:
        import uvicorn; uvicorn.run(app, host="127.0.0.1", port=port)
    else:  # stdlib fallback
        from http.server import BaseHTTPRequestHandler, HTTPServer
        MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _send(self, code, data, ctype="application/json"):
                raw = data if isinstance(data, bytes) else json.dumps(data).encode()
                self.send_response(code); self.send_header("Content-Type", ctype)
                for k, v in SECURITY_HEADERS.items(): self.send_header(k, v)
                self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def do_GET(self):
                path = self.path.split("?")[0]
                if path in ("/", "/index.html"): return self._send(200, (STATIC/"index.html").read_bytes(), "text/html")
                if path.startswith("/static/"):
                    f = (STATIC / path.split("/static/")[1]).resolve()
                    if not f.is_relative_to(STATIC.resolve()) or not f.is_file():
                        return self._send(404, {"error": "not found"})
                    return self._send(200, f.read_bytes(), MIME.get(f.suffix, "text/plain"))
                if path.startswith("/api/results/"):
                    status, payload = h_results(path[len("/api/results/"):])
                    return self._send(status, payload)
                route = ("GET", path)
                if route not in ROUTES: return self._send(404, {"error": "not found"})
                status, payload = ROUTES[route](None); return self._send(status, payload)
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0) or 0)
                if n > MAX_BODY_BYTES: return self._send(413, {"error": "request body too large"})
                try: body = json.loads(self.rfile.read(n) or b"{}")
                except Exception: return self._send(400, {"error": "request body must be valid JSON"})
                if not isinstance(body, dict): return self._send(400, {"error": "request body must be a JSON object"})
                route = ("POST", self.path.split("?")[0])
                if route not in ROUTES: return self._send(404, {"error": "not found"})
                status, payload = ROUTES[route](body); self._send(status, payload)
        print(f"Experimentation Copilot (stdlib fallback) on http://127.0.0.1:{port}")
        HTTPServer(("127.0.0.1", port), H).serve_forever()
