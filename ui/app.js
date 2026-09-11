const API_BASE = "/api";

const State = {
  jobId: null,
  filename: null,
  columns: [],
  status: null,
  insights: null,
  activityLog: [],
};

function logActivity(level, message) {
  const entry = { time: new Date(), level, message };
  State.activityLog.unshift(entry);
  if (State.activityLog.length > 200) State.activityLog.pop();
  renderActivityLog();
}

function fmtTime(d) {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON error page */ }
  if (!res.ok) {
    const detail = (body && body.detail) || res.statusText || "Request failed";
    throw new Error(detail);
  }
  return body;
}

function escapeHtml(str) {
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function showToast(message, type = "success") {
  const container = document.getElementById("toastContainer");
  const colors = { success: "border-white/30", error: "border-red-500/50", info: "border-white/20" };
  const el = document.createElement("div");
  el.className = `pointer-events-auto glass-card rounded-xl px-4 py-3 text-xs text-white font-mono border ${colors[type] || colors.info} shadow-lg`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ---------- Navigation ----------
const Nav = {
  set(key) {
    document.querySelectorAll(".view-page").forEach((el) => el.classList.add("hidden"));
    const view = document.getElementById(`view${key.charAt(0).toUpperCase()}${key.slice(1)}`);
    if (view) view.classList.remove("hidden");

    document.querySelectorAll(".sidebar-nav-item").forEach((el) => {
      el.className = "sidebar-nav-item flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-zinc-400 hover:text-white hover:bg-white/5 transition-colors group cursor-pointer";
    });
    const navEl = document.getElementById(`nav${key.charAt(0).toUpperCase()}${key.slice(1)}`);
    if (navEl) navEl.className = "sidebar-nav-item flex items-center gap-3 px-3.5 py-2.5 rounded-xl bg-white/10 text-white border border-white/20 shadow-sm shadow-white/5 group transition-all cursor-pointer";

    if (key === "chatbot") document.getElementById("chatInputField").focus();
    if (key === "graph") Graph.loadFull();
  },
};

// ---------- Theme ----------
const Theme = {
  themes: ["theme-noir", "theme-cyber", "theme-light"],
  icons: ["fa-moon", "fa-bolt", "fa-sun"],
  idx: 0,
  toggle() {
    document.body.classList.remove(...Theme.themes);
    Theme.idx = (Theme.idx + 1) % Theme.themes.length;
    document.body.classList.add(Theme.themes[Theme.idx]);
    document.getElementById("themeIcon").className = `fa-solid ${Theme.icons[Theme.idx]} text-xs text-white`;
  },
};

// ---------- Health ----------
async function pollHealth() {
  try {
    const h = await api("/health");
    const badge = document.getElementById("healthBadge");
    badge.innerHTML = `
      <span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full ${h.kafka_connected ? "bg-white" : "bg-red-500"}"></span>Kafka</span>
      <span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full ${h.neo4j_connected ? "bg-white" : "bg-red-500"}"></span>Neo4j</span>
      <span class="flex items-center gap-1"><span class="w-1.5 h-1.5 rounded-full bg-white"></span>API</span>
    `;
    document.getElementById("pipelineDot").className = `w-1.5 h-1.5 rounded-full ${h.status === "ok" ? "bg-white animate-pulse" : "bg-red-500"}`;

    const detail = document.getElementById("healthDetailBlock");
    detail.innerHTML = [
      ["Kafka Stream", h.kafka_connected],
      ["Neo4j Graph DB", h.neo4j_connected],
    ].map(([label, ok]) => `
      <div class="flex items-center justify-between">
        <span class="flex items-center gap-2"><i class="fa-solid ${ok ? "fa-check text-white" : "fa-xmark text-red-400"} text-[10px]"></i> ${label}</span>
        <span class="${ok ? "text-white" : "text-red-400"} text-[11px] font-medium">${ok ? "Connected" : "Unreachable"}</span>
      </div>`).join("");

    const settingsBlock = document.getElementById("settingsHealthBlock");
    if (settingsBlock) {
      settingsBlock.innerHTML = `
        <div class="flex items-center justify-between"><span class="text-zinc-400">Overall status</span><span class="text-white">${h.status}</span></div>
        <div class="flex items-center justify-between"><span class="text-zinc-400">kafka_connected</span><span class="${h.kafka_connected ? "text-white" : "text-red-400"}">${h.kafka_connected}</span></div>
        <div class="flex items-center justify-between"><span class="text-zinc-400">neo4j_connected</span><span class="${h.neo4j_connected ? "text-white" : "text-red-400"}">${h.neo4j_connected}</span></div>`;
    }
  } catch (err) {
    logActivity("ERROR", `Health check failed: ${err.message}`);
  }
}

// ---------- Upload ----------
function parseClientPreview(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0).slice(0, 6);
  return lines.map((line) => line.split(","));
}

const Upload = {
  file: null,
  onFileSelected(evt) {
    const f = evt.target.files?.[0];
    document.getElementById("uploadError").classList.add("hidden");
    if (!f) return;
    Upload.file = f;
    document.getElementById("uploadFileName").textContent = f.name;
    document.getElementById("uploadPreviewWrap").classList.remove("hidden");

    const reader = new FileReader();
    reader.onload = (e) => {
      const rows = parseClientPreview(String(e.target.result));
      const head = document.getElementById("uploadPreviewHead");
      const body = document.getElementById("uploadPreviewBody");
      head.innerHTML = (rows[0] || []).map((h) => `<th class="py-2 px-3">${escapeHtml(h)}</th>`).join("");
      body.innerHTML = rows.slice(1).map((r) => `<tr>${r.map((c) => `<td class="py-2 px-3">${escapeHtml(c)}</td>`).join("")}</tr>`).join("");
    };
    reader.readAsText(f.slice(0, 20000));
  },
  async start() {
    if (!Upload.file) return;
    const btn = document.getElementById("btnStartIngest");
    btn.disabled = true;
    btn.textContent = "Uploading...";
    try {
      const form = new FormData();
      form.append("file", Upload.file);
      logActivity("INFO", `Uploading ${Upload.file.name} (${Upload.file.size} bytes) to /ingest`);
      const res = await api("/ingest", { method: "POST", body: form });
      State.jobId = res.job_id;
      State.filename = Upload.file.name;
      logActivity("SUCCESS", `Ingest accepted: job_id=${res.job_id}, rows_received=${res.rows_received}`);
      showToast(`Upload accepted: ${res.rows_received} rows queued`, "success");
      document.getElementById("currentDatasetLabel").textContent = Upload.file.name;
      Nav.set("ingestion");
      Ingestion.startPolling();
    } catch (err) {
      document.getElementById("uploadError").textContent = err.message;
      document.getElementById("uploadError").classList.remove("hidden");
      logActivity("ERROR", `Ingest failed: ${err.message}`);
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Start Pipeline";
    }
  },
};

// ---------- Ingestion status ----------
const Ingestion = {
  timer: null,
  startPolling() {
    if (Ingestion.timer) clearInterval(Ingestion.timer);
    document.getElementById("ingestionEmptyState").classList.add("hidden");
    document.getElementById("ingestionDetail").classList.remove("hidden");
    const poll = async () => {
      if (!State.jobId) return;
      try {
        const s = await api(`/status?job_id=${encodeURIComponent(State.jobId)}`);
        State.status = s;
        Ingestion.render(s);
        Dashboard.render();
        if (s.status === "complete") {
          clearInterval(Ingestion.timer);
          logActivity("SUCCESS", `Ingestion complete: ${s.rows_loaded}/${s.rows_total} loaded, ${s.rows_failed} failed`);
          const ins = await api(`/insights?job_id=${encodeURIComponent(State.jobId)}`).catch(() => null);
          State.insights = ins;
          State.columns = (ins && ins.columns) ? ins.columns.map((c) => c.column) : [];
          Dashboard.render();
          Chat.renderSuggestions();
          Graph.loadDashboardPreview();
          Dashboard.loadPreviewTable();
        }
      } catch {
        // dataset not yet visible in Neo4j
      }
    };
    poll();
    Ingestion.timer = setInterval(poll, 1500);
  },
  render(s) {
    document.getElementById("ingestFilename").textContent = s.filename || State.filename || "";
    const pct = s.rows_total > 0 ? Math.min(100, Math.round(((s.rows_loaded + s.rows_failed) / s.rows_total) * 100)) : 0;
    document.getElementById("ingestProgressBar").style.width = `${pct}%`;
    document.getElementById("ingestTotal").textContent = s.rows_total;
    document.getElementById("ingestLoaded").textContent = s.rows_loaded;
    document.getElementById("ingestFailed").textContent = s.rows_failed;
    document.getElementById("ingestPct").textContent = `${pct}%`;
    const badge = document.getElementById("ingestStatusBadge");
    badge.textContent = s.status;
    const colorMap = { complete: "border-white/40 text-white", loading: "border-white/25 text-zinc-200", queued: "border-white/15 text-zinc-400", failed: "border-red-500/50 text-red-400" };
    badge.className = `px-2 py-0.5 rounded-full border text-[10px] uppercase ${colorMap[s.status] || colorMap.queued}`;
  },
};

// ---------- Dashboard ----------
const Dashboard = {
  render() {
    const s = State.status;
    const ins = State.insights;
    document.getElementById("kpiTotalRows").textContent = s ? s.rows_loaded.toLocaleString() : "-";
    document.getElementById("kpiTotalRowsSub").textContent = s ? `of ${s.rows_total.toLocaleString()} total - ${s.rows_failed} failed` : "Upload a CSV to begin";
    document.getElementById("kpiColumns").textContent = State.columns.length || "-";
    document.getElementById("kpiColumnsSub").textContent = State.columns.length ? State.columns.join(", ") : "-";
    document.getElementById("kpiHealth").textContent = ins ? ins.health_score : "-";
    document.getElementById("kpiStatus").textContent = s ? s.status : "-";
    document.getElementById("kpiStatusSub").textContent = s ? `job_id: ${State.jobId}` : "-";

    document.getElementById("tableTitle").textContent = State.filename || "No file uploaded";
    document.getElementById("tableSubtitle").textContent = s ? `${s.rows_total} rows - status: ${s.status}` : "-";
  },
  async loadPreviewTable() {
    if (!State.jobId) return;
    try {
      const graph = await api(`/graph?job_id=${encodeURIComponent(State.jobId)}&limit=10`);
      const rowNodes = graph.nodes.filter((n) => n.type === "Row").sort((a, b) => (a.props.row_index || 0) - (b.props.row_index || 0));
      if (!rowNodes.length) return;
      const cols = State.columns.length ? State.columns : Object.keys(rowNodes[0].props).filter((k) => !["row_key", "row_index", "dataset_id"].includes(k));
      document.getElementById("previewHeadRow").innerHTML = cols.map((c) => `<th class="py-2.5 px-3">${escapeHtml(c)}</th>`).join("");
      document.getElementById("previewBody").innerHTML = rowNodes.map((n) => `
        <tr>${cols.map((c) => `<td class="py-2 px-3">${escapeHtml(n.props[c] ?? "")}</td>`).join("")}</tr>
      `).join("");
    } catch (err) {
      logActivity("ERROR", `Preview table load failed: ${err.message}`);
    }
  },
};

// ---------- Graph ----------
const Graph = {
  data: null,
  async fetchGraph(limit) {
    if (!State.jobId) return null;
    try {
      return await api(`/graph?job_id=${encodeURIComponent(State.jobId)}&limit=${limit}`);
    } catch (err) {
      logActivity("ERROR", `Graph fetch failed: ${err.message}`);
      return null;
    }
  },
  async loadDashboardPreview() {
    const data = await Graph.fetchGraph(24);
    if (data) Graph.render(data, document.getElementById("graphCanvasHost"), 420, 260);
  },
  async loadFull() {
    const data = await Graph.fetchGraph(60);
    const host = document.getElementById("graphFullHost");
    if (data) {
      Graph.render(data, host, 760, 460);
    } else {
      host.innerHTML = `<p class="text-xs font-mono text-zinc-500">No dataset uploaded yet.</p>`;
    }
  },
  render(data, host, w, h) {
    Graph.data = data;
    const rowNodes = data.nodes.filter((n) => n.type === "Row");
    const datasetNode = data.nodes.find((n) => n.type === "Dataset");
    const cx = w / 2, cy = h / 2;
    const radius = Math.min(w, h) / 2 - 40;
    const positioned = rowNodes.map((n, i) => {
      const angle = (2 * Math.PI * i) / Math.max(rowNodes.length, 1);
      return { ...n, x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
    });

    const lines = positioned.map((n) => `<line x1="${cx}" y1="${cy}" x2="${n.x}" y2="${n.y}" stroke="#71717a" stroke-width="1" opacity="0.5"/>`).join("");
    const circles = positioned.map((n) => `
      <g class="cursor-pointer" onclick='Graph.inspect(${JSON.stringify(n.id)})'>
        <circle cx="${n.x}" cy="${n.y}" r="9" fill="#181a20" stroke="#a1a1aa" stroke-width="1.6" class="hover:stroke-white transition-colors"/>
      </g>`).join("");

    host.innerHTML = `
      <svg width="100%" height="100%" viewBox="0 0 ${w} ${h}">
        ${lines}
        ${circles}
        <circle cx="${cx}" cy="${cy}" r="18" fill="#ffffff" stroke="#7c2d12" stroke-width="0"/>
        <text x="${cx}" y="${cy + 4}" text-anchor="middle" font-size="9" font-weight="700" fill="#000">DS</text>
      </svg>
      <p class="absolute bottom-2 left-3 text-[10px] font-mono text-zinc-500">${datasetNode ? datasetNode.label : ""} - ${rowNodes.length} rows shown</p>
    `;
  },
  inspect(nodeId) {
    if (!Graph.data) return;
    const node = Graph.data.nodes.find((n) => n.id === nodeId);
    if (!node) return;
    document.getElementById("inspectNodeTitle").textContent = node.label || node.id;
    document.getElementById("inspectNodeBody").textContent = JSON.stringify(node.props || node, null, 2);
    document.getElementById("nodeInspectModal").classList.remove("hidden");
  },
  closeInspect() {
    document.getElementById("nodeInspectModal").classList.add("hidden");
  },
};

// ---------- Chat ----------
const Chat = {
  async submit(evt) {
    evt.preventDefault();
    const input = document.getElementById("chatInputField");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    Chat.appendUser(text);
    logActivity("QUERY", `Chat question: "${text}"`);
    try {
      const res = await api("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text, job_id: State.jobId || undefined }),
      });
      Chat.appendBot(res);
      logActivity(res.grounded ? "SUCCESS" : "INFO", `Chat answer (grounded=${res.grounded}): ${res.answer}`);
    } catch (err) {
      Chat.appendBot({ answer: err.message, cypher: "", result: [], grounded: false });
      logActivity("ERROR", `Chat failed: ${err.message}`);
    }
  },
  sendQuick(text) {
    document.getElementById("chatInputField").value = text;
    Chat.submit({ preventDefault() {} });
  },
  appendUser(text) {
    const stream = document.getElementById("chatMessageStream");
    stream.insertAdjacentHTML("beforeend", `
      <div class="flex flex-col items-end">
        <div class="bg-gradient-to-b from-white to-zinc-200 text-black text-xs px-3.5 py-2.5 rounded-2xl rounded-tr-sm max-w-[85%] shadow-md font-medium leading-relaxed">${escapeHtml(text)}</div>
        <span class="text-[9px] font-mono text-zinc-500 mt-1 mr-1">${fmtTime(new Date())}</span>
      </div>`);
    stream.scrollTop = stream.scrollHeight;
  },
  appendBot(res) {
    const stream = document.getElementById("chatMessageStream");
    const groundedBadge = res.grounded
      ? `<span class="flex items-center gap-1 text-[10px] font-mono grounded-true bg-white/5 px-2 py-0.5 rounded border border-white/15 font-medium"><i class="fa-solid fa-shield-check text-[10px]"></i> Grounded in Neo4j</span>`
      : `<span class="flex items-center gap-1 text-[10px] font-mono grounded-false bg-red-500/5 px-2 py-0.5 rounded border border-red-500/20 font-medium"><i class="fa-solid fa-circle-xmark text-[10px]"></i> Not grounded</span>`;
    const cypherBlock = res.cypher ? `
      <div class="rounded-lg bg-noir-950 border border-white/10 p-2.5 font-mono text-[11px] mt-2">
        <div class="flex items-center justify-between text-[10px] text-zinc-500 mb-1 border-b border-white/10 pb-1"><span>Cypher Query</span></div>
        <code class="text-white block whitespace-pre-wrap">${escapeHtml(res.cypher)}</code>
      </div>
      <div class="rounded-lg bg-noir-950/70 p-2 font-mono text-[10px] text-zinc-400 border border-white/5 mt-2">
        <span class="text-zinc-500">Raw Result:</span> <span class="text-white font-medium">${escapeHtml(JSON.stringify(res.result))}</span>
      </div>` : "";
    stream.insertAdjacentHTML("beforeend", `
      <div class="flex flex-col items-start gap-1 max-w-[95%]">
        <div class="flex items-center gap-1.5 mb-1">
          <div class="w-5 h-5 rounded-full bg-white/10 flex items-center justify-center text-white text-[10px] border border-white/20"><i class="fa-solid fa-robot"></i></div>
          <span class="text-[10px] font-mono font-semibold text-zinc-300">DataFlow Copilot</span>
        </div>
        <div class="bg-noir-850 border border-white/10 rounded-2xl rounded-tl-sm p-3 text-xs text-zinc-200 space-y-1 w-full">
          <p class="leading-relaxed">${escapeHtml(res.answer)}</p>
          ${cypherBlock}
          <div class="flex items-center justify-between pt-1">${groundedBadge}</div>
        </div>
      </div>`);
    stream.scrollTop = stream.scrollHeight;
  },
  clear() {
    document.getElementById("chatMessageStream").innerHTML = "";
    logActivity("INFO", "Chat history cleared (client-side only)");
  },
  renderSuggestions() {
    const pills = document.getElementById("suggestionPills");
    const suggestions = (State.insights && State.insights.suggested_questions) || [];
    pills.innerHTML = suggestions.map((s) => `
      <button class="px-2 py-1 rounded bg-white/5 hover:bg-white/10 text-zinc-300 whitespace-nowrap border border-white/10 transition-colors" onclick='Chat.sendQuick(${JSON.stringify(s)})'>${escapeHtml(s)}</button>
    `).join("");
  },
};

// ---------- Activity log ----------
function renderActivityLog() {
  const levelColor = { INFO: "text-white", SUCCESS: "text-white", ERROR: "text-red-400", QUERY: "text-zinc-300" };
  const rows = State.activityLog.map((e) => `
    <p><span class="text-zinc-500">[${fmtTime(e.time)}]</span> <span class="${levelColor[e.level] || "text-white"} font-bold">[${e.level}]</span> ${escapeHtml(e.message)}</p>
  `).join("");
  const full = document.getElementById("fullActivityLog");
  if (full) full.innerHTML = rows || `<p class="text-zinc-500">No activity yet.</p>`;
  const mini = document.getElementById("recentActivityMini");
  if (mini) {
    mini.innerHTML = State.activityLog.slice(0, 4).map((e) => `
      <div class="flex items-center justify-between">
        <span class="truncate flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full ${e.level === "ERROR" ? "bg-red-500" : "bg-white"}"></span> ${escapeHtml(e.message)}</span>
        <span class="text-zinc-500 text-[10px]">${fmtTime(e.time)}</span>
      </div>`).join("") || `<p class="text-zinc-500">No activity yet.</p>`;
  }
}

// ---------- Boot ----------
document.addEventListener("DOMContentLoaded", () => {
  document.body.classList.add("theme-noir");
  Nav.set("dashboard");
  logActivity("INFO", "DataFlowAI UI loaded");
  pollHealth();
  setInterval(pollHealth, 8000);
});
