"use strict";

const API = "/api";
let auraChart = null;
let signalsChart = null;

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

const TIER_CLASS = { 0: "t0", 1: "t1", 2: "t2", 3: "t3" };
const TIER_COLORS = ["#4caf82", "#d8c150", "#e0913e", "#e05a5a"];

function colorForIndex(v) {
  if (v == null) return "#8ea0ab";
  if (v < 25) return TIER_COLORS[0];
  if (v < 50) return TIER_COLORS[1];
  if (v < 75) return TIER_COLORS[2];
  return TIER_COLORS[3];
}

// ---- Status card -----------------------------------------------------------
async function loadStatus() {
  const s = await api("/status");
  const indexEl = document.getElementById("indexValue");
  const badge = document.getElementById("tierBadge");
  const msg = document.getElementById("tierMessage");
  const whyList = document.getElementById("whyList");
  const banner = document.getElementById("crisisBanner");

  banner.classList.toggle("hidden", !s.safety_alert);

  if (!s.has_data) {
    indexEl.textContent = "—";
    indexEl.style.color = "var(--muted)";
    badge.textContent = "No data yet";
    badge.className = "tier";
    msg.textContent = "Add a check-in or load the demo timeline to begin.";
    whyList.innerHTML = '<li class="muted">—</li>';
    return;
  }

  indexEl.textContent = s.aura_index != null ? s.aura_index : "—";
  indexEl.style.color = colorForIndex(s.aura_index);

  let label = s.tier_label + (s.calibrating ? " · calibrating" : "");
  badge.textContent = label;
  badge.className = "tier " + (TIER_CLASS[s.tier] || "");
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
      '<li class="muted">No signals are meaningfully above your baseline.</li>';
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

// ---- Charts ----------------------------------------------------------------
async function loadTimeline() {
  const data = await api("/timeline");
  const t = data.timeline;
  const labels = t.map((d) => d.date.slice(5)); // MM-DD

  renderAuraChart(labels, t);
  renderSignalsChart(labels, t);

  document.getElementById(
    "dataInfo"
  ).textContent = `${t.length} check-in(s) stored locally.`;
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
          borderColor: "#5ac8b0",
          backgroundColor: "rgba(90,200,176,0.12)",
          pointBackgroundColor: pointColors,
          pointRadius: 3,
          fill: true,
          tension: 0.3,
        },
        threshold(labels, 25, "#4caf82"),
        threshold(labels, 50, "#d8c150"),
        threshold(labels, 75, "#e05a5a"),
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        y: { min: 0, max: 100, ticks: { color: "#8ea0ab" }, grid: { color: "#26323a" } },
        x: { ticks: { color: "#8ea0ab", maxTicksLimit: 12 }, grid: { display: false } },
      },
    },
  });
}

function renderSignalsChart(labels, t) {
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
        mk("sleep_hours", "#5ac8b0"),
        mk("social_count", "#7aa2f7"),
        mk("energy", "#c3a6ff"),
        mk("neg_sentiment", "#e0913e"),
      ],
    },
    options: {
      plugins: { legend: { labels: { color: "#8ea0ab", boxWidth: 12 } } },
      scales: {
        y: { position: "left", ticks: { color: "#8ea0ab" }, grid: { color: "#26323a" } },
        y1: {
          position: "right", min: 0, max: 1,
          ticks: { color: "#e0913e" }, grid: { display: false },
          title: { display: true, text: "tone", color: "#e0913e" },
        },
        x: { ticks: { color: "#8ea0ab", maxTicksLimit: 12 }, grid: { display: false } },
      },
    },
  });
}

// ---- Crisis resources ------------------------------------------------------
async function loadResources() {
  try {
    const data = await api("/resources");
    const list = document.getElementById("resourceList");
    list.innerHTML = data.crisis_resources
      .map(
        (r) => `<li>
          <div class="r-name">${r.name} <span class="muted small">(${r.region})</span></div>
          <div class="r-contact">${r.contact}</div>
          <a href="${r.url}" target="_blank" rel="noopener">${r.url}</a>
        </li>`
      )
      .join("");
  } catch (e) {
    /* resources are best-effort */
  }
}

