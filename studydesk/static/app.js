"use strict";
const $ = (id) => document.getElementById(id);
let currentPlan = null;
let busy = false;
let liveAvailable = false;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function notice(message, error = false) {
  $("notice").textContent = message;
  $("notice").className = error ? "error" : "";
  $("notice").hidden = false;
}

function setBusy(value) {
  busy = value;
  $("plan-button").disabled = value;
  $("execute-button").disabled = value || !currentPlan || !currentPlan.actions.length ||
    (currentPlan.warnings.length > 0 && !$("confirmation").checked);
  $("cancel-button").disabled = value || !currentPlan;
  $("prompt").disabled = value;
  $("mode").disabled = value;
  document.querySelectorAll("[data-example], .note-button").forEach(button => { button.disabled = value; });
  $("plan-button").textContent = value ? "Working…" : "Build a plan ↗";
}

async function api(path, payload) {
  let response;
  try {
    response = await fetch(path, payload === undefined ? {} : {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
    });
  } catch (_) { throw new Error("Could not reach the server. Check that the app is running, then refresh."); }
  let data;
  try { data = await response.json(); }
  catch (_) { throw new Error("The server returned an unreadable response. Refresh and try again."); }
  if (!response.ok) throw new Error(data.error || "The request could not be completed.");
  return data;
}

function fillList(id, values, render, empty) {
  const list = $(id);
  list.replaceChildren();
  if (!values.length) list.append(node("li", empty, "empty"));
  else values.forEach(value => { const item = node("li"); render(item, value); list.append(item); });
}

async function refresh() {
  const state = await api("/api/state");
  $("note-count").textContent = state.notes.length;
  $("task-count").textContent = state.tasks.filter(t => !t.done).length;
  fillList("notes", state.notes, (item, name) => {
    const button = node("button", "▤  " + name, "note-button");
    button.type = "button";
    button.disabled = busy;
    button.addEventListener("click", () => { if (!busy) { $("prompt").value = "Read note " + name; $("prompt").focus(); } });
    item.append(button);
  }, "A fresh start. Your notes will appear here.");
  fillList("tasks", state.tasks, (item, task) => {
    if (task.done) item.className = "task-done";
    item.append(node("span", "#" + task.id, "task-id"), node("span", (task.done ? "✓ " : "○ ") + task.title));
  }, "Nothing on your list just yet.");
  $("audit-count").textContent = state.audit.length + " events";
  $("audit").replaceChildren();
  state.audit.forEach(event => {
    const entry = node("div", undefined, "audit-entry");
    entry.append(node("time", event.at), node("span", event.event), node("code", event.detail));
    $("audit").append(entry);
  });
  liveAvailable = state.live_available;
}

function renderPlan(plan) {
  currentPlan = plan;
  $("plan-card").hidden = false;
  $("results-card").hidden = true;
  $("plan-summary").textContent = plan.summary;
  $("actions").replaceChildren();
  plan.actions.forEach(action => {
    const item = node("li");
    item.append(node("strong", action.tool), node("pre", JSON.stringify(action.arguments, null, 2)));
    $("actions").append(item);
  });
  $("warnings").replaceChildren(...plan.warnings.map(warning => node("li", warning)));
  $("risk-box").hidden = !plan.warnings.length;
  $("confirmation").checked = false;
}

$("request-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (busy) return;
  const prompt = $("prompt").value.trim();
  if (!prompt) return;
  // A newly requested plan replaces the displayed plan. Old plans are not auto-executed.
  currentPlan = null;
  $("plan-card").hidden = true;
  $("results-card").hidden = true;
  setBusy(true);
  notice(document.querySelector('input[name="mode"]:checked').value === "demo" ? "Building an offline demo plan…" : "Asking OpenAI for a plan. Temporary API errors are retried up to three times…");
  try {
    const plan = await api("/api/plan", {prompt, mode: document.querySelector('input[name="mode"]:checked').value});
    renderPlan(plan);
    notice(plan.actions.length ? "Your plan is ready. Review each action before executing." : plan.summary);
    await refresh();
  } catch (error) { notice(error.message, true); }
  finally { setBusy(false); }
});

$("confirmation").addEventListener("change", () => setBusy(busy));
$("execute-button").addEventListener("click", async () => {
  if (busy || !currentPlan) return;
  setBusy(true);
  notice("Executing your reviewed plan…");
  try {
    const result = await api("/api/execute", {plan_id: currentPlan.id, confirmed: $("confirmation").checked});
    currentPlan = null;
    $("plan-card").hidden = true;
    $("results-card").hidden = false;
    $("results").replaceChildren();
    result.results.forEach(item => {
      const block = node("div", undefined, "result");
      const title = node("div", undefined, "result-title");
      title.append(node("span", item.status === "success" ? "DONE" : "FAILED", "result-badge" + (item.status === "error" ? " error" : "")), node("strong", item.tool));
      block.append(title, node("pre", item.error || JSON.stringify(item.result, null, 2)));
      $("results").append(block);
    });
    notice(result.status === "completed" ? "All actions completed. Your workspace is up to date." :
      "Execution stopped after an error. Earlier successful actions remain saved. " + result.skipped + " action(s) skipped.", result.status !== "completed");
    await refresh();
  } catch (error) {
    // If the network failed after execution, do not offer blind replay.
    currentPlan = null;
    $("plan-card").hidden = true;
    notice(error.message + " Check the activity log and create a fresh plan before retrying.", true);
    try { await refresh(); } catch (_) { /* original error remains visible */ }
  } finally { setBusy(false); }
});

$("cancel-button").addEventListener("click", async () => {
  if (busy || !currentPlan) return;
  setBusy(true);
  try {
    await api("/api/cancel", {plan_id: currentPlan.id});
    currentPlan = null;
    $("plan-card").hidden = true;
    notice("Plan cancelled. No actions were executed.");
    await refresh();
  } catch (error) { notice(error.message, true); }
  finally { setBusy(false); }
});

document.querySelectorAll("[data-example]").forEach(button => {
  button.addEventListener("click", () => {
    if (busy) return;
    $("prompt").value = button.dataset.example;
    $("prompt").focus();
  });
});
$("mode").addEventListener("change", () => {
  $("mode-info").textContent = document.querySelector('input[name="mode"]:checked').value === "demo" ?
    "Offline demo uses example commands, without an LLM or API key." :
    (liveAvailable ? "OpenAI interprets flexible natural language. Requests and the note/task inventory are sent to the API." :
      "OpenAI needs a server API key. Set OPENAI_API_KEY and restart the app, or use Offline demo.");
});
refresh().catch(error => notice(error.message, true));
