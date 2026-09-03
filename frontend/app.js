"use strict";

const API = "/api";
let auraChart = null;
let signalsChart = null;

// ---- Theme Toggle -----------------------------------------------------------
function initTheme() {
  const saved = localStorage.getItem("aura-theme");
  const theme = saved || "light";
  document.documentElement.setAttribute("data-theme", theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("aura-theme", next);
  // Redraw charts with new theme colors
  loadTimeline();
}

function getThemeColors() {
  const style = getComputedStyle(document.documentElement);
  return {
    text: style.getPropertyValue("--text-secondary").trim(),
    grid: style.getPropertyValue("--chart-grid").trim(),
    accent: style.getPropertyValue("--accent").trim(),
    tier0: style.getPropertyValue("--tier0").trim(),
    tier1: style.getPropertyValue("--tier1").trim(),
    tier2: style.getPropertyValue("--tier2").trim(),
    tier3: style.getPropertyValue("--tier3").trim(),
  };
}

// ---- API Helpers ------------------------------------------------------------
let authToken = null;

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...opts.headers };
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  const res = await fetch(API + path, { ...opts, headers });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

const TIER_CLASS = { 0: "t0", 1: "t1", 2: "t2", 3: "t3" };

function colorForIndex(v) {
  const c = getThemeColors();
  if (v == null) return c.text;
  if (v < 25) return c.tier0;
  if (v < 50) return c.tier1;
  if (v < 75) return c.tier2;
  return c.tier3;
}

// ---- Gauge Animation --------------------------------------------------------
function updateGauge(value) {
  const fill = document.getElementById("gaugeFill");
  const circumference = 2 * Math.PI * 52; // r=52
  if (value == null) {
    fill.style.strokeDashoffset = circumference;
    fill.style.stroke = getThemeColors().text;
    return;
  }
  const offset = circumference - (value / 100) * circumference;
  fill.style.strokeDashoffset = offset;
  fill.style.stroke = colorForIndex(value);
}

// ---- Status Card ------------------------------------------------------------
async function loadStatus() {
  const s = await api("/status");
  const indexEl = document.getElementById("indexValue");
  const badge = document.getElementById("tierBadge");
  const msg = document.getElementById("tierMessage");
  const whyList = document.getElementById("whyList");
  const banner = document.getElementById("crisisBanner");

  banner.classList.toggle("hidden", !s.safety_alert);

  if (!s.has_data) {
    indexEl.textContent = "--";
    indexEl.style.color = "var(--text-secondary)";
    updateGauge(null);
    badge.textContent = "No data yet";
    badge.className = "tier-badge";
    msg.textContent = "Add a check-in or load the demo timeline to begin.";
    whyList.innerHTML = '<li class="empty-state">--</li>';
    return;
  }

  indexEl.textContent = s.aura_index != null ? s.aura_index : "--";
  indexEl.style.color = colorForIndex(s.aura_index);
  updateGauge(s.aura_index);

  let label = s.tier_label + (s.calibrating ? " · calibrating" : "");
  badge.textContent = label;
  badge.className = "tier-badge " + (TIER_CLASS[s.tier] || "");
  msg.textContent = s.tier_message || "";

  if (s.top_signals && s.top_signals.length) {
    whyList.innerHTML = s.top_signals
      .map(
        (sig) =>
          `<li><span class="sig-label">${sig.label}.</span> ${sig.message}</li>`
      )
      .join("");
  } else {
    whyList.innerHTML =
      '<li class="empty-state">No signals are meaningfully above your baseline.</li>';
  }

  const refl = document.getElementById("reflectionBlock");
  const reflText = document.getElementById("reflectionText");
  if (s.reflection) {
    reflText.textContent = s.reflection;
    refl.classList.remove("hidden");
  } else {
    refl.classList.add("hidden");
  }
}

// ---- Charts -----------------------------------------------------------------
async function loadTimeline() {
  const data = await api("/timeline");
  const t = data.timeline;
  const labels = t.map((d) => d.date.slice(5));

  renderAuraChart(labels, t);
  renderSignalsChart(labels, t);

  document.getElementById("dataInfo").textContent =
    `${t.length} check-in(s) stored.`;
}

function threshold(labels, value, color) {
  return {
    label: "",
    data: labels.map(() => value),
    borderColor: color,
    borderWidth: 1,
    borderDash: [4, 4],
    pointRadius: 0,
    fill: false,
    tension: 0,
  };
}

