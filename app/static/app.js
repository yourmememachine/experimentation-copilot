const $ = s => document.querySelector(s);
let currentPlan = null, lastGuardrails = null, lastSnapshot = null, lastSnapshotFlag = null;
let lastWinner = null, lastWinnerFlag = null, gradSnapshot = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || ("Request failed: " + r.status));
  return data;
}
const post = (path, body) => api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});

function setLoading(btn, on, busyLabel) {
  if (!btn) return;
  if (on) { btn.dataset.label = btn.textContent; btn.disabled = true; if (busyLabel) btn.textContent = busyLabel; }
  else { btn.disabled = false; if (btn.dataset.label) btn.textContent = btn.dataset.label; }
}

async function loadHealth() {
  try { const h = await api("/api/health");
    $("#health").textContent = h.demo_mode
      ? "Using sample flags — add a Flagsmith token for live mode"
      : "Connected to Flagsmith (live)";
  } catch { $("#health").textContent = "Could not reach the server."; }
}

function variantWeight(v) {
  const w = Number(v.weight ?? v.allocation_percent ?? v.default_percentage_allocation ?? v.allocation);
  return Number.isFinite(w) ? Math.min(100, Math.max(0, w)) : 0;
}
function variantName(v) { return v.name || v.value || "variant"; }

function splitBar(variants) {
  const colours = ["#2563eb", "#f59e0b", "#10b981", "#8b5cf6"];
  return '<div class="splitbar">' + variants.map((v, i) =>
    `<span style="width:${variantWeight(v)}%;background:${colours[i % 4]}" title="${escapeHtml(variantName(v))} ${variantWeight(v)}%"></span>`).join("") + "</div>" +
    '<p class="splitlabels">' + variants.map(v => `${escapeHtml(variantName(v))}: ${variantWeight(v)}%`).join(" · ") + "</p>";
}

function rolloutLine(plan) {
  const steps = (plan.rollout_steps || []).map(s => Number(s.traffic_percent)).filter(Number.isFinite);
  if (!steps.length) return "";
  let line = `Starts at ${steps[0]}% of users`;
  if (steps.length > 1) line += `, ramps ${steps.slice(1).join("% → ")}%`;
  let html = `<p class="rollout">${escapeHtml(line)}</p>`;
  const traffic = Number(plan.traffic_percent ?? plan.traffic_percentage);
  const variants = plan.variants || [];
  if (Number.isFinite(traffic) && variants.length >= 2) {
    const split = variants.map(v => `${escapeHtml(variantName(v))} ${variantWeight(v)}%`).join(" / ");
    html += `<p class="rollout">${traffic}% of users enter the experiment; split ${split} inside the experiment.</p>`;
  }
  return html;
}

function updateApplyState() {
  $("#applyBtn").disabled = !(lastGuardrails && lastGuardrails.passed && $("#approveBox").checked);
}

function renderPlan(plan, guardrails) {
  currentPlan = plan;
  lastGuardrails = guardrails || {blocks: [], warnings: [], passed: true};
  // A new plan invalidates the previous apply's result and rollback.
  lastSnapshot = null; lastSnapshotFlag = null;
  $("#applyResult").innerHTML = "";
  $("#rollbackBtn").classList.add("hidden");
  $("#planBody").innerHTML =
    `<p><strong>Flag:</strong> <code>${escapeHtml(plan.flag_name || plan.name || "")}</code></p>
     <p><strong>Hypothesis:</strong> ${escapeHtml(plan.hypothesis || "—")}</p>
     <p><strong>Success metric:</strong> ${escapeHtml(plan.metric || plan.success_metric || "—")} &nbsp;·&nbsp; <strong>Intent:</strong> ${escapeHtml(plan.intent || "—")}</p>
     <p><strong>Variants &amp; traffic split</strong></p>${splitBar(plan.variants || [])}${rolloutLine(plan)}`;
  const g = lastGuardrails;
  const blocks = g.blocks || [], warnings = g.warnings || [];
  let state;
  if (blocks.length) state = '<p class="block">Blocked — fix the items below before this plan can be applied.</p>';
  else if (warnings.length) state = '<p class="warn">Passed with warnings — review before approving.</p>';
  else state = '<p class="pass">Passed.</p>';
  $("#guardrails").innerHTML = state +
    blocks.map(b => `<p class="block">Blocked: ${escapeHtml(b)}</p>`).join("") +
    warnings.map(w => `<p class="warn">Warning: ${escapeHtml(w)}</p>`).join("") +
    (g.rollback ? `<p class="splitlabels">Rollback: ${escapeHtml(g.rollback)}</p>` : "");
  $("#approveBox").checked = false;
  updateApplyState();
  $("#planCard").classList.remove("hidden");
}

