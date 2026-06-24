"use strict";

const state = {
  scope: "workspace",
  runId: null,
  snapshot: null,
  stream: null,
  activityView: "conversation",
  inspectorView: "state",
  logFilter: "all",
  openFolders: new Set([""]),
  previousFiles: new Map(),
  selectedFile: null,
  selectedFileMtime: null,
  fileData: null,
  initializedTree: false,
  defaultSystemPrompt: "",
  systemPrompt: "",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function icon(name) {
  const node = document.createElement("i");
  node.setAttribute("data-lucide", name);
  return node;
}

function refreshIcons(root = document) {
  if (window.lucide) window.lucide.createIcons({ attrs: { "aria-hidden": "true" }, root });
}

function showToast(message, isError = false) {
  const toast = element("div", `toast${isError ? " is-error" : ""}`, message);
  $("#toast-region").append(toast);
  setTimeout(() => toast.remove(), 4200);
}

function setConnection(value) {
  const connection = $("#connection-status");
  connection.dataset.state = value;
  connection.querySelector(".connection-label").textContent = value === "live" ? "Live" : value === "offline" ? "Mất kết nối" : "Đang kết nối";
}

function compactRunId(runId) {
  if (!runId) return "No runs";
  return runId.length > 27 ? `${runId.slice(0, 18)}…${runId.slice(-7)}` : runId;
}

function formatTime(timestamp, includeSeconds = true) {
  if (!timestamp) return "--:--";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "--:--";
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit", minute: "2-digit", second: includeSeconds ? "2-digit" : undefined, hour12: false,
  }).format(date);
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function safeJson(value) {
  try { return JSON.stringify(value ?? {}, null, 2); }
  catch { return "{}"; }
}

function parseJson(text) {
  if (typeof text !== "string") return null;
  const trimmed = text.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try { return JSON.parse(trimmed); }
  catch { return null; }
}

function renderRunPicker(runs, selectedRunId) {
  const select = $("#run-select");
  const previous = select.value;
  select.replaceChildren();
  if (!runs.length) {
    const option = element("option", "", "No runs yet");
    option.value = "";
    select.append(option);
    return;
  }
  runs.forEach((run) => {
    const option = element("option", "", `${compactRunId(run.run_id)} · ${run.status}`);
    option.value = run.run_id;
    option.title = run.prompt || run.run_id;
    select.append(option);
  });
  select.value = selectedRunId || previous || runs[0].run_id;
}

function flattenTree(node, map = new Map()) {
  if (!node) return map;
  map.set(node.path, { mtime: node.mtime_ns, size: node.size, type: node.type });
  (node.children || []).forEach((child) => flattenTree(child, map));
  return map;
}

function fileChangeFor(node, currentMap) {
  if (!state.initializedTree) return null;
  const old = state.previousFiles.get(node.path);
  if (!old) return "new";
  const current = currentMap.get(node.path);
  return old.mtime !== current.mtime || old.size !== current.size ? "changed" : null;
}

function renderTreeNode(node, depth, currentMap) {
  if (node.type === "directory") {
    const details = element("details", "tree-folder");
    details.open = state.openFolders.has(node.path) || depth === 0;
    details.addEventListener("toggle", () => {
      if (details.open) state.openFolders.add(node.path);
      else state.openFolders.delete(node.path);
    });
    const summary = element("summary");
    const row = element("div", "tree-row folder-row");
    row.style.paddingLeft = `${8 + depth * 13}px`;
    row.append(element("span", "tree-caret", "›"), icon("folder"), element("span", "tree-name", node.name));
    summary.append(row);
    details.append(summary);
    const children = element("div", "tree-children");
    (node.children || []).forEach((child) => children.append(renderTreeNode(child, depth + 1, currentMap)));
    details.append(children);
    return details;
  }

  const row = element("button", "tree-row");
  row.type = "button";
  row.style.paddingLeft = `${20 + depth * 13}px`;
  row.title = node.path;
  row.dataset.path = node.path;
  if (state.selectedFile && state.selectedFile.scope === state.scope && state.selectedFile.path === node.path) row.classList.add("is-selected");
  const change = fileChangeFor(node, currentMap);
  if (change) {
    row.classList.add(change === "new" ? "is-new" : "is-changed", "flash");
  }
  row.append(icon(node.type === "symlink" ? "file-symlink" : "file-code-2"), element("span", "tree-name", node.name));
  if (change) row.append(element("span", "tree-change", change));
  row.addEventListener("click", () => openFile(node));
  return row;
}

