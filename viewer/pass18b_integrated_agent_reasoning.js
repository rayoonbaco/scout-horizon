(function () {
  "use strict";

  const CARD_ID = "pass18b-agent-reasoning-card";
  let lastSig = "";

  function clean(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "object") {
      try { return JSON.stringify(value); } catch (err) { return String(value); }
    }
    return String(value).replace(/\s+/g, " ").trim();
  }

  function esc(value) {
    return clean(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function lower(value) { return clean(value).toLowerCase(); }

  function textOf(signal) {
    if (!signal || typeof signal !== "object") return "";
    return Object.keys(signal).map(k => clean(signal[k])).join(" ").toLowerCase();
  }

  function titleOf(signal) {
    if (!signal || typeof signal !== "object") return "No signal selected";
    for (const key of ["title", "headline", "name", "summary", "observation", "text"]) {
      const val = clean(signal[key]);
      if (val) return val;
    }
    return "Untitled signal";
  }

  function sourceOf(signal) {
    if (!signal || typeof signal !== "object") return "current sources";
    for (const key of ["source", "source_name", "publisher", "domain", "url", "link"]) {
      const val = clean(signal[key]);
      if (val) return val;
    }
    return "current sources";
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

  function inputVal(selectors, fallback) {
    for (const sel of selectors) {
      const n = document.querySelector(sel);
      if (n && "value" in n) return clean(n.value);
    }
    return fallback || "";
  }

  function mission() {
    let mode = inputVal(["#scanMode", "[name='mode']", "select"], "broad_targeted");
    const checked = document.querySelector("input[name='mode']:checked, input[name='scan_mode']:checked");
    if (checked) mode = clean(checked.value);
    return {
      query: inputVal(["#topicInput", "#queryInput", "#keywordInput", "[name='query']", "[name='keyword']", "input[placeholder*='Topic' i]", "input[placeholder*='Keyword' i]"], "GLP-1 manufacturing pressure"),
      company: inputVal(["#companyInput", "#companyFocus", "[name='company']", "[name='company_focus']", "input[placeholder*='Company' i]"], ""),
      mode: mode || "broad_targeted",
      source: inputVal(["#sourceInput", "#sourceFilter", "[name='source']", "[name='source_filter']"], "")
    };
  }

  function hasAny(text, terms) { return terms.some(t => text.indexOf(t) >= 0); }

  function modeLabel(mode) {
    const m = lower(mode);
    if (m.indexOf("targeted") >= 0 && m.indexOf("broad") < 0) return "Targeted";
    if (m.indexOf("broad") >= 0 && m.indexOf("targeted") < 0) return "Broad";
    return "Broad + targeted";
  }

  function family(query) {
    const q = lower(query);
    if (hasAny(q, ["cyber", "ot", "cisa", "cve", "kev", "vulnerability"])) return "cyber/OT risk";
    if (hasAny(q, ["glp", "obesity", "semaglutide", "tirzepatide", "injectable"])) return "GLP-1 / injectable manufacturing";
    if (hasAny(q, ["fda", "gmp", "validation", "inspection", "warning"])) return "FDA/GMP validation pressure";
    if (hasAny(q, ["cdmo", "outsourcing", "fill", "finish", "capacity"])) return "CDMO / capacity pressure";
    if (hasAny(q, ["bms", "automation", "commissioning", "facilities"])) return "regulated facilities integration";
    return "life-sciences strategic signal";
  }

  function sourceIsCyber(source) {
    return hasAny(lower(source), ["cisa", "nvd", "cyber", "cve", "kev", "security", "ics", "ot"]);
  }

  function evidence(signal, m) {
    const blob = textOf(signal);
    const q = lower(m.query);
    const reasons = [];
    let direct = false;
    let adjacent = false;

    const lanes = [
      ["cyber/OT", ["cyber", "ot", "cisa", "cve", "kev"], ["cyber", "ot", "cisa", "cve", "kev", "security", "ics", "vulnerability"]],
      ["GLP-1/manufacturing", ["glp", "manufacturing", "injectable"], ["glp", "manufacturing", "capacity", "fill", "finish", "cdmo", "injectable", "sterile", "novo", "lilly"]],
      ["FDA/GMP", ["fda", "gmp", "validation"], ["fda", "gmp", "validation", "inspection", "warning", "compliance", "quality"]],
      ["CDMO/capacity", ["cdmo", "outsourcing", "capacity"], ["cdmo", "outsourcing", "capacity", "supplier", "fill", "finish", "manufacturing"]],
      ["facilities/BMS", ["bms", "automation", "commissioning", "facilities"], ["bms", "building", "facility", "commissioning", "automation", "controls", "environmental"]]
    ];

    lanes.forEach(lane => {
      if (hasAny(q, lane[1])) {
        if (hasAny(blob, lane[2])) {
          direct = true;
          reasons.push("Evidence matches the " + lane[0] + " lane.");
        } else {
          adjacent = true;
          reasons.push("Requested " + lane[0] + " lane is not directly visible in the top signal.");
        }
      }
    });

    if (m.company) {
      const company = lower(m.company);
      const companyHit = blob.indexOf(company) >= 0 ||
        (company === "eli lilly" && blob.indexOf("lilly") >= 0) ||
        (company === "novo nordisk" && blob.indexOf("novo") >= 0);
      if (companyHit) {
        direct = true;
        reasons.push("Company focus appears in the signal evidence.");
      } else {
        adjacent = true;
        reasons.push("Company focus is not directly visible; this should be treated as adjacent unless supporting evidence says otherwise.");
      }
    }

    if (m.source && hasAny(q, ["cyber", "ot"]) && !sourceIsCyber(m.source)) {
      adjacent = true;
      reasons.push("Cyber/OT mission is constrained to a non-cyber source, so source-limited adjacent labeling is appropriate.");
    }

    const truth = lower(clean(signal && (signal.truth_label || signal.strategic_warnings || signal.company_adjacent_only || signal.source_filter_adjacent_only)));
    if (truth.indexOf("adjacent") >= 0 || truth.indexOf("source-limited") >= 0 || truth.indexOf("no direct") >= 0) {
      adjacent = true;
    }

    let status = "Contextual evidence";
    if (direct && adjacent) status = "Mixed direct + adjacent";
    else if (direct) status = "Direct evidence";
    else if (adjacent) status = "Adjacent / source-limited";

    if (!reasons.length) reasons.push("Signal ranked highest after topic, source, and scan-mode weighting.");
    return { status, reasons };
  }

  function findRightPanel() {
    const existing = document.getElementById(CARD_ID);
    if (existing && existing.parentElement) return existing.parentElement;

    const all = Array.from(document.querySelectorAll("section, aside, main, div"));
    const candidates = all.filter(n => {
      const t = clean(n.textContent);
      return t.indexOf("Scout Brief") >= 0 && t.indexOf("Intel Stack") >= 0;
    });
    if (candidates.length) {
      candidates.sort((a, b) => (a.getBoundingClientRect().width || 9999) - (b.getBoundingClientRect().width || 9999));
      return candidates[0];
    }

    const scout = all.find(n => clean(n.textContent).indexOf("Scout Brief") >= 0);
    if (scout) return scout.parentElement || scout;

    return document.body;
  }

  function ensureStyles() {
    if (document.querySelector("style[data-pass18b]")) return;
    const style = document.createElement("style");
    style.setAttribute("data-pass18b", "true");
    style.textContent = `
      #${CARD_ID} {
        border: 1px solid rgba(244, 178, 74, 0.72);
        border-radius: 16px;
        background: rgba(12, 24, 28, 0.82);
        color: #f5f2e8;
        padding: 12px 14px;
        margin: 12px 0;
        box-shadow: 0 14px 32px rgba(0,0,0,.22);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
      }
      #${CARD_ID} .p18b-eyebrow {
        color: #6ee7e0;
        text-transform: uppercase;
        letter-spacing: .08em;
        font-weight: 800;
        font-size: 10px;
        margin-bottom: 3px;
      }
      #${CARD_ID} .p18b-title {
        font-weight: 900;
        font-size: 18px;
        line-height: 1.1;
        margin-bottom: 4px;
      }
      #${CARD_ID} .p18b-sub {
        color: #c8d6d8;
        font-size: 11px;
        margin-bottom: 10px;
      }
      #${CARD_ID} .p18b-box {
        border: 1px solid rgba(103, 231, 224, .22);
        border-radius: 11px;
        background: rgba(0, 18, 24, .45);
        padding: 9px 10px;
        margin-top: 8px;
      }
      #${CARD_ID} .p18b-label {
        color: #72e5ee;
        text-transform: uppercase;
        font-size: 9.5px;
        letter-spacing: .08em;
        font-weight: 800;
        margin-bottom: 5px;
      }
      #${CARD_ID} .p18b-line {
        font-size: 11.5px;
        line-height: 1.35;
        margin: 4px 0;
      }
      #${CARD_ID} .p18b-strong { font-weight: 850; color: #fff4d6; }
      #${CARD_ID} .p18b-muted { color: #c8d6d8; }
    `;
    document.head.appendChild(style);
  }

  function render(signals) {
    ensureStyles();
    const m = mission();
    const top = signals && signals.length ? signals[0] : null;
    const ev = evidence(top, m);
    const parent = findRightPanel();

    let card = document.getElementById(CARD_ID);
    if (!card) {
      card = document.createElement("section");
      card.id = CARD_ID;
      // Place after Scout Brief if possible, before Intel Stack.
      const kids = Array.from(parent.children || []);
      const intel = kids.find(k => clean(k.textContent).indexOf("Intel Stack") >= 0);
      if (intel) parent.insertBefore(card, intel);
      else parent.appendChild(card);
    }

    const runLog = [
      "Interpreted mission as " + family(m.query) + ".",
      "Applied topic / keyword weighting.",
      m.company ? "Applied company focus: " + m.company + "." : "No company focus supplied; scan stays broad.",
      m.source ? "Applied source filter: " + m.source + "." : "Used all available sources.",
      "Applied scan mode: " + modeLabel(m.mode) + ".",
      "Ranked candidate signals and checked direct vs adjacent evidence."
    ];

    card.innerHTML = `
      <div class="p18b-eyebrow">Agent Reasoning</div>
      <div class="p18b-title">Why this signal won</div>
      <div class="p18b-sub">Visible reasoning layer added in Pass 18B.</div>

      <div class="p18b-box">
        <div class="p18b-label">Evidence status</div>
        <div class="p18b-line"><span class="p18b-strong">${esc(ev.status)}</span></div>
        <div class="p18b-line p18b-muted">Top source: ${esc(sourceOf(top))}</div>
      </div>

      <div class="p18b-box">
        <div class="p18b-label">Why selected</div>
        ${ev.reasons.slice(0, 4).map(r => `<div class="p18b-line">• ${esc(r)}</div>`).join("")}
      </div>

      <div class="p18b-box">
        <div class="p18b-label">Agent run log</div>
        ${runLog.map((r, i) => `<div class="p18b-line"><span class="p18b-strong">${i + 1}.</span> ${esc(r)}</div>`).join("")}
      </div>
    `;
  }

  function sig(payload) {
    try { return JSON.stringify(payload).slice(0, 8000); }
    catch (err) { return String(Date.now()); }
  }

  function poll() {
    const m = mission();
    const params = new URLSearchParams({
      query: m.query || "",
      keyword: m.query || "",
      q: m.query || "",
      company: m.company || "",
      company_focus: m.company || "",
      mode: m.mode || "broad_targeted",
      coverage: m.mode || "broad_targeted",
      source: m.source || "",
      source_filter: m.source || "",
      t: String(Date.now())
    });
    fetch("/api/signals?" + params.toString())
      .then(r => r.json())
      .then(payload => {
        const s = sig(payload);
        if (s !== lastSig) {
          lastSig = s;
          render(normalize(payload));
        }
      })
      .catch(() => {
        ensureStyles();
        findRightPanel();
      });
  }

  const originalFetch = window.fetch;
  if (typeof originalFetch === "function" && !window.__PASS18B_FETCH_WRAPPED__) {
    window.__PASS18B_FETCH_WRAPPED__ = true;
    window.fetch = function () {
      return originalFetch.apply(this, arguments).then(response => {
        try {
          const url = clean(response && response.url);
          if (url.indexOf("/api/signals") >= 0) {
            response.clone().json().then(payload => {
              const s = sig(payload);
              if (s !== lastSig) {
                lastSig = s;
                render(normalize(payload));
              }
            }).catch(() => {});
          }
        } catch (err) {}
        return response;
      });
    };
  }

  function boot() {
    poll();
    setInterval(poll, 7000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
