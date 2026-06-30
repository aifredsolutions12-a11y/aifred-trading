const SIGNAL_INDEX = "data/signals_index.json";
const POSITION_INDEX = "data/position_status.json";
const POSTMORTEM_INDEX = "data/postmortems_index.json";
const WEIGHTS_INDEX = "data/weights_index.json";
const STATS_EXTENDED = "data/stats_extended.json";

// Tab switching
document.querySelectorAll(".tab").forEach(t => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(x => x.style.display = "none");
    t.classList.add("active");
    document.getElementById("tab-" + t.dataset.tab).style.display = "block";
  });
});

// ════════════════════════════════════════════════════════════
// Formatters
// ════════════════════════════════════════════════════════════
function fmtPrice(v) {
  if (v == null || isNaN(v)) return "—";
  if (Math.abs(v) >= 1000) return "$" + v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (Math.abs(v) >= 1) return "$" + v.toFixed(4);
  if (Math.abs(v) >= 0.01) return "$" + v.toFixed(6);
  return "$" + v.toFixed(8);
}

function fmtAge(iso) {
  if (!iso) return "unknown";
  const opened = new Date(iso);
  const now = new Date();
  const mins = Math.floor((now - opened) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ${mins % 60}m`;
  const days = Math.floor(hrs / 24);
  return `${days}d ${hrs % 24}h`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

// v3 NEW: Tier badge based on symbol
function tierBadge(symbol) {
  const t1 = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
  const t3 = ["ZECUSDT"];
  if (t1.includes(symbol)) return '<span class="badge-tier-1">T1</span>';
  if (t3.includes(symbol)) return '<span class="badge-tier-3">T3</span>';
  return '<span class="badge-tier-2">T2</span>';
}

// v3 NEW: Time progress color logic
function timeProgressClass(pct) {
  if (pct == null) return "safe";
  if (pct >= 80) return "danger";
  if (pct >= 50) return "warning";
  return "safe";
}

// ════════════════════════════════════════════════════════════
// Render signals
// ════════════════════════════════════════════════════════════
function renderSignal(s) {
  const tfTrail = (s.tf_aggregate?.tf_trail || [])
    .map(t => {
      const pct = Math.max(0, Math.min(100, t.score));
      const color = pct >= 65 ? "#56d364" : pct <= 35 ? "#f85149" : "#d29922";
      return `
        <div class="tf-row">
          <span class="tf-name">${t.tf}</span>
          <div class="tf-bar"><div class="tf-bar-fill" style="width:${pct}%;background:${color};"></div></div>
          <span class="tf-score">${t.score.toFixed(0)}</span>
          <span class="tf-weight">(${(t.weight*100).toFixed(0)}%)</span>
        </div>`;
    }).join("");

  const atrBadge = s.atr_pct
    ? `<span class="badge-atr">ATR ${s.atr_pct.toFixed(2)}%</span>`
    : "";

  return `
    <div class="card">
      <div class="card-head">
        <span class="card-symbol">
          ${s.symbol}${tierBadge(s.symbol)}${atrBadge}
        </span>
        <span class="pos pos-${s.position}">${s.position}</span>
      </div>
      <div class="stats">
        <div class="stat"><span class="stat-label">Confidence</span><span class="stat-val conf-${s.confidence}">${s.confidence}</span></div>
        <div class="stat"><span class="stat-label">Confluence</span><span class="stat-val">${(s.final_confluence||0).toFixed(1)}%</span></div>
        <div class="stat"><span class="stat-label">EV (R)</span><span class="stat-val">${(s.ev_R||0).toFixed(2)}R</span></div>
        <div class="stat"><span class="stat-label">Win Prob</span><span class="stat-val">${s.estimated_win_prob_pct||0}%</span></div>
        <div class="stat"><span class="stat-label">Price</span><span class="stat-val">${fmtPrice(s.current_price)}</span></div>
        <div class="stat"><span class="stat-label">Max Hold</span><span class="stat-val">${s.max_hold_hours ? s.max_hold_hours + 'h' : '—'}</span></div>
      </div>
      ${renderSLTPCompare(s)}
      <div class="tf-trail">
        <div style="font-size:0.85em; color:#8b949e; margin-bottom:6px;">TF Scoring Trail</div>
        ${tfTrail || '<div style="color:#6e7681; font-size:0.85em;">no data</div>'}
      </div>
      ${s.final_narrative ? `<div class="narrative">${s.final_narrative}</div>` : ""}
      ${s.memory_reflection ? `<div class="memory-reflection"><strong>💭 Memory:</strong> ${s.memory_reflection}</div>` : ""}
    </div>
  `;
}

// v3 NEW: 3-layer SL/TP comparison renderer
function renderSLTPCompare(p) {
  if (!p.stop_loss_effective && !p.stop_loss) return "";

  const ai_sl = p.stop_loss_ai ?? p.stop_loss;
  const atr_sl = p.stop_loss_atr;
  const eff_sl = p.stop_loss_effective ?? p.stop_loss;
  const ai_tp = p.take_profit_ai ?? p.take_profit_1;
  const atr_tp = p.take_profit_atr;
  const eff_tp = p.take_profit_effective ?? p.take_profit_1;
  const be = p.be_trigger_price;

  const atrRow = (atr_sl != null && atr_tp != null) ? `
      <div class="sltp-compare-row">
        <span class="stat-label">ATR side</span>
        <span class="sl-text">${fmtPrice(atr_sl)}</span>
        <span class="tp-text">${fmtPrice(atr_tp)}</span>
      </div>` : "";

  const beRow = be != null ? `
      <div class="sltp-compare-row">
        <span class="stat-label">BE trig.</span>
        <span class="be-text" colspan="2">${fmtPrice(be)} ${p.be_activated ? "🟦 ARMED" : ""}</span>
        <span></span>
      </div>` : "";

  return `
    <div class="sltp-compare">
      <div class="sltp-compare-row sltp-compare-header">
        <span>Layer</span><span>SL</span><span>TP</span>
      </div>
      <div class="sltp-compare-row">
        <span class="stat-label">AI side</span>
        <span class="sl-text">${fmtPrice(ai_sl)}</span>
        <span class="tp-text">${fmtPrice(ai_tp)}</span>
      </div>
      ${atrRow}
      <div class="sltp-compare-row sltp-effective">
        <span>⚡ Effective</span>
        <span class="sl-text">${fmtPrice(eff_sl)}</span>
        <span class="tp-text">${fmtPrice(eff_tp)}</span>
      </div>
      ${beRow}
    </div>
  `;
}

// ════════════════════════════════════════════════════════════
// Render position card (v3 enhanced)
// ════════════════════════════════════════════════════════════
function renderPosition(p) {
  const origConf = p.original_confluence || 0;
  const latestConf = p.latest_confluence || origConf;
  const hasEvolved = Math.abs(latestConf - origConf) > 0.5;
  const evolution = hasEvolved
    ? `<div class="pos-evolution">
         📊 Confluence evolved: ${origConf.toFixed(1)} → 
         <strong>${latestConf.toFixed(1)}</strong>
         (latest conviction: <span class="conf-${p.latest_confidence}">${p.latest_confidence}</span>)
       </div>`
    : "";

  const refreshBadge = p.refresh_count > 0
    ? `<span class="pos-refresh-badge">🔁 ${p.refresh_count} refresh${p.refresh_count > 1 ? 'es' : ''}</span>`
    : "";

  const beBadge = p.be_activated
    ? `<span class="badge-be">🟦 BE ARMED</span>`
    : "";

  const lastRefreshTxt = p.last_refresh_at
    ? `Last refresh: ${fmtAge(p.last_refresh_at)} ago`
    : "Not yet refreshed";

  // v3 NEW: Time progress bar
  const tpClass = timeProgressClass(p.time_progress_pct);
  const timeBar = p.time_progress_pct != null ? `
    <div class="time-progress">
      <div class="time-progress-label">
        <span>⏱️ Time in trade</span>
        <span>${p.age_hours}h / ${p.max_hold_hours}h
          ${p.hours_remaining != null ? `· ${p.hours_remaining}h left` : ''}</span>
      </div>
      <div class="time-progress-bar">
        <div class="time-progress-fill ${tpClass}" style="width:${p.time_progress_pct}%"></div>
      </div>
    </div>` : "";

  // ATR badge
  const atrBadge = p.atr_pct != null
    ? `<span class="badge-atr">ATR ${p.atr_pct.toFixed(2)}%</span>`
    : "";

  return `
    <div class="pos-card">
      <div class="pos-card-head">
        <div>
          <strong style="font-size:1.1em;">${p.symbol}</strong>${tierBadge(p.symbol)}
          <span class="pos pos-${p.position}">${p.position}</span>
          ${refreshBadge}
          ${beBadge}
          ${atrBadge}
        </div>
        <div style="color:#8b949e; font-size:0.85em;">
          Opened: ${fmtTime(p.logged_at)}
        </div>
      </div>
      <div class="pos-meta">
        <div class="pos-stat">
          <div class="pos-stat-label">ENTRY ZONE</div>
          <div class="pos-stat-val">${fmtPrice(p.entry_zone?.low)} – ${fmtPrice(p.entry_zone?.high)}</div>
        </div>
        <div class="pos-stat">
          <div class="pos-stat-label">LATEST EV (R)</div>
          <div class="pos-stat-val">${(p.latest_ev_R || 0).toFixed(2)}R</div>
        </div>
        <div class="pos-stat">
          <div class="pos-stat-label">CONFIDENCE</div>
          <div class="pos-stat-val conf-${p.latest_confidence || p.confidence}">${p.latest_confidence || p.confidence || "—"}</div>
        </div>
        <div class="pos-stat">
          <div class="pos-stat-label">MAX HOLD</div>
          <div class="pos-stat-val">${p.max_hold_hours ? p.max_hold_hours + 'h' : '—'}</div>
        </div>
      </div>

      ${renderSLTPCompare(p)}
      ${timeBar}

      <div class="pos-age">
        ⏱️ Active for ${fmtAge(p.logged_at)} · ${lastRefreshTxt}
      </div>
      ${evolution}
    </div>
  `;
}

// ════════════════════════════════════════════════════════════
// Render post-mortems (unchanged)
// ════════════════════════════════════════════════════════════
function renderPostmortem(pm) {
  return `
    <div class="pm-card">
      <div class="pm-head">
        <strong>${pm.coin}</strong>
        <span style="color:#8b949e; font-size:0.85em;">
          ${pm.date} · ${pm.wins||0}W / ${pm.losses||0}L of ${pm.trades_reviewed||0}
        </span>
      </div>
      <div class="pm-lesson">"${pm.lesson || '—'}"</div>
      ${pm.adjustment ? `<div class="pm-adjustment"><strong>Adjustment:</strong> ${pm.adjustment}</div>` : ""}
      ${pm.methodology_flag ? `<div style="margin-top:6px; font-size:0.85em; color:#d29922;">⚙️ ${pm.methodology_flag}</div>` : ""}
    </div>
  `;
}

// ════════════════════════════════════════════════════════════
// Render adaptive weights (unchanged)
// ════════════════════════════════════════════════════════════
function renderWeights(w) {
  const weights = w.weights || {};
  const bars = Object.entries(weights)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => {
      const pct = v * 100;
      return `
        <div class="tf-row">
          <span class="tf-name" style="width:90px;">${k}</span>
          <div class="tf-bar"><div class="tf-bar-fill" style="width:${pct*3}%;background:#58a6ff;"></div></div>
          <span class="tf-score">${pct.toFixed(1)}%</span>
        </div>`;
    }).join("");
  return `
    <div class="pm-card">
      <div class="pm-head">
        <strong>${w.coin}</strong>
        <span style="color:#8b949e; font-size:0.85em;">Adaptive Weights</span>
      </div>
      ${bars}
    </div>
  `;
}

// ════════════════════════════════════════════════════════════
// v3 NEW: Render extended stats
// ════════════════════════════════════════════════════════════
function renderStats(s) {
  if (!s) return '<div class="empty">No stats data yet.</div>';

  const outcomeRows = Object.entries(s.outcome_distribution || {})
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => {
      const icon = {
        "TP_HIT": "✅", "TP1": "✅",
        "SL": "🛑", "BE_STOP": "🟦",
        "TIME_WIN": "⏰✅", "TIME_LOSS": "⏰🛑", "TIME_FLAT": "⏰⚪",
        "NO_FILL": "⊘", "EXPIRED": "⌛", "INVALID": "⚠️",
        "NO_TRADE": "—", "FLIPPED": "🔄",
      }[k] || "?";
      return `<div class="stats-row"><span>${icon} ${k}</span><strong>${v}</strong></div>`;
    }).join("");

  const classRows = Object.entries(s.class_distribution || {})
    .map(([k, v]) => `<div class="stats-row"><span>${k}</span><strong>${v}</strong></div>`)
    .join("");

  const pnlRows = Object.entries(s.avg_pnl_by_class || {})
    .map(([k, v]) => {
      const color = v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--muted)";
      return `<div class="stats-row"><span>${k}</span><strong style="color:${color}">${v > 0 ? '+' : ''}${v}%</strong></div>`;
    }).join("");

  return `
    <div class="stats-grid">
      <div class="stats-card">
        <h3>📊 Outcome Distribution</h3>
        ${outcomeRows || '<div style="color:#6e7681;">No closed trades yet</div>'}
      </div>
      <div class="stats-card">
        <h3>🏷️ Class Distribution</h3>
        ${classRows || '<div style="color:#6e7681;">No data</div>'}
      </div>
      <div class="stats-card">
        <h3>💰 Avg P&L by Class</h3>
        ${pnlRows || '<div style="color:#6e7681;">No P&L data yet</div>'}
      </div>
      <div class="stats-card">
        <h3>🟦 BE Activation Rate</h3>
        <div class="stats-kpi">${s.be_activation_rate_pct || 0}%</div>
        <div class="stats-row" style="border:none">
          <span>BE armed:</span><strong>${s.be_activated_count || 0}</strong>
        </div>
        <div class="stats-row" style="border:none">
          <span>Closed total:</span><strong>${s.closed_trades_total || 0}</strong>
        </div>
      </div>
    </div>
  `;
}

// ════════════════════════════════════════════════════════════
// Loader
// ════════════════════════════════════════════════════════════
async function loadJSON(path) {
  try {
    const r = await fetch(path + "?t=" + Date.now());
    return await r.json();
  } catch (e) {
    return null;
  }
}

async function init() {
  // Signals
  const signals = await loadJSON(SIGNAL_INDEX);
  if (signals && signals.length > 0) {
    document.getElementById("signalGrid").innerHTML = signals.map(renderSignal).join("");
    document.getElementById("lastUpdate").textContent =
      "Last update: " + new Date(signals[0].timestamp).toLocaleString();
  } else {
    document.getElementById("signalGrid").innerHTML =
      '<div class="empty">No signals yet. Agent runs hourly.</div>';
  }

  // Open positions
  const positions = await loadJSON(POSITION_INDEX);
  if (positions && positions.length > 0) {
    document.getElementById("positionsList").innerHTML = positions.map(renderPosition).join("");
  } else {
    document.getElementById("positionsList").innerHTML =
      '<div class="empty">No open positions right now.</div>';
  }

  // Post-mortems
  const pms = await loadJSON(POSTMORTEM_INDEX);
  if (pms && pms.length > 0) {
    document.getElementById("pmList").innerHTML = pms.map(renderPostmortem).join("");
  } else {
    document.getElementById("pmList").innerHTML =
      '<div class="empty">No post-mortems yet. Runs daily after midnight UTC.</div>';
  }

  // Adaptive weights
  const ws = await loadJSON(WEIGHTS_INDEX);
  if (ws && ws.length > 0) {
    document.getElementById("weightsList").innerHTML = ws.map(renderWeights).join("");
  } else {
    document.getElementById("weightsList").innerHTML =
      '<div class="empty">Adaptive weights appear after 20+ closed trades per coin.</div>';
  }

  // v3 NEW: Stats
  const stats = await loadJSON(STATS_EXTENDED);
  document.getElementById("statsBox").innerHTML = renderStats(stats);
}

init();
setInterval(init, 60000);  // refresh every minute