function renderTree(files) {
  const tree = $("#file-tree");
  const currentMap = flattenTree(files.tree);
  const selectedMeta = state.selectedFile ? currentMap.get(state.selectedFile.path) : null;
  if (selectedMeta && state.selectedFileMtime && selectedMeta.mtime !== state.selectedFileMtime) {
    $("#file-change-dot").classList.add("is-active");
    if (state.inspectorView === "file") openFile({ path: state.selectedFile.path, mtime_ns: selectedMeta.mtime }, true);
  }
  tree.replaceChildren();
  if (files.tree) tree.append(renderTreeNode(files.tree, 0, currentMap));
  else tree.append(element("div", "empty-state", "Folder trống"));
  $("#explorer-title").textContent = files.scope === "workspace" ? "Workspace" : "Project";
  $("#tree-root").textContent = files.root;
  $("#tree-count").textContent = `${files.entries || 0} mục${files.truncated ? "+" : ""}`;
  state.previousFiles = currentMap;
  state.initializedTree = true;
  refreshIcons(tree);
}

function classifyMessage(message) {
  const parsed = parseJson(message.content);
  if (parsed && parsed.capability) return { role: "tool", label: `Tool · ${parsed.capability}`, parsed };
  if (message.role === "assistant" && parsed && parsed.action === "tool") return { role: "assistant", label: `Agent · call ${parsed.tool || "tool"}`, parsed };
  if (message.role === "assistant" && parsed && parsed.action === "final") return { role: "assistant", label: message.agent_id || "Agent", parsed };
  return { role: message.role, label: message.agent_id || message.role, parsed };
}

function messageInitial(role) {
  if (role === "assistant") return "AI";
  if (role === "system") return "S";
  if (role === "tool") return "T";
  return "U";
}

function renderConversation(messages) {
  const container = $("#activity-content");
  const wasNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 90;
  container.replaceChildren();
  if (!messages.length) {
    container.append(element("div", "empty-state", "Chưa có conversation cho run này."));
    return;
  }
  messages.forEach((message) => {
    const info = classifyMessage(message);
    const row = element("article", "message-row");
    row.dataset.role = info.role;
    row.append(element("div", "message-avatar", messageInitial(info.role)));
    const body = element("div", "message-body");
    const meta = element("div", "message-meta");
    meta.append(element("strong", "", info.label), element("span", "role-tag", info.role));
    if (message.final || (info.parsed && info.parsed.action === "final")) meta.append(element("span", "final-tag", "Final"));
    body.append(meta);
    let content = message.content;
    if (info.parsed && info.parsed.action === "final" && info.parsed.message) content = info.parsed.message;
    const contentNode = element("pre", `message-content${info.parsed && !(info.parsed.action === "final" && info.parsed.message) ? " is-json" : ""}`);
    contentNode.textContent = info.parsed && !(info.parsed.action === "final" && info.parsed.message) ? safeJson(info.parsed) : content;
    body.append(contentNode);
    row.append(body);
    container.append(row);
  });
  if (wasNearBottom) container.scrollTop = container.scrollHeight;
}

function eventLabel(event) {
  return event.topic || event.event || event.status || event.kind || "event";
}

function eventDetail(event) {
  const parts = [];
  if (event.tool) parts.push(event.tool);
  if (event.action) parts.push(`action=${event.action}`);
  if (event.step !== undefined) parts.push(`step=${event.step}`);
  if (event.ok !== undefined) parts.push(`ok=${event.ok}`);
  if (event.error) parts.push(event.error);
  return parts.join(" · ") || event.run_id || "";
}

