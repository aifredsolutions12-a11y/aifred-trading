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
  const [signals, stats, journal, health, positions] = await Promise.all([
    fetchJson("latest_signals.json", []),
    fetchJson("stats.json", {}),
    fetchJson("journal.json", []),
    fetchJson("api_health.json", { providers: {} }),
    fetchJson("position_status.json", []),    // ← NEW
  ]);
  renderSignals(signals);
  renderStats(stats);
  renderJournal(journal);
  renderHealth(health);
  renderPositions(positions);                  // ← NEW
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

function fmtAge(iso) {
  if (!iso) return "—";
  const opened = new Date(iso);
  const mins = Math.floor((Date.now() - opened) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return mins + "m";
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + "h " + (mins % 60) + "m";
  const days = Math.floor(hrs / 24);
  return days + "d " + (hrs % 24) + "h";
}

function renderPositions(rows) {
  const grid = $("#positions-grid");
  if (!grid) return; // Tab doesn't exist yet in HTML

  grid.innerHTML = "";
  if (!rows.length) {
    grid.innerHTML = "<p style='color:var(--muted);'>No open positions right now.</p>";
    return;
  }

  // Sort by most recently opened
  rows.sort((a, b) => (b.logged_at || "").localeCompare(a.logged_at || ""));

  for (const p of rows) {
    const pos = p.position || "WAIT";
    const entry = p.entry_zone || {};
    const refreshCount = p._refresh_count ?? p.refresh_count ?? 0;
    const origConf = p.original_confluence ?? p.confluence_score ?? "—";
    const latestConf = p._latest_confluence ?? p.latest_confluence ?? origConf;
    const latestConfidence = p._latest_confidence ?? p.latest_confidence ?? p.confidence ?? "—";
    const latestEvR = p._latest_ev_R ?? p.latest_ev_R ?? p.ev_R ?? null;
    const lastRefresh = p._last_refresh_at ?? p.last_refresh_at ?? null;

    const evolved = origConf !== "—" && latestConf !== "—" &&
                   Math.abs(parseFloat(latestConf) - parseFloat(origConf)) > 0.5;

    const evolutionHTML = evolved
      ? `<div style="margin-top:8px; padding:8px; background:var(--bg); border-left:3px solid #58a6ff; border-radius:4px; font-size:0.85em;">
           📊 Confluence: ${parseFloat(origConf).toFixed(1)} → <b>${parseFloat(latestConf).toFixed(1)}</b>
           &nbsp;·&nbsp; Now: <b>${latestConfidence}</b>
         </div>`
      : "";

    const refreshBadgeHTML = refreshCount > 0
      ? `<span style="display:inline-block; padding:2px 8px; border-radius:10px; background:#1f6feb; color:white; font-size:0.75em; margin-left:8px;">🔁 ${refreshCount}×</span>`
      : "";

    grid.innerHTML += `
      <div class="card">
        <h3>
          <span>${p.symbol || "?"} ${refreshBadgeHTML}</span>
          <span class="badge ${pos}">${pos}</span>
        </h3>
        <div class="meta">Opened: ${p.logged_at ? new Date(p.logged_at).toLocaleString() : "—"}</div>
        <div>Entry: ${entry.low?.toFixed?.(4) ?? "—"} – ${entry.high?.toFixed?.(4) ?? "—"}</div>
        <div>SL: ${p.stop_loss?.toFixed?.(4) ?? "—"} | TP1: ${p.take_profit_1?.toFixed?.(4) ?? "—"}</div>
        <div>Latest EV: <b>${latestEvR != null ? parseFloat(latestEvR).toFixed(2) + "R" : "—"}</b></div>
        <div class="meta" style="margin-top:6px;">
          ⏱️ Active for ${fmtAge(p.logged_at)}
          ${lastRefresh ? ` · Last refresh ${fmtAge(lastRefresh)} ago` : ""}
        </div>
        ${evolutionHTML}
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