function openCrisis() {
  document.getElementById("crisisModal").classList.remove("hidden");
}
function closeCrisis() {
  document.getElementById("crisisModal").classList.add("hidden");
}

// ---- Assessments (PHQ-9 / GAD-7) -------------------------------------------
let ASSESS_SCHEMA = null;

async function loadAssessmentSchema() {
  try {
    ASSESS_SCHEMA = await api("/assessments/schema");
    renderAssessment();
  } catch (e) {
    /* best-effort */
  }
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
        ${opts
          .map((o) => `<option value="${o.value}">${o.value} · ${o.label}</option>`)
          .join("")}
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
  status.textContent = "Submitting…";
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

// ---- Evaluation panel ------------------------------------------------------
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
      panel.innerHTML =
        '<p class="muted">Load the demo or add assessments to see metrics.</p>';
      return;
    }
    const c = e.correlation || {};
    const fmt = (v) => (v == null ? "—" : v);
    const lead = e.lead_time_days == null ? "—" : `${e.lead_time_days} d`;
    panel.innerHTML =
      metricTile("Corr · PHQ-9", fmt(c["PHQ-9"]), "Aura vs PHQ-9") +
      metricTile("Corr · GAD-7", fmt(c["GAD-7"]), "Aura vs GAD-7") +
      metricTile("Lead time", lead, "before 1st PHQ-9 case") +
      metricTile("Precision", fmt(e.precision), "tier≥2 alerts") +
      metricTile("Recall", fmt(e.recall), "of case days") +
      metricTile("F1", fmt(e.f1), "");
  } catch (err) {
    panel.innerHTML = '<p class="muted">Evaluation unavailable.</p>';
  }
}

// ---- Refresh + events ------------------------------------------------------
async function refresh() {
  await Promise.all([loadStatus(), loadTimeline(), loadEval()]);
}

async function loadEngineMode() {
  try {
    const h = await api("/health");
    document.getElementById("engineMode").textContent = h.gemini_enabled
      ? `Gemini: ${h.model}`
      : "Offline analyzer (no API key)";
  } catch (e) {
    document.getElementById("engineMode").textContent = "offline";
  }
}

function wireEvents() {
  const energy = document.getElementById("energyInput");
  energy.addEventListener("input", () => {
    document.getElementById("energyVal").textContent = energy.value;
  });

  document.getElementById("dateInput").valueAsDate = new Date();

  document.getElementById("entryForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = document.getElementById("formStatus");
    status.textContent = "Saving…";
    const body = {
      date: document.getElementById("dateInput").value || null,
      journal_text: document.getElementById("journalInput").value,
      sleep_hours: numOrNull("sleepInput"),
      social_count: numOrNull("socialInput"),
      energy: parseInt(energy.value, 10),
    };
    try {
      await api("/entries", { method: "POST", body: JSON.stringify(body) });
      status.textContent = "Saved ✓";
      document.getElementById("journalInput").value = "";
      await refresh();
      setTimeout(() => (status.textContent = ""), 1500);
    } catch (err) {
      status.textContent = "Error saving";
    }
  });

  document.getElementById("seedBtn").addEventListener("click", async () => {
    await api("/seed", {
      method: "POST",
      body: JSON.stringify({ scenario: "decline", days: 60 }),
    });
    await refresh();
  });

  document.getElementById("wipeBtn").addEventListener("click", async () => {
    if (!confirm("Delete ALL locally stored check-ins? This cannot be undone."))
      return;
    await api("/data", { method: "DELETE" });
    await refresh();
  });

  document.getElementById("openCrisis").addEventListener("click", openCrisis);
  document.getElementById("openCrisis2").addEventListener("click", openCrisis);
  document.getElementById("closeCrisis").addEventListener("click", closeCrisis);

  document
    .getElementById("assessForm")
    .addEventListener("submit", submitAssessment);
  document
    .getElementById("instrumentSelect")
    .addEventListener("change", renderAssessment);
}

function numOrNull(id) {
  const v = document.getElementById(id).value;
  return v === "" ? null : Number(v);
}

// ---- Init ------------------------------------------------------------------
wireEvents();
loadEngineMode();
loadResources();
loadAssessmentSchema();
refresh();
