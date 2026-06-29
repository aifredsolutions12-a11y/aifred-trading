const BASE = "data/";
const $ = (s) => document.querySelector(s);

async function fetchJson(name, fallback) {
  try {
    const r = await fetch(BASE + name, { cache: "no-store" });
    if (!r.ok) return fallback;
    return await r.json();
  } catch { return fallback; }
}

async function loadAll() {
  const [signals, stats, journal, health] = await Promise.all([
    fetchJson("latest_signals.json", []),
    fetchJson("stats.json", {}),
    fetchJson("journal.json", []),
    fetchJson("api_health.json", { providers: {} }),
  ]);
  renderSignals(signals);
  renderStats(stats);
  renderJournal(journal);
  renderHealth(health);
  $("#updated").textContent = "Updated " + new Date().toLocaleString();
}

function renderSignals(rows) {
  const grid = $("#signals-grid");
  grid.innerHTML = "";
  if (!rows.length) {
    grid.innerHTML = "<p style='color:var(--muted);'>No signals yet — waiting for the first agent run.</p>";
    return;
  }
  rows.sort((a, b) => (b.logged_at || "").localeCompare(a.logged_at || ""));
  for (const r of rows) {
    const pos = r.position || "WAIT";
    const entry = r.entry_zone || {};
    const score = r.confluence_score ?? "—";
    const outcomeCls = r.outcome === "TP1" ? "tp" : r.outcome === "SL" ? "sl" : "";
    grid.innerHTML += `
      <div class="card">
        <h3>
          <span>${r.symbol || "?"} <small style="color:var(--muted)">${r.timeframe || ""}</small></span>
          <span class="badge ${pos}">${pos}</span>
        </h3>
        <div class="meta">${r.logged_at ? new Date(r.logged_at).toLocaleString() : ""}</div>
        <div>Confidence: <b>${r.confidence || "—"}</b></div>
        <div>Confluence: <b>${score}</b></div>
        <div>Entry: ${entry.low?.toFixed?.(4) ?? "—"} – ${entry.high?.toFixed?.(4) ?? "—"}</div>
        <div>SL: ${r.stop_loss?.toFixed?.(4) ?? "—"} | TP1: ${r.take_profit_1?.toFixed?.(4) ?? "—"}</div>
        <div>Outcome: <b class="${outcomeCls}">${r.outcome || "open"}</b>
          ${r.pnl_pct != null ? ` (${r.pnl_pct}%)` : ""}
        </div>
      </div>`;
  }
}

function renderStats(s) {
  $("#kpi-trades").textContent = s.trades ?? 0;
  $("#kpi-wr").textContent     = (s.win_rate ?? 0) + "%";
  $("#kpi-pnl").textContent    = (s.avg_pnl_pct ?? 0) + "%";

  const m = s.by_method || {};
  const labels = Object.keys(m);
  const data   = labels.map(k => m[k].win_rate);

  if (window._mc) window._mc.destroy();
  if (!labels.length) return;

  window._mc = new Chart($("#methodChart"), {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Win Rate %",
        data,
        backgroundColor: "#58a6ff",
        borderColor: "#58a6ff",
        borderWidth: 1,
      }]
    },
    options: {
      scales: {
        y: { beginAtZero: true, max: 100, ticks: { color: "#c9d1d9" }, grid: { color: "#30363d" } },
        x: { ticks: { color: "#c9d1d9" }, grid: { color: "#30363d" } }
      },
      plugins: { legend: { display: false } }
    }
  });
}

function renderJournal(rows) {
  const tbody = $("#journal-table tbody");
  tbody.innerHTML = "";
  rows.slice().reverse().forEach(r => {
    const cls = r.outcome === "TP1" ? "tp" : r.outcome === "SL" ? "sl" : "";
    tbody.innerHTML += `<tr>
      <td>${r.logged_at ? new Date(r.logged_at).toLocaleString() : "—"}</td>
      <td>${r.symbol || "—"}</td>
      <td>${r.timeframe || "—"}</td>
      <td><span class="badge ${r.position || 'WAIT'}">${r.position || "—"}</span></td>
      <td>${r.confidence || "—"}</td>
      <td>${r.confluence_score ?? "—"}</td>
      <td class="${cls}">${r.outcome || "open"}</td>
      <td>${r.pnl_pct ?? "—"}</td>
    </tr>`;
  });
}

function renderHealth(h) {
  const grid = $("#health-grid");
  grid.innerHTML = "";
  const providers = h.providers || {};
  if (!Object.keys(providers).length) {
    grid.innerHTML = "<p style='color:var(--muted);'>No API calls tracked yet.</p>";
    return;
  }
  for (const [name, p] of Object.entries(providers)) {
    grid.innerHTML += `<div class="card">
      <h3><span>${name}</span> <span class="health-status">${p.status || "—"}</span></h3>
      <div>Calls: <b>${p.calls}</b></div>
      <div>Errors: <b>${p.errors}</b> (${p.error_rate_pct}%)</div>
      <div>Avg latency: <b>${p.avg_latency_ms} ms</b></div>
      <div class="meta">Last error: ${p.last_error || "none"}</div>
    </div>`;
  }
}

// Tab switching
document.querySelectorAll(".tab").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll(".tab, main > section").forEach(x => x.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  };
});

loadAll();