function renderAuraChart(labels, t) {
  const c = getThemeColors();
  const idx = t.map((d) => d.aura_index);
  const pointColors = idx.map(colorForIndex);
  const ctx = document.getElementById("auraChart");
  if (auraChart) auraChart.destroy();
  auraChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Aura Index",
          data: idx,
          borderColor: c.accent,
          backgroundColor: c.accent + "18",
          pointBackgroundColor: pointColors,
          pointRadius: 2.5,
          borderWidth: 2,
          fill: true,
          tension: 0.3,
        },
        threshold(labels, 25, c.tier0),
        threshold(labels, 50, c.tier1),
        threshold(labels, 75, c.tier3),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { min: 0, max: 100, ticks: { color: c.text }, grid: { color: c.grid } },
        x: { ticks: { color: c.text, maxTicksLimit: 12 }, grid: { display: false } },
      },
    },
  });
}

function renderSignalsChart(labels, t) {
  const c = getThemeColors();
  const ctx = document.getElementById("signalsChart");
  if (signalsChart) signalsChart.destroy();
  const mk = (key, color) => ({
    label: key,
    data: t.map((d) => d[key]),
    borderColor: color,
    backgroundColor: color,
    pointRadius: 0,
    borderWidth: 2,
    tension: 0.3,
    yAxisID: key === "neg_sentiment" ? "y1" : "y",
  });
  signalsChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        mk("sleep_hours", c.accent),
        mk("social_count", "#7aa2f7"),
        mk("energy", "#c3a6ff"),
        mk("neg_sentiment", c.tier2),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: c.text, boxWidth: 12, usePointStyle: true } } },
      scales: {
        y: { position: "left", ticks: { color: c.text }, grid: { color: c.grid } },
        y1: {
          position: "right", min: 0, max: 1,
          ticks: { color: c.tier2 }, grid: { display: false },
          title: { display: true, text: "tone", color: c.tier2 },
        },
        x: { ticks: { color: c.text, maxTicksLimit: 12 }, grid: { display: false } },
      },
    },
  });
}

// ---- Crisis Resources -------------------------------------------------------
async function loadResources() {
  try {
    const data = await api("/resources");
    const list = document.getElementById("resourceList");
    list.innerHTML = data.crisis_resources
      .map(
        (r) => `<li>
          <div class="r-name">${r.name} <span style="color:var(--text-secondary);font-size:12px">(${r.region})</span></div>
          <div class="r-contact">${r.contact}</div>
          <a href="${r.url}" target="_blank" rel="noopener">${r.url}</a>
        </li>`
      )
      .join("");
  } catch (e) { /* best-effort */ }
}

function openCrisis() { document.getElementById("crisisModal").classList.remove("hidden"); }
function closeCrisis() { document.getElementById("crisisModal").classList.add("hidden"); }

// ---- Assessments ------------------------------------------------------------
let ASSESS_SCHEMA = null;

async function loadAssessmentSchema() {
  try {
    ASSESS_SCHEMA = await api("/assessments/schema");
    renderAssessment();
  } catch (e) { /* best-effort */ }
}

function renderAssessment() {
  if (!ASSESS_SCHEMA) return;
  const inst = document.getElementById("instrumentSelect").value;
  const meta = ASSESS_SCHEMA.instruments[inst];
  const opts = ASSESS_SCHEMA.response_options;
  document.getElementById("assessItems").innerHTML = meta.items
    .map(
      (item, i) => `
    <div class="assess-item">
      <label>${i + 1}. ${item}</label>
      <select data-idx="${i}">
        ${opts.map((o) => `<option value="${o.value}">${o.value} - ${o.label}</option>`).join("")}
      </select>
    </div>`
    )
    .join("");
}

async function submitAssessment(e) {
  e.preventDefault();
  const inst = document.getElementById("instrumentSelect").value;
  const responses = Array.from(
    document.querySelectorAll("#assessItems select")
  ).map((s) => parseInt(s.value, 10));
  const status = document.getElementById("assessStatus");
  status.textContent = "Submitting...";
  try {
    const res = await api("/assessments", {
      method: "POST",
      body: JSON.stringify({ instrument: inst, responses }),
    });
    status.textContent = `${res.instrument}: ${res.total}/${res.max} (${res.severity})`;
    if (res.safety_alert) {
      document.getElementById("crisisBanner").classList.remove("hidden");
    }
    await loadEval();
  } catch (err) {
    status.textContent = "Error submitting";
  }
}

// ---- Evaluation Panel -------------------------------------------------------
function metricTile(label, value, sub) {
  return `<div class="metric">
    <div class="metric-val">${value}</div>
    <div class="metric-label">${label}</div>
    ${sub ? `<div class="metric-sub">${sub}</div>` : ""}
  </div>`;
}