$("#planBtn").onclick = async () => {
  $("#planError").textContent = "";
  setLoading($("#planBtn"), true, "Drafting…");
  try { const d = await post("/api/plan", {prompt: $("#prompt").value}); renderPlan(d.plan, d.guardrails); }
  catch (e) { $("#planError").textContent = e.message; }
  finally { setLoading($("#planBtn"), false); }
};
// Example chips fill the prompt box only — drafting is a separate click.
document.querySelectorAll(".ex").forEach(b => b.onclick = () => { $("#prompt").value = b.dataset.p; $("#prompt").focus(); });
$("#approveBox").onchange = updateApplyState;

$("#applyBtn").onclick = async () => {
  setLoading($("#applyBtn"), true, "Applying…");
  try { const d = await post("/api/apply", {plan_id: currentPlan.id, approved: $("#approveBox").checked});
    lastSnapshot = d.snapshot_id; lastSnapshotFlag = d.flag.name || d.flag;
    $("#applyResult").innerHTML =
      `Applied. Flag <code>${escapeHtml(d.flag.name || "")}</code> is set up` +
      (d.traffic_percent != null ? ` starting at ${escapeHtml(d.traffic_percent)}% of users` : "") +
      `. Snapshot <code>${escapeHtml(d.snapshot_id)}</code> saved for rollback.` +
      ` <span class="nextsteps">Next: <a href="#flagsSection">view your flags</a> · <a href="#staleSection">check stale flags</a></span>`;
    $("#rollbackBtn").classList.remove("hidden");
    if (d.flag.name) $("#simFlag").value = d.flag.name;
    loadFlags();
  } catch (e) { $("#applyResult").textContent = e.message; }
  finally { setLoading($("#applyBtn"), false); updateApplyState(); }
};

$("#rollbackBtn").onclick = async () => {
  if (!lastSnapshot) return;
  if (!confirm(`Roll back ${lastSnapshotFlag || "this flag"} to the state saved before the apply?`)) return;
  try { const d = await post("/api/rollback", {snapshot_id: lastSnapshot, approved: true});
    $("#applyResult").textContent = "Rolled back: " + d.flag_name;
    $("#rollbackBtn").classList.add("hidden"); lastSnapshot = null; lastSnapshotFlag = null;
    loadFlags();
  } catch (e) { $("#applyResult").textContent = e.message; }
};

async function loadFlags() {
  setLoading($("#flagsBtn"), true, "Refreshing…");
  $("#flagsError").textContent = "";
  try {
    const d = await api("/api/flags");
    if (d.client_available === false) $("#flagsError").textContent = d.error || "Flagsmith is unavailable right now.";
    document.querySelector("#flagsTable tbody").innerHTML = d.flags.map(f => {
      const vars = (f.variants && f.variants.length) ? f.variants.map(v => escapeHtml(variantName(v)) + " " + variantWeight(v) + "%")
        : (f.multivariate_options || []).map(v => escapeHtml(v.value) + " " + (Number.isFinite(Number(v.default_percentage_allocation)) ? Number(v.default_percentage_allocation) : 0) + "%");
      return `<tr><td><code>${escapeHtml(f.name)}</code></td><td>${f.enabled ? "Enabled" : "Disabled"}${f.is_archived ? " (archived)" : ""}</td><td>${escapeHtml(f.type || "boolean")}</td>
       <td>${vars.join(", ") || "—"}</td><td>${escapeHtml(f.description || "")}</td></tr>`; }).join("");
  } catch (e) { $("#flagsError").textContent = e.message; }
  finally { setLoading($("#flagsBtn"), false); }
}
$("#flagsBtn").onclick = loadFlags;