function renderTimeline(events) {
  const container = $("#activity-content");
  container.replaceChildren();
  if (!events.length) {
    container.append(element("div", "empty-state", "Chưa có state event cho run này."));
    return;
  }
  const list = element("div", "timeline");
  events.forEach((event) => {
    const row = element("div", "timeline-item");
    row.dataset.kind = event.kind || "Event";
    row.dataset.failed = String(event.ok === false || event.topic === "tool.failed" || event.status === "failed");
    row.append(element("span", "timeline-time", formatTime(event.timestamp)), element("span", "timeline-track"));
    row.querySelector(".timeline-track").append(element("span", "timeline-marker"));
    const detail = element("div", "timeline-detail");
    detail.append(element("strong", "", eventLabel(event)), element("span", "", eventDetail(event)));
    row.append(detail);
    list.append(row);
  });
  container.append(list);
}

function deriveStages(run) {
  const events = run.events || [];
  const checkpoint = run.checkpoint || {};
  const status = run.status || "idle";
  const has = (predicate) => events.some(predicate);
  const accepted = has((e) => e.topic === "task.accepted");
  const llm = has((e) => e.kind === "LLMCallEvent" || String(e.tool || "").startsWith("llm."));
  const acted = has((e) => e.topic === "tool.requested" && !String(e.tool || "").startsWith("llm."));
  const checkpointed = Boolean(checkpoint.run_id);
  const done = ["completed", "failed"].includes(status);
  const stages = [
    ["Accepted", accepted], ["Thinking", llm], ["Acting", acted], ["Checkpoint", checkpointed], ["Complete", done],
  ];
  let activeIndex = stages.findIndex(([, completed]) => !completed);
  if (activeIndex < 0) activeIndex = stages.length - 1;
  return stages.map(([label, completed], index) => ({ label, completed, active: !done && index === activeIndex }));
}

function renderStages(run) {
  const list = $("#stage-list");
  list.replaceChildren();
  deriveStages(run).forEach((stage) => {
    const node = element("div", `stage${stage.completed ? " is-done" : ""}${stage.active ? " is-active" : ""}`);
    node.append(element("span", "stage-dot"), element("span", "stage-label", stage.label));
    list.append(node);
  });
  const status = run.status || "idle";
  const statusNode = $("#run-status");
  statusNode.textContent = status;
  statusNode.dataset.status = status;
}

function renderMetrics(run) {
  const checkpoint = run.checkpoint || {};
  const metrics = run.summary?.metrics || {};
  const values = [
    ["Status", run.status || "idle"], ["Step", checkpoint.step ?? 0],
    ["LLM calls", metrics.llm_calls ?? countEvents(run.events, "LLMCallEvent")],
    ["Tool calls", countToolCalls(run.events)],
  ];
  const grid = $("#metric-grid");
  grid.replaceChildren();
  values.forEach(([label, value]) => {
    const metric = element("div", "metric");
    metric.append(element("span", "", label), element("strong", "", value));
    grid.append(metric);
  });
  const statePayload = {
    run_id: run.run_id,
    status: run.status,
    step: checkpoint.step ?? 0,
    budget: checkpoint.budget || {},
    state: checkpoint.state || {},
    job: run.job || null,
  };
  $("#state-json").textContent = safeJson(statePayload);
}

function countEvents(events = [], kind) { return events.filter((event) => event.kind === kind).length; }
function countToolCalls(events = []) {
  return events.filter((event) =>
    (event.topic === "tool.completed" || event.topic === "tool.failed") &&
    !String(event.tool || "").startsWith("llm."),
  ).length;
}

function matchesLogFilter(event) {
  if (state.logFilter === "all") return true;
  if (state.logFilter === "kernel") return event.kind === "KernelEvent";
  if (state.logFilter === "llm") return event.kind === "LLMCallEvent";
  return event.kind === "StateEvent";
}

function renderLogs(events) {
  const output = $("#log-output");
  const atBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 60;
  output.replaceChildren();
  events.filter(matchesLogFilter).forEach((event) => {
    const row = element("div", "log-line");
    row.dataset.kind = event.kind || "Event";
    row.dataset.failed = String(event.ok === false || event.topic === "tool.failed" || event.status === "failed");
    row.append(
      element("span", "log-time", formatTime(event.timestamp)),
      element("span", "log-kind", event.kind || "Event"),
      element("span", "log-message", `${eventLabel(event)}${eventDetail(event) ? ` · ${eventDetail(event)}` : ""}`),
    );
    output.append(row);
  });
  if ($("#auto-scroll").checked && (atBottom || !output.dataset.touched)) output.scrollTop = output.scrollHeight;
}