async function loadEval() {
  const panel = document.getElementById("evalPanel");
  try {
    const e = await api("/eval");
    if (!e.available) {
      panel.innerHTML = '<p class="empty-state">Load the demo or add assessments to see metrics.</p>';
      return;
    }
    const c = e.correlation || {};
    const fmt = (v) => (v == null ? "--" : v);
    const lead = e.lead_time_days == null ? "--" : `${e.lead_time_days}d`;
    panel.innerHTML =
      metricTile("Corr PHQ-9", fmt(c["PHQ-9"]), "Aura vs PHQ-9") +
      metricTile("Corr GAD-7", fmt(c["GAD-7"]), "Aura vs GAD-7") +
      metricTile("Lead time", lead, "before 1st case") +
      metricTile("Precision", fmt(e.precision), "tier 2+ alerts") +
      metricTile("Recall", fmt(e.recall), "of case days") +
      metricTile("F1", fmt(e.f1), "harmonic mean");
  } catch (err) {
    panel.innerHTML = '<p class="empty-state">Evaluation unavailable.</p>';
  }
}

// ---- Service Tags -----------------------------------------------------------
async function loadEngineMode() {
  try {
    const h = await api("/health");
    document.getElementById("engineMode").textContent = h.gemini_enabled
      ? `Gemini: ${h.model}`
      : "Offline analyzer";

    // Storage badge
    const badge = document.getElementById("storageBadge");
    badge.textContent = h.storage === "firestore" ? "Cloud" : "Local";

    // Footer service tags
    const toggle = (id, active) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle("active", active);
    };
    toggle("serviceGemini", h.gemini_enabled);
    toggle("serviceFirebase", h.storage === "firestore");
    toggle("serviceLogging", h.cloud_logging);

    // Show auth overlay if Firebase is enabled but no token
    if (h.firebase_auth && !authToken) {
      document.getElementById("authOverlay").classList.remove("hidden");
    }
  } catch (e) {
    document.getElementById("engineMode").textContent = "offline";
  }
}

// ---- Refresh + Events -------------------------------------------------------
async function refresh() {
  await Promise.all([loadStatus(), loadTimeline(), loadEval()]);
}

function wireEvents() {
  // Theme toggle
  document.getElementById("themeToggle").addEventListener("click", toggleTheme);

  // Energy slider
  const energy = document.getElementById("energyInput");
  energy.addEventListener("input", () => {
    document.getElementById("energyVal").textContent = energy.value;
  });

  document.getElementById("dateInput").valueAsDate = new Date();

  // Entry form
  document.getElementById("entryForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = document.getElementById("formStatus");
    status.textContent = "Saving...";
    const body = {
      date: document.getElementById("dateInput").value || null,
      journal_text: document.getElementById("journalInput").value,
      sleep_hours: numOrNull("sleepInput"),
      social_count: numOrNull("socialInput"),
      energy: parseInt(energy.value, 10),
    };
    try {
      await api("/entries", { method: "POST", body: JSON.stringify(body) });
      status.textContent = "Saved";
      document.getElementById("journalInput").value = "";
      await refresh();
      setTimeout(() => (status.textContent = ""), 2000);
    } catch (err) {
      status.textContent = "Error saving";
    }
  });

  // Seed + wipe
  document.getElementById("seedBtn").addEventListener("click", async () => {
    await api("/seed", {
      method: "POST",
      body: JSON.stringify({ scenario: "decline", days: 60 }),
    });
    await refresh();
  });

  document.getElementById("wipeBtn").addEventListener("click", async () => {
    if (!confirm("Delete ALL check-ins? This cannot be undone.")) return;
    await api("/data", { method: "DELETE" });
    await refresh();
  });

  // Crisis modal
  document.getElementById("openCrisis").addEventListener("click", openCrisis);
  document.getElementById("openCrisis2").addEventListener("click", openCrisis);
  document.getElementById("closeCrisis").addEventListener("click", closeCrisis);
  document.getElementById("modalBackdrop").addEventListener("click", closeCrisis);

  // Assessments
  document.getElementById("assessForm").addEventListener("submit", submitAssessment);
  document.getElementById("instrumentSelect").addEventListener("change", renderAssessment);

  // Sign in button (placeholder for Firebase SDK integration)
  document.getElementById("googleSignIn").addEventListener("click", () => {
    alert("To enable Google Sign-in, configure Firebase Auth.\nSee docs/DEPLOY.md for setup steps.");
  });
}

function numOrNull(id) {
  const v = document.getElementById(id).value;
  return v === "" ? null : Number(v);
}

// ---- Init -------------------------------------------------------------------
initTheme();
wireEvents();
loadEngineMode();
loadResources();
loadAssessmentSchema();
refresh();
