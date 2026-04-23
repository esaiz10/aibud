const overviewEl = document.getElementById("overview");
const projectsEl = document.getElementById("projects");
const tasksEl = document.getElementById("tasks");
const memoriesEl = document.getElementById("memories");
const reportsEl = document.getElementById("reports");
const runsEl = document.getElementById("runs");
const eventsEl = document.getElementById("events");
const responseEl = document.getElementById("response");
const askForm = document.getElementById("ask-form");
const refreshButton = document.getElementById("refresh-button");
const latestStatusEl = document.getElementById("latest-status");

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function renderList(target, items, renderItem) {
  if (!items.length) {
    target.innerHTML = `<div class="card"><small>Nothing here yet.</small></div>`;
    return;
  }
  target.innerHTML = items.map(renderItem).join("");
}

function safe(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return safe(value);
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function pill(text, className = "subtle") {
  return `<span class="pill ${className}">${safe(text)}</span>`;
}

function summarizePayload(payload) {
  const text = JSON.stringify(payload || {});
  return text.length > 180 ? `${text.slice(0, 180)}...` : text;
}

async function refresh() {
  const [overview, projects, tasks, memories, reports, runs, events] = await Promise.all([
    getJson("/api/overview"),
    getJson("/api/projects"),
    getJson("/api/tasks"),
    getJson("/api/memories"),
    getJson("/api/reports"),
    getJson("/api/runs"),
    getJson("/api/events"),
  ]);

  overviewEl.innerHTML = Object.entries(overview.overview)
    .map(([label, value]) => `
      <div class="stat">
        <strong>${safe(label)}</strong>
        <div class="stat-value">${safe(value)}</div>
      </div>
    `)
    .join("");

  renderList(projectsEl, projects.projects, (item) => `
    <div class="card">
      <div class="card-header">
        <strong>${safe(item.name)}</strong>
        ${pill(item.status, `status-${safe(item.status)}`)}
      </div>
      <div class="card-meta">
        ${pill(`Priority ${item.priority}`)}
      </div>
      <div class="card-body muted">${safe(item.description || "No project description.")}</div>
    </div>
  `);

  renderList(tasksEl, tasks.tasks, (item) => `
    <div class="card">
      <div class="card-header">
        <strong>${safe(item.title)}</strong>
        ${pill(item.status, `status-${safe(item.status)}`)}
      </div>
      <div class="card-meta">
        ${pill(item.project_name)}
        ${pill(`Priority ${item.priority}`)}
      </div>
      <div class="card-body muted">${safe(item.details || "No task details.")}</div>
    </div>
  `);

  renderList(memoriesEl, memories.memories, (item) => `
    <div class="card">
      <div class="card-header">
        <strong>${safe(item.title)}</strong>
        ${pill(item.kind)}
      </div>
      <div class="card-meta">
        <small>${safe(formatDate(item.created_at))}</small>
      </div>
      <div class="card-body muted">${safe(item.content).slice(0, 240)}</div>
    </div>
  `);

  renderList(reportsEl, reports.reports, (item) => `
    <div class="card">
      <div class="card-header">
        <strong>${safe(item.title)}</strong>
        ${pill("Report")}
      </div>
      <div class="card-meta">
        <small>${safe(formatDate(item.created_at))}</small>
      </div>
      <div class="card-body muted">${safe(item.body).slice(0, 300)}</div>
    </div>
  `);

  renderList(runsEl, runs.runs, (item) => `
    <div class="card">
      <div class="card-header">
        <strong>${safe(item.project_name)}</strong>
        ${pill(item.status, `status-${safe(item.status)}`)}
      </div>
      <div class="card-meta">
        ${pill(`Mode ${item.mode || "normal"}`)}
      </div>
      <div class="card-body">${safe(item.prompt)}</div>
      <div class="card-meta">
        <small>${safe(formatDate(item.updated_at || item.created_at))}</small>
      </div>
      <div class="card-body muted">${safe(item.summary || "No reasoning summary recorded.")}</div>
    </div>
  `);

  renderList(eventsEl, events.events, (item) => `
    <div class="card ${item.kind === "error" ? "error-card" : ""}">
      <div class="card-header">
        <strong>${safe(item.message)}</strong>
        ${pill(item.kind, `kind-${safe(item.kind)}`)}
      </div>
      <div class="trace-meta">
        <small>${safe(formatDate(item.created_at))}</small>
      </div>
      <div class="mono">${safe(summarizePayload(item.payload))}</div>
    </div>
  `);

  const latestRun = runs.runs[0];
  if (latestRun) {
    latestStatusEl.className = `pill status-${latestRun.status}`;
    latestStatusEl.textContent = latestRun.status;
    if (!responseEl.dataset.manual) {
      responseEl.classList.remove("empty");
      responseEl.textContent = `${latestRun.summary || "No summary."}\n\n${latestRun.response || latestRun.prompt}`;
    }
  }
}

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitBtn = askForm.querySelector("button[type=submit]");
  const project = document.getElementById("project").value;
  const mode = document.getElementById("mode").value;
  const prompt = document.getElementById("prompt").value;
  latestStatusEl.className = "pill status-running";
  latestStatusEl.textContent = "running";
  responseEl.dataset.manual = "true";
  responseEl.classList.remove("empty");
  responseEl.textContent = "Running...";
  submitBtn.disabled = true;

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project, prompt, mode }),
    });
    const payload = await response.json();
    latestStatusEl.className = `pill status-${payload.run?.status || (payload.ok ? "completed" : "failed")}`;
    latestStatusEl.textContent = payload.run?.status || (payload.ok ? "completed" : "failed");
    responseEl.textContent = `Mode: ${payload.mode || mode}\nCache hit: ${payload.cache_hit ? "yes" : "no"}\n\n${payload.summary || "Request failed."}\n\n${payload.response || payload.error || "Unknown error."}`;
    if (payload.ok) {
      document.getElementById("prompt").value = "";
    }
    await refresh();
  } catch (err) {
    latestStatusEl.className = "pill status-failed";
    latestStatusEl.textContent = "failed";
    responseEl.textContent = `Network error: ${err.message}`;
  } finally {
    submitBtn.disabled = false;
  }
});

refreshButton.addEventListener("click", refresh);
refresh();
setInterval(refresh, 10000);
