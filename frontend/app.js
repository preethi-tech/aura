"use strict";

const API = "/api";
let auraChart = null;
let signalsChart = null;
let weekdayChart = null;

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
  loadInsights();
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

  renderForecastChip(s.forecast);
  renderInterventions(s.interventions);
  renderCircleNudge(s.circle_nudge);
}

function renderForecastChip(fc) {
  const block = document.getElementById("forecastChip");
  if (!fc || !fc.available) { block.classList.add("hidden"); return; }
  const icon = document.getElementById("forecastIcon");
  const arrows = { worsening: "\u2197", improving: "\u2198", stable: "\u2192" };
  icon.textContent = arrows[fc.trend] || "\u2192";
  icon.style.color =
    fc.trend === "worsening" ? "var(--tier3)" :
    fc.trend === "improving" ? "var(--tier0)" : "var(--text-secondary)";
  document.getElementById("forecastText").textContent = fc.text;
  block.classList.remove("hidden");
}

function renderInterventions(items) {
  const block = document.getElementById("interventionBlock");
  const list = document.getElementById("interventionList");
  if (!items || !items.length) { block.classList.add("hidden"); return; }
  list.innerHTML = items
    .map(
      (it) => `<div class="intervention">
        <div class="intervention-title">${it.title}
          <span class="intervention-dur">${it.duration}</span></div>
        <div class="intervention-action">${it.action}</div>
        <div class="intervention-why">${it.rationale}</div>
      </div>`
    )
    .join("");
  block.classList.remove("hidden");
}

function renderCircleNudge(nudge) {
  const block = document.getElementById("circleNudgeBlock");
  if (!nudge || !nudge.contacts || !nudge.contacts.length) {
    block.classList.add("hidden");
    return;
  }
  document.getElementById("nudgeHeadline").textContent = nudge.headline;
  document.getElementById("nudgePrivacy").textContent = nudge.privacy_note;
  document.getElementById("nudgeContacts").innerHTML = nudge.contacts
    .map((c) => {
      const enc = encodeURIComponent(c.message);
      let link = "";
      if (c.method === "email" && c.detail) {
        link = `<a class="btn btn-secondary" href="mailto:${c.detail}?body=${enc}">Email ${c.name}</a>`;
      } else if ((c.method === "text" || c.method === "phone") && c.detail) {
        link = `<a class="btn btn-secondary" href="sms:${c.detail}?body=${enc}">Message ${c.name}</a>`;
      }
      return `<div class="nudge-contact">
        <div class="nudge-contact-name">${c.name}</div>
        <div class="nudge-message">${c.message}</div>
        <div class="nudge-actions">
          ${link}
          <button class="btn btn-secondary nudge-copy" data-msg="${enc}">Copy message</button>
        </div>
      </div>`;
    })
    .join("");
  // Wire copy buttons
  block.querySelectorAll(".nudge-copy").forEach((btn) => {
    btn.addEventListener("click", () => {
      navigator.clipboard.writeText(decodeURIComponent(btn.dataset.msg));
      btn.textContent = "Copied";
      setTimeout(() => (btn.textContent = "Copy message"), 1500);
    });
  });
  block.classList.remove("hidden");
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

// ---- AI Insights ------------------------------------------------------------
async function loadInsights() {
  let data;
  try {
    data = await api("/insights");
  } catch (e) { return; }

  // Weekly summary
  const ws = data.weekly_summary || {};
  const wsEl = document.getElementById("weeklySummary");
  const srcBadge = document.getElementById("insightSource");
  if (ws.available) {
    wsEl.textContent = ws.narrative;
    wsEl.classList.remove("empty-state");
    srcBadge.textContent = ws.narrative_source === "gemini" ? "Gemini" : "Explainable";
  } else {
    wsEl.textContent = ws.narrative || "Add more check-ins to unlock your summary.";
    wsEl.classList.add("empty-state");
  }

  // Cycles + weekday chart
  const cy = data.cycles || {};
  const cyEl = document.getElementById("cyclesText");
  if (cy.available) {
    cyEl.textContent = cy.text || "No strong weekly pattern yet -- keep checking in.";
    cyEl.classList.remove("empty-state");
    renderWeekdayChart(cy.by_weekday || {});
  } else {
    cyEl.textContent = "Patterns appear once there's enough history.";
    cyEl.classList.add("empty-state");
  }

  // Forecast
  const fc = data.forecast || {};
  const fcEl = document.getElementById("forecastDetail");
  if (fc.available) {
    fcEl.textContent = fc.text;
    fcEl.classList.remove("empty-state");
    document.getElementById("fcNow").textContent = Math.round(fc.current);
    document.getElementById("fcProj").textContent = Math.round(fc.projected);
    const arrow = document.getElementById("fcArrow");
    arrow.innerHTML = fc.trend === "worsening" ? "&#8599;" :
      fc.trend === "improving" ? "&#8600;" : "&rarr;";
    document.getElementById("fcProj").style.color = colorForIndex(fc.projected);
  } else {
    fcEl.textContent = "A short-term projection will appear here.";
    fcEl.classList.add("empty-state");
  }
}

function renderWeekdayChart(byWeekday) {
  const order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const labels = order.filter((d) => d in byWeekday);
  const vals = labels.map((d) => byWeekday[d]);
  const c = getThemeColors();
  const ctx = document.getElementById("weekdayChart");
  if (!ctx) return;
  if (weekdayChart) weekdayChart.destroy();
  weekdayChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: vals,
        backgroundColor: vals.map(colorForIndex),
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { min: 0, max: 100, ticks: { color: c.text }, grid: { color: c.grid } },
        x: { ticks: { color: c.text }, grid: { display: false } },
      },
    },
  });
}