function renderResults(d) {
  lastWinnerFlag = d.flag_name;
  lastWinner = (d.recommended_winner && d.recommended_winner !== "inconclusive") ? d.recommended_winner : null;
  const rows = (d.variants || []).map(v =>
    `<tr><td><code>${escapeHtml(v.name)}</code></td><td>${escapeHtml(v.exposures)}</td><td>${escapeHtml(v.conversions)}</td><td>${escapeHtml(v.rate)}</td></tr>`).join("");
  $("#resultsBody").innerHTML =
    `<table><thead><tr><th>Variant</th><th>Exposures</th><th>Conversions</th><th>Rate</th></tr></thead><tbody>${rows}</tbody></table>` +
    (lastWinner
      ? `<p class="pass">Recommended winner: <strong>${escapeHtml(lastWinner)}</strong> (${escapeHtml(d.total_conversions)} conversions in total).</p>`
      : `<p class="warn">Result so far: inconclusive — fewer than 30 conversions in total, so no winner is recommended yet.</p>`);
  $("#graduateBtn").classList.toggle("hidden", !lastWinner);
  $("#gradRollbackBtn").classList.add("hidden");
  $("#graduateResult").textContent = "";
}

$("#simBtn").onclick = async () => {
  $("#simError").textContent = "";
  setLoading($("#simBtn"), true, "Simulating…");
  try {
    const visitors = Number($("#simVisitors").value) || 1000;
    const d = await post("/api/simulate", {flag_name: $("#simFlag").value.trim(), visitors});
    renderResults(d);
  } catch (e) { $("#simError").textContent = e.message; }
  finally { setLoading($("#simBtn"), false); }
};

$("#graduateBtn").onclick = async () => {
  if (!lastWinner || !lastWinnerFlag) return;
  if (!confirm(`Roll out ${lastWinner} to 100% for ${lastWinnerFlag}?`)) return;
  setLoading($("#graduateBtn"), true, "Rolling out…");
  try { const d = await post("/api/graduate", {flag_name: lastWinnerFlag, winner: lastWinner, approved: true});
    gradSnapshot = d.snapshot_id;
    $("#graduateResult").innerHTML = `Rolled out. <code>${escapeHtml(d.winner)}</code> now receives 100% for <code>${escapeHtml(d.flag_name)}</code>. Snapshot <code>${escapeHtml(d.snapshot_id)}</code> saved for rollback.`;
    $("#gradRollbackBtn").classList.remove("hidden");
    loadFlags();
  } catch (e) { $("#graduateResult").textContent = e.message; }
  finally { setLoading($("#graduateBtn"), false); }
};

$("#gradRollbackBtn").onclick = async () => {
  if (!gradSnapshot) return;
  if (!confirm(`Roll back the rollout for ${lastWinnerFlag || "this flag"}?`)) return;
  try { const d = await post("/api/rollback", {snapshot_id: gradSnapshot, approved: true});
    $("#graduateResult").textContent = "Rolled back: " + d.flag_name;
    $("#gradRollbackBtn").classList.add("hidden"); gradSnapshot = null;
    loadFlags();
  } catch (e) { $("#graduateResult").textContent = e.message; }
};

$("#staleBtn").onclick = async () => {
  $("#staleError").textContent = "";
  setLoading($("#staleBtn"), true, "Checking…");
  try {
    const d = await api("/api/stale");
    $("#staleBody").innerHTML = d.stale.length ? d.stale.map(s =>
      `<div class="staleitem"><p><strong><code>${escapeHtml(s.flag)}</code></strong> — stale score ${escapeHtml(s.stale_score ?? s.score)}/100${s.age_days != null ? " · " + escapeHtml(s.age_days) + " days old" : ""}${s.safe_to_remove ? " · safe to remove" : ""}</p>
       <p>${(s.reasons || []).map(escapeHtml).join(" · ")}</p><p><strong>Recommended:</strong> ${escapeHtml(s.recommended_action)}</p>
       <button class="ghost archiveBtn" data-flag="${escapeHtml(s.flag)}">Approve &amp; archive</button></div>`).join("")
      : "<p>No stale flags found. Nice and tidy.</p>";
    document.querySelectorAll(".archiveBtn").forEach(b => b.onclick = async () => {
      const flag = b.dataset.flag;
      if (!confirm(`Archive ${flag}? It will stop being served to clients.`)) return;
      setLoading(b, true, "Archiving…");
      try { await post("/api/archive", {flag_name: flag, approved: true});
        b.closest(".staleitem").remove(); loadFlags();
      } catch (e) { $("#staleError").textContent = e.message; setLoading(b, false); }
    });
  } catch (e) { $("#staleError").textContent = e.message; }
  finally { setLoading($("#staleBtn"), false); }
};
loadHealth(); loadFlags();
