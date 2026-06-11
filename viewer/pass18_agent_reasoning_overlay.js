(function () {
  "use strict";

  const PASS18_ID = "scout-pass18-agent-reasoning";
  const STATE = {
    lastSignature: "",
    lastSignals: [],
    lastPayload: null,
    active: true
  };

  function $(selector) {
    return document.querySelector(selector);
  }

  function clean(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "object") {
      try { return JSON.stringify(value); } catch (err) { return String(value); }
    }
    return String(value).replace(/\s+/g, " ").trim();
  }

  function lower(value) {
    return clean(value).toLowerCase();
  }

  function textOf(signal) {
    if (!signal || typeof signal !== "object") return "";
    return Object.keys(signal).map(k => clean(signal[k])).join(" ").toLowerCase();
  }

  function titleOf(signal) {
    if (!signal || typeof signal !== "object") return "No signal selected";
    const keys = ["title", "headline", "name", "summary", "observation", "text"];
    for (const key of keys) {
      const val = clean(signal[key]);
      if (val) return val;
    }
    return "Untitled signal";
  }

  function sourceOf(signal) {
    if (!signal || typeof signal !== "object") return "current sources";
    const keys = ["source", "source_name", "publisher", "domain", "url", "link"];
    for (const key of keys) {
      const val = clean(signal[key]);
      if (val) return val;
    }
    return "current sources";
  }

  function getInputValue(candidates) {
    for (const sel of candidates) {
      const node = $(sel);
      if (node && "value" in node) return clean(node.value);
    }
    return "";
  }

  function getMission() {
    const query = getInputValue([
      "#topicInput", "#queryInput", "#keywordInput", "[name='query']", "[name='keyword']",
      "input[placeholder*='Topic' i]", "input[placeholder*='Keyword' i]", "textarea[placeholder*='Topic' i]"
    ]) || "GLP-1 manufacturing pressure";

    const company = getInputValue([
      "#companyInput", "#companyFocus", "[name='company']", "[name='company_focus']",
      "input[placeholder*='Company' i]"
    ]);

    let mode = getInputValue(["#scanMode", "[name='mode']", "select"]);
    const checkedMode = $("input[name='mode']:checked, input[name='scan_mode']:checked");
    if (checkedMode) mode = clean(checkedMode.value);
    if (!mode) mode = "broad_targeted";

    const source = getInputValue([
      "#sourceInput", "#sourceFilter", "[name='source']", "[name='source_filter']",
      "input[placeholder*='Source' i]"
    ]);

    return { query, company, mode, source };
  }

  function hasAny(text, terms) {
    return terms.some(term => text.indexOf(term) >= 0);
  }

  function modeLabel(mode) {
    const m = lower(mode);
    if (m.indexOf("targeted") >= 0 && m.indexOf("broad") < 0) return "Targeted scan";
    if (m.indexOf("broad") >= 0 && m.indexOf("targeted") < 0) return "Broad scan";
    return "Broad + targeted scan";
  }

  function modeMeaning(mode) {
    const m = lower(mode);
    if (m.indexOf("targeted") >= 0 && m.indexOf("broad") < 0) {
      return "Prioritizes direct topic, company, and selected-source evidence. Adjacent results should be labeled.";
    }
    if (m.indexOf("broad") >= 0 && m.indexOf("targeted") < 0) {
      return "Prioritizes market context, pressure patterns, and wider industry signals.";
    }
    return "Balances market-wide context with targeted relevance and executive usefulness.";
  }

  function sourceIsCyber(source) {
    return hasAny(lower(source), ["cisa", "nvd", "cyber", "cve", "kev", "security", "ics", "ot"]);
  }

  function queryFamily(query) {
    const q = lower(query);
    if (hasAny(q, ["cyber", "ot", "cisa", "vulnerability", "cve", "kev"])) return "cyber/OT risk";
    if (hasAny(q, ["glp", "semaglutide", "tirzepatide", "obesity", "injectable"])) return "GLP-1 / injectable manufacturing";
    if (hasAny(q, ["gmp", "fda", "validation", "inspection", "warning", "quality"])) return "FDA/GMP validation pressure";
    if (hasAny(q, ["cdmo", "outsourcing", "fill", "finish", "capacity"])) return "CDMO / fill-finish capacity";
    if (hasAny(q, ["bms", "building", "commissioning", "automation", "facilities"])) return "regulated facilities integration";
    return "strategic life-sciences signal";
  }

  function evidenceFit(signal, mission) {
    const blob = textOf(signal);
    const q = lower(mission.query);
    let direct = false;
    let adjacent = false;
    let why = [];

    const families = [
      { name: "cyber/OT", q: ["cyber", "ot", "cisa", "vulnerability", "cve", "kev"], s: ["cyber", "ot", "cisa", "vulnerability", "cve", "kev", "security", "ics"] },
      { name: "GLP-1/manufacturing", q: ["glp", "manufacturing", "injectable"], s: ["glp", "manufacturing", "capacity", "fill", "finish", "injectable", "sterile", "cdmo", "lilly", "novo"] },
      { name: "FDA/GMP", q: ["fda", "gmp", "validation"], s: ["fda", "gmp", "validation", "inspection", "warning", "compliance", "quality"] },
      { name: "CDMO/capacity", q: ["cdmo", "outsourcing", "capacity"], s: ["cdmo", "outsourcing", "capacity", "supplier", "fill", "finish", "manufacturing"] },
      { name: "facilities/BMS", q: ["bms", "automation", "commissioning", "facilities"], s: ["bms", "building", "facility", "commissioning", "automation", "controls", "environmental"] }
    ];

    for (const family of families) {
      if (hasAny(q, family.q)) {
        if (hasAny(blob, family.s)) {
          direct = true;
          why.push("Evidence language matches the requested " + family.name + " lane.");
        } else {
          adjacent = true;
          why.push("Requested " + family.name + " lane is not directly visible in the top evidence.");
        }
      }
    }

    if (mission.company) {
      const c = lower(mission.company);
      if (blob.indexOf(c) >= 0 || (c === "eli lilly" && blob.indexOf("lilly") >= 0) || (c === "novo nordisk" && blob.indexOf("novo") >= 0)) {
        direct = true;
        why.push("Company focus appears in the signal evidence.");
      } else {
        adjacent = true;
        why.push("Company focus is not directly visible; treat this as adjacent unless supporting evidence says otherwise.");
      }
    }

    if (mission.source) {
      const sourceName = lower(sourceOf(signal));
      const desired = lower(mission.source);
      if (sourceName.indexOf(desired) >= 0 || desired.indexOf(sourceName) >= 0) {
        why.push("Selected source constraint is represented.");
      } else {
        adjacent = true;
        why.push("Selected source constraint may be source-limited or adjacent.");
      }
    }

    if (hasAny(q, ["cyber", "ot"]) && mission.source && !sourceIsCyber(mission.source)) {
      adjacent = true;
      why.push("Cyber/OT mission is being run against a non-cyber source; mark as source-limited adjacent.");
    }

    const rawTruth = lower(clean(signal && (signal.truth_label || signal.strategic_warnings || signal.company_adjacent_only || signal.source_filter_adjacent_only)));
    if (rawTruth.indexOf("adjacent") >= 0 || rawTruth.indexOf("no direct") >= 0 || rawTruth.indexOf("source-limited") >= 0) adjacent = true;

    let label = "Direct evidence";
    if (adjacent && direct) label = "Mixed direct + adjacent";
    else if (adjacent) label = "Adjacent / source-limited";
    else if (!direct) label = "Contextual evidence";

    return { label, why };
  }

  function normalize(payload) {
    if (Array.isArray(payload)) return payload.filter(x => x && typeof x === "object");
    if (payload && typeof payload === "object") {
      for (const key of ["signals", "items", "data", "results"]) {
        if (Array.isArray(payload[key])) return payload[key].filter(x => x && typeof x === "object");
      }
    }
    return [];
  }

  function buildReasoning(signals) {
    const mission = getMission();
    const top = signals && signals.length ? signals[0] : null;
    const fit = evidenceFit(top, mission);
    const family = queryFamily(mission.query);
    const source = sourceOf(top);

    const steps = [
      "Interpreted mission: " + family,
      "Applied topic / keyword weighting",
      mission.company ? "Applied company focus: " + mission.company : "No company focus supplied",
      mission.source ? "Applied source filter: " + mission.source : "Used available source pool",
      "Applied scan mode: " + modeLabel(mission.mode),
      "Ranked candidate signals",
      "Checked direct vs adjacent evidence",
      "Prepared executive brief"
    ];

    const why = [
      "Top signal: " + titleOf(top),
      "Source: " + source,
      "Evidence status: " + fit.label,
      "Scan mode: " + modeLabel(mission.mode) + " — " + modeMeaning(mission.mode)
    ].concat(fit.why);

    return { mission, top, fit, steps, why };
  }

  function ensurePanel() {
    let panel = document.getElementById(PASS18_ID);
    if (panel) return panel;

    const style = document.createElement("style");
    style.setAttribute("data-pass18-agent-reasoning", "true");
    style.textContent = `
      #${PASS18_ID} {
        position: fixed;
        right: 18px;
        bottom: 18px;
        z-index: 9999;
        width: min(430px, calc(100vw - 36px));
        max-height: min(570px, calc(100vh - 36px));
        overflow: auto;
        border: 1px solid rgba(164, 185, 210, 0.28);
        border-radius: 20px;
        background: rgba(8, 16, 29, 0.93);
        color: #ecf6ff;
        box-shadow: 0 24px 70px rgba(0, 0, 0, 0.38);
        backdrop-filter: blur(18px);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
      }
      #${PASS18_ID}.collapsed .pass18-body { display: none; }
      #${PASS18_ID} .pass18-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 14px 16px;
        cursor: pointer;
        border-bottom: 1px solid rgba(164, 185, 210, 0.16);
      }
      #${PASS18_ID} .pass18-title {
        font-weight: 800;
        letter-spacing: 0.02em;
        font-size: 13px;
        text-transform: uppercase;
      }
      #${PASS18_ID} .pass18-pill {
        border: 1px solid rgba(108, 230, 197, 0.35);
        color: #8df3d5;
        border-radius: 999px;
        padding: 4px 9px;
        font-size: 11px;
        white-space: nowrap;
      }
      #${PASS18_ID} .pass18-body { padding: 14px 16px 16px; }
      #${PASS18_ID} h4 {
        margin: 12px 0 7px;
        font-size: 12px;
        color: #9fd2ff;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      #${PASS18_ID} .pass18-card {
        border: 1px solid rgba(164, 185, 210, 0.14);
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.045);
        padding: 10px 11px;
        margin: 8px 0;
      }
      #${PASS18_ID} .pass18-line {
        display: flex;
        gap: 8px;
        align-items: flex-start;
        margin: 7px 0;
        font-size: 12.5px;
        line-height: 1.35;
      }
      #${PASS18_ID} .pass18-dot {
        flex: 0 0 auto;
        width: 6px;
        height: 6px;
        margin-top: 6px;
        border-radius: 50%;
        background: #8df3d5;
      }
      #${PASS18_ID} .pass18-muted { color: #b7c9dc; font-size: 12px; line-height: 1.4; }
      #${PASS18_ID} .pass18-strong { color: #ffffff; font-weight: 700; }
      #${PASS18_ID} button {
        all: unset;
        cursor: pointer;
        color: #b7c9dc;
        font-size: 12px;
      }
      @media (max-width: 820px) {
        #${PASS18_ID} {
          left: 14px;
          right: 14px;
          bottom: 14px;
          width: auto;
        }
      }
    `;
    document.head.appendChild(style);

    panel = document.createElement("section");
    panel.id = PASS18_ID;
    panel.innerHTML = `
      <div class="pass18-head" title="Click to collapse / expand">
        <div>
          <div class="pass18-title">Agent Reasoning</div>
          <div class="pass18-muted">Why this signal won + run log</div>
        </div>
        <div class="pass18-pill">Pass 18</div>
      </div>
      <div class="pass18-body">
        <div class="pass18-card">
          <div class="pass18-muted">Waiting for Scout Horizon signals...</div>
        </div>
      </div>
    `;
    panel.querySelector(".pass18-head").addEventListener("click", function () {
      panel.classList.toggle("collapsed");
    });
    document.body.appendChild(panel);
    return panel;
  }

  function render(signals) {
    const panel = ensurePanel();
    const body = panel.querySelector(".pass18-body");
    const reasoning = buildReasoning(signals);
    const statusClass = reasoning.fit.label;
    const whyLines = reasoning.why.map(line => `
      <div class="pass18-line"><span class="pass18-dot"></span><span>${escapeHtml(line)}</span></div>
    `).join("");
    const stepLines = reasoning.steps.map((line, idx) => `
      <div class="pass18-line"><span class="pass18-dot"></span><span><span class="pass18-strong">${idx + 1}.</span> ${escapeHtml(line)}</span></div>
    `).join("");

    body.innerHTML = `
      <div class="pass18-card">
        <div class="pass18-muted">Mission</div>
        <div class="pass18-strong">${escapeHtml(reasoning.mission.query || "No topic supplied")}</div>
        <div class="pass18-muted">${escapeHtml(reasoning.mission.company ? "Company focus: " + reasoning.mission.company : "Company focus: none")}</div>
        <div class="pass18-muted">${escapeHtml("Mode: " + modeLabel(reasoning.mission.mode))}</div>
      </div>
      <h4>Why this signal won</h4>
      <div class="pass18-card">${whyLines}</div>
      <h4>Agent run log</h4>
      <div class="pass18-card">${stepLines}</div>
      <h4>Truth guardrail</h4>
      <div class="pass18-card">
        <div class="pass18-line"><span class="pass18-dot"></span><span>${escapeHtml(statusClass)}</span></div>
        <div class="pass18-muted">Direct, adjacent, and source-limited states are intentionally visible so the demo does not overclaim.</div>
      </div>
    `;
  }

  function escapeHtml(value) {
    return clean(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function signature(payload) {
    try { return JSON.stringify(payload).slice(0, 8000); }
    catch (err) { return String(Date.now()); }
  }

  const originalFetch = window.fetch;
  if (typeof originalFetch === "function" && !window.__PASS18_FETCH_WRAPPED__) {
    window.__PASS18_FETCH_WRAPPED__ = true;
    window.fetch = function () {
      const args = arguments;
      return originalFetch.apply(this, args).then(function (response) {
        try {
          const url = clean(response && response.url);
          if (url.indexOf("/api/signals") >= 0) {
            response.clone().json().then(function (payload) {
              const sig = signature(payload);
              if (sig !== STATE.lastSignature) {
                STATE.lastSignature = sig;
                STATE.lastPayload = payload;
                STATE.lastSignals = normalize(payload);
                render(STATE.lastSignals);
              }
            }).catch(function () {});
          }
        } catch (err) {}
        return response;
      });
    };
  }

  function pollSignals() {
    const mission = getMission();
    const params = new URLSearchParams({
      query: mission.query || "",
      keyword: mission.query || "",
      q: mission.query || "",
      company: mission.company || "",
      company_focus: mission.company || "",
      mode: mission.mode || "broad_targeted",
      coverage: mission.mode || "broad_targeted",
      source: mission.source || "",
      source_filter: mission.source || "",
      t: String(Date.now())
    });
    fetch("/api/signals?" + params.toString())
      .then(r => r.json())
      .then(payload => {
        const sig = signature(payload);
        if (sig !== STATE.lastSignature) {
          STATE.lastSignature = sig;
          STATE.lastPayload = payload;
          STATE.lastSignals = normalize(payload);
          render(STATE.lastSignals);
        }
      })
      .catch(function () {
        ensurePanel();
      });
  }

  function boot() {
    ensurePanel();
    setTimeout(pollSignals, 700);
    setInterval(pollSignals, 7000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