// ---- Circle of Care ---------------------------------------------------------
async function loadContacts() {
  let data;
  try { data = await api("/contacts"); } catch (e) { return; }
  const list = document.getElementById("contactList");
  const contacts = data.contacts || [];
  if (!contacts.length) {
    list.innerHTML = '<li class="empty-state">No trusted contacts yet.</li>';
    return;
  }
  list.innerHTML = contacts
    .map(
      (c) => `<li>
        <span><strong>${c.name}</strong>
          <span class="contact-meta">${c.method}${c.detail ? " &middot; " + c.detail : ""} &middot; notify tier ${c.notify_tier}+</span>
        </span>
        <button class="contact-del" data-id="${c.id}" title="Remove">&times;</button>
      </li>`
    )
    .join("");
  list.querySelectorAll(".contact-del").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/contacts/${btn.dataset.id}`, { method: "DELETE" });
      await loadContacts();
      await loadStatus();
    });
  });
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

    // Load Firebase config if enabled
    if (h.firebase_auth) {
      try {
        const fbConfig = await api("/firebase-config");
        if (fbConfig.enabled && fbConfig.config) {
          firebaseConfig = fbConfig.config;
          // Initialize Firebase
          if (!firebase.apps.length) {
            firebase.initializeApp(firebaseConfig);
          }
        }
      } catch (e) {
        console.error("Failed to load Firebase config:", e);
      }
    }

    // Show auth overlay if Firebase is enabled but no token
    if (h.firebase_auth && !authToken) {
      // Check if Firebase SDK is actually configured
      if (firebase && firebase.auth) {
        document.getElementById("authOverlay").classList.remove("hidden");
      } else {
        // Firebase SDK not configured, hide overlay and use default user
        document.getElementById("authOverlay").classList.add("hidden");
      }
    }
  } catch (e) {
    document.getElementById("engineMode").textContent = "offline";
  }
}

// ---- Refresh + Events -------------------------------------------------------
async function refresh() {
  await Promise.all([
    loadStatus(), loadTimeline(), loadEval(), loadInsights(), loadContacts(),
  ]);
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
      steps: numOrNull("stepsInput"),
      active_minutes: numOrNull("activeInput"),
      screen_time_min: numOrNull("screenInput"),
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
    if (!confirm("Delete ALL data (check-ins + contacts)? This cannot be undone.")) return;
    await api("/data", { method: "DELETE" });
    await refresh();
  });

  // Export data
  document.getElementById("exportBtn").addEventListener("click", async () => {
    const data = await api("/export");
    const blob = new Blob([JSON.stringify(data, null, 2)],
      { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "aura-export.json";
    a.click();
    URL.revokeObjectURL(url);
  });

  // Passive fields toggle
  document.getElementById("togglePassive").addEventListener("click", () => {
    const fields = document.getElementById("passiveFields");
    const btn = document.getElementById("togglePassive");
    const shown = !fields.classList.contains("hidden");
    fields.classList.toggle("hidden");
    btn.textContent = shown
      ? "+ Add passive signals (steps, screen time)"
      : "- Hide passive signals";
  });

  // Google Fit sync
  document.getElementById("fitSyncBtn").addEventListener("click", async () => {
    const status = document.getElementById("fitStatus");
    status.textContent = "Syncing...";
    try {
      const res = await api("/fit/sync", {
        method: "POST", body: JSON.stringify({ days: 60 }),
      });
      if (res.synced > 0) {
        status.textContent = `Synced ${res.synced} days (${res.source})`;
        await refresh();
      } else {
        status.textContent = res.detail || "Nothing to sync yet";
      }
      setTimeout(() => (status.textContent = ""), 3500);
    } catch (err) {
      status.textContent = "Sync failed";
    }
  });

  // Circle of Care: add contact
  document.getElementById("contactForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = document.getElementById("contactStatus");
    const name = document.getElementById("contactName").value.trim();
    if (!name) { status.textContent = "Name required"; return; }
    status.textContent = "Adding...";
    try {
      await api("/contacts", {
        method: "POST",
        body: JSON.stringify({
          name,
          method: document.getElementById("contactMethod").value,
          detail: document.getElementById("contactDetail").value,
          notify_tier: parseInt(document.getElementById("contactTier").value, 10),
        }),
      });
      document.getElementById("contactName").value = "";
      document.getElementById("contactDetail").value = "";
      status.textContent = "Added";
      await loadContacts();
      await loadStatus();
      setTimeout(() => (status.textContent = ""), 2000);
    } catch (err) {
      status.textContent = "Error adding";
    }
  });

  // Crisis modal
  document.getElementById("openCrisis").addEventListener("click", openCrisis);
  document.getElementById("openCrisis2").addEventListener("click", openCrisis);
  document.getElementById("closeCrisis").addEventListener("click", closeCrisis);
  document.getElementById("modalBackdrop").addEventListener("click", closeCrisis);

  // Assessments
  document.getElementById("assessForm").addEventListener("submit", submitAssessment);
  document.getElementById("instrumentSelect").addEventListener("change", renderAssessment);

  // Sign in with Firebase Auth
  document.getElementById("googleSignIn").addEventListener("click", async () => {
    const btn = document.getElementById("googleSignIn");
    btn.disabled = true;
    btn.textContent = "Signing in...";

    try {
      if (!firebase || !firebase.auth || !firebaseConfig) {
        alert("Firebase not configured. Please enable Firebase in the deployment.");
        btn.disabled = false;
        btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg> Sign in with Google`;
        return;
      }

      const provider = new firebase.auth.GoogleAuthProvider();
      const result = await firebase.auth().signInWithPopup(provider);
      const idToken = await result.user.getIdToken();
      authToken = idToken;

      // Hide auth overlay
      document.getElementById("authOverlay").classList.add("hidden");

      // Show user email
      document.getElementById("userEmail").textContent = result.user.email;
      document.getElementById("userMenu").classList.remove("hidden");

      // Refresh data with authenticated user
      await refresh();
    } catch (error) {
      console.error("Sign-in error:", error);
      alert("Sign-in failed: " + error.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg> Sign in with Google`;
    }
  });

  // Sign out
  document.getElementById("signOutBtn").addEventListener("click", async () => {
    try {
      if (firebase && firebase.auth) {
        await firebase.auth().signOut();
      }
      authToken = null;
      document.getElementById("userMenu").classList.add("hidden");
      document.getElementById("authOverlay").classList.remove("hidden");
      await refresh();
    } catch (error) {
      console.error("Sign-out error:", error);
    }
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