function renderSnapshot(snapshot) {
  state.snapshot = snapshot;
  if (!state.runId) state.runId = snapshot.selected_run_id;
  renderRunPicker(snapshot.runs || [], state.runId || snapshot.selected_run_id);
  renderTree(snapshot.files);
  const run = snapshot.run || {};
  renderStages(run);
  renderMetrics(run);
  renderLogs(run.events || []);
  if (state.activityView === "conversation") renderConversation(run.messages || []);
  else renderTimeline(run.events || []);
  $("#activity-count").textContent = state.activityView === "conversation" ? `${(run.messages || []).length} messages` : `${(run.events || []).length} events`;
}

function connectStream() {
  if (state.stream) state.stream.close();
  setConnection("connecting");
  const params = new URLSearchParams({ scope: state.scope });
  if (state.runId) params.set("run_id", state.runId);
  const stream = new EventSource(`/api/stream?${params}`);
  state.stream = stream;
  stream.addEventListener("snapshot", (event) => {
    if (stream !== state.stream) return;
    setConnection("live");
    try { renderSnapshot(JSON.parse(event.data)); }
    catch (error) { console.error(error); }
  });
  stream.onerror = () => {
    if (stream === state.stream) setConnection("offline");
  };
}

async function refreshSnapshot() {
  const params = new URLSearchParams({ scope: state.scope });
  if (state.runId) params.set("run_id", state.runId);
  const response = await fetch(`/api/snapshot?${params}`);
  if (!response.ok) throw new Error((await response.json()).error || "Không thể tải snapshot");
  renderSnapshot(await response.json());
}

async function openFile(node, quiet = false) {
  state.selectedFile = { scope: state.scope, path: node.path };
  state.selectedFileMtime = node.mtime_ns || state.previousFiles.get(node.path)?.mtime || null;
  try {
    const params = new URLSearchParams({ scope: state.scope, path: node.path });
    const response = await fetch(`/api/file?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Không thể mở file");
    state.fileData = data;
    $("#file-name").textContent = data.name;
    $("#file-path").textContent = data.path;
    $("#file-size").textContent = formatBytes(data.size);
    $("#file-content").textContent = data.content;
    $("#file-change-dot").classList.remove("is-active");
    setInspectorView("file");
    if (!quiet) renderTree(state.snapshot.files);
  } catch (error) {
    showToast(error.message, true);
  }
}

function setActivityView(view) {
  state.activityView = view;
  $$('[data-view]').forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  if (state.snapshot) {
    const run = state.snapshot.run || {};
    if (view === "conversation") renderConversation(run.messages || []);
    else renderTimeline(run.events || []);
    $("#activity-count").textContent = view === "conversation" ? `${(run.messages || []).length} messages` : `${(run.events || []).length} events`;
  }
}

function setInspectorView(view) {
  state.inspectorView = view;
  $$('[data-inspector]').forEach((button) => {
    const active = button.dataset.inspector === view;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  $("#state-view").classList.toggle("is-hidden", view !== "state");
  $("#file-view").classList.toggle("is-hidden", view !== "file");
  $("#prompt-view").classList.toggle("is-hidden", view !== "prompt");
}

function setSystemPrompt(value, persist = true) {
  state.systemPrompt = value;
  $("#system-prompt-input").value = value;
  $("#system-prompt-count").textContent = `${value.length.toLocaleString("vi-VN")} ký tự`;
  $("#system-prompt-button").classList.toggle("is-custom", value !== state.defaultSystemPrompt);
  if (persist) localStorage.setItem("core-agent-system-prompt", value);
}

function openSystemPromptEditor() {
  setInspectorView("prompt");
  if (window.matchMedia("(max-width: 860px)").matches) {
    $("#explorer-panel").classList.remove("is-open");
    $("#inspector-panel").classList.add("is-open");
    $("#mobile-scrim").classList.add("is-open");
  }
  $("#system-prompt-input").focus();
}

function setScope(scope) {
  if (scope === state.scope) return;
  state.scope = scope;
  state.previousFiles = new Map();
  state.initializedTree = false;
  state.openFolders = new Set([""]);
  $$('[data-scope]').forEach((button) => {
    const active = button.dataset.scope === scope;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  connectStream();
}

async function submitPrompt() {
  const input = $("#prompt-input");
  const prompt = input.value.trim();
  if (!prompt) {
    showToast("Prompt đang trống.", true);
    input.focus();
    return;
  }
  const button = $("#run-button");
  button.disabled = true;
  try {
    const response = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, system_prompt: state.systemPrompt }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Không thể khởi chạy agent");
    state.runId = data.run.run_id;
    input.value = "";
    showToast(`Đã khởi chạy ${compactRunId(state.runId)}`);
    connectStream();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function openMobilePanel(panel) {
  const explorer = $("#explorer-panel");
  const inspector = $("#inspector-panel");
  const target = panel === "explorer" ? explorer : inspector;
  const shouldOpen = !target.classList.contains("is-open");
  explorer.classList.remove("is-open");
  inspector.classList.remove("is-open");
  if (shouldOpen) target.classList.add("is-open");
  $("#mobile-scrim").classList.toggle("is-open", shouldOpen);
}

function closeMobilePanels() {
  $("#explorer-panel").classList.remove("is-open");
  $("#inspector-panel").classList.remove("is-open");
  $("#mobile-scrim").classList.remove("is-open");
}

function bindEvents() {
  $("#run-select").addEventListener("change", (event) => {
    state.runId = event.target.value || null;
    connectStream();
  });
  $("#run-button").addEventListener("click", submitPrompt);
  $("#system-prompt-button").addEventListener("click", openSystemPromptEditor);
  $("#system-prompt-input").addEventListener("input", (event) => setSystemPrompt(event.target.value));
  $("#reset-system-prompt").addEventListener("click", () => {
    setSystemPrompt(state.defaultSystemPrompt);
    showToast("Đã khôi phục system prompt mặc định.");
  });
  $("#load-run-system").addEventListener("click", () => {
    const message = state.snapshot?.run?.messages?.find((item) => item.role === "system");
    if (!message) {
      showToast("Run này không có system prompt.", true);
      return;
    }
    setSystemPrompt(message.content);
    showToast("Đã nạp system prompt từ run đang xem.");
  });
  $("#prompt-input").addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      submitPrompt();
    }
  });
  $$('[data-view]').forEach((button) => button.addEventListener("click", () => setActivityView(button.dataset.view)));
  $$('[data-inspector]').forEach((button) => button.addEventListener("click", () => setInspectorView(button.dataset.inspector)));
  $$('[data-scope]').forEach((button) => button.addEventListener("click", () => setScope(button.dataset.scope)));
  $$('[data-log-filter]').forEach((button) => button.addEventListener("click", () => {
    state.logFilter = button.dataset.logFilter;
    $$('[data-log-filter]').forEach((item) => item.classList.toggle("is-active", item === button));
    if (state.snapshot) renderLogs(state.snapshot.run.events || []);
  }));
  $("#tree-refresh").addEventListener("click", () => refreshSnapshot().catch((error) => showToast(error.message, true)));
  $("#copy-state").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("#state-json").textContent); showToast("Đã sao chép state JSON."); }
    catch { showToast("Không thể sao chép state.", true); }
  });
  $("#log-output").addEventListener("scroll", () => { $("#log-output").dataset.touched = "true"; });
  $("#explorer-toggle").addEventListener("click", () => openMobilePanel("explorer"));
  $("#inspector-toggle").addEventListener("click", () => openMobilePanel("inspector"));
  $("#mobile-scrim").addEventListener("click", closeMobilePanels);
  window.addEventListener("beforeunload", () => state.stream?.close());
}

async function init() {
  bindEvents();
  refreshIcons();
  try {
    const response = await fetch("/api/bootstrap?scope=workspace");
    if (!response.ok) throw new Error("Không thể tải Core Agent UI");
    const snapshot = await response.json();
    state.defaultSystemPrompt = snapshot.default_system_prompt || "";
    const savedSystemPrompt = localStorage.getItem("core-agent-system-prompt");
    setSystemPrompt(savedSystemPrompt === null ? state.defaultSystemPrompt : savedSystemPrompt, false);
    state.runId = snapshot.selected_run_id;
    renderSnapshot(snapshot);
    connectStream();
  } catch (error) {
    setConnection("offline");
    showToast(error.message, true);
  }
}

document.addEventListener("DOMContentLoaded", init);
