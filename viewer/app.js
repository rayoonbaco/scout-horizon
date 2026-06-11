(() => {
  const state = {
    signals: [],
    filteredSignals: [],
    selectedId: null,
    pollingUntil: 0,
    lastJsError: "",
    apiState: null,
    controlsReady: false,
    meta: null,
    clientFilters: {
      decisionLens: "all",
      timeWindow: "all",
      region: "all",
      accountFocus: "all",
      accountName: "all",
      serviceLine: "all",
      lane: "all",
      regulator: "all",
      source: "all",
      signalType: "all",
      minScore: "0",
      minConfidence: "0",
      minPriority: "0",
      freeText: "",
      sortBy: "priority_desc"
    }
  };

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

  window.onerror = function(message, source, lineno, colno) {
    state.lastJsError = `${message} @ ${source || "unknown"}:${lineno || 0}:${colno || 0}`;
    updateDiagnostics();
  };

  function banner(text, kind = "warn") {
    const el = $("statusBanner");
    el.className = `banner ${kind}`;
    el.textContent = text;
  }

  function selectedTargetNames() {
    return Array.from($("webSourceTargets").selectedOptions || []).map(option => option.value);
  }

  function forceEditable(id) {
    const el = $(id);
    if (!el) return;
    el.disabled = false;
    el.readOnly = false;
    el.removeAttribute("readonly");
    el.removeAttribute("disabled");
    el.style.pointerEvents = "auto";
    el.style.userSelect = "text";
    el.style.webkitUserSelect = "text";
  }

  function requestBody() {
    return {
      keyword: $("webKeyword").value || "",
      company: $("webCompany").value || "",
      mode: $("webMode").value || "broad_and_targeted",
      sources: selectedTargetNames(),
      max_results_per_query: 6
    };
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, {
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      ...options
    });
    const text = await response.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { raw: text };
    }
    if (!response.ok) throw new Error(data.detail || data.message || text || `${response.status}`);
    return data;
  }

  function coerceNumber(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
  }

  function cleanText(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function norm(value) {
    return cleanText(value).toLowerCase();
  }

  function asArray(value) {
    if (Array.isArray(value)) return value.filter(Boolean);
    if (value == null || value === "" || value === "—") return [];
    return String(value).split(/[;,|]/).map(part => cleanText(part)).filter(Boolean);
  }

  function uniqueSorted(values) {
    return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b));
  }

  function formatDecimal(num) {
    return coerceNumber(num).toFixed(2);
  }

  function formatPercentish(num) {
    return coerceNumber(num).toFixed(2);
  }

  function formatDate(value) {
    const raw = cleanText(value);
    if (!raw) return "Unknown";
    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) return raw;
    return parsed.toLocaleString();
  }

  function timeValue(signal) {
    const raw = signal.latest_event_time_utc || signal.published || signal.earliest_event_time_utc || signal.time || "";
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime();
  }

  function signalTypeOf(signal) {
    return cleanText(
      signal.signal_type ||
      signal.type ||
      signal.event_type ||
      signal.lane ||
      "general"
    );
  }

  function accountNamesOf(signal) {
    return uniqueSorted([
      ...asArray(signal.account_name),
      ...asArray(signal.account_names),
      ...asArray(signal.accounts),
      ...asArray(signal.facets?.accounts)
    ]);
  }

  function serviceLinesOf(signal) {
    return uniqueSorted([
      ...asArray(signal.service_line),
      ...asArray(signal.service_lines),
      ...asArray(signal.facets?.service_lines)
    ]);
  }

  function regionsOf(signal) {
    return uniqueSorted([
      ...asArray(signal.region),
      ...asArray(signal.regions),
      ...asArray(signal.operating_region),
      ...asArray(signal.operating_regions),
      ...asArray(signal.facets?.operating_regions)
    ]);
  }

  function regulatorsOf(signal) {
    return uniqueSorted([
      ...asArray(signal.regulator),
      ...asArray(signal.regulators),
      ...asArray(signal.facets?.regulators)
    ]);
  }

  function sourceTypesOf(signal) {
    return uniqueSorted([
      cleanText(signal.source),
      cleanText(signal.sources),
      cleanText(signal.source_domain),
      ...asArray(signal.facets?.source_types)
    ]);
  }

  function accountTypeOf(signal) {
    return cleanText(signal.account_type || signal.facets?.account_types?.[0] || "other") || "other";
  }

  function scoreOf(signal) {
    return coerceNumber(signal.score ?? signal.priority_score ?? 0);
  }

  function priorityOf(signal) {
    return coerceNumber(signal.priority_score ?? signal.score ?? 0);
  }

  function confidenceOf(signal) {
    return coerceNumber(signal.confidence ?? signal.confidence_score ?? 0);
  }

  function observationOf(signal) {
    return cleanText(signal.observation || signal.summary || signal.snippet || "");
  }

  function recommendationOf(signal) {
    return cleanText(signal.recommended_action || signal.recommendation || "");
  }

  // PASS 9 - readiness lane support
  function readinessLaneOf(signal) {
    return cleanText(signal.pressure_or_opportunity_lane || signal.opportunity_lane || signal.readiness_lane || "");
  }

  function tagsOf(signal) {
    return uniqueSorted([
      cleanText(signal.lane),
      signalTypeOf(signal),
      accountTypeOf(signal),
      ...regionsOf(signal),
      ...serviceLinesOf(signal),
      ...regulatorsOf(signal),
      ...sourceTypesOf(signal),
      ...accountNamesOf(signal),
      ...asArray(signal.tags),
      ...asArray(signal.facets?.modalities),
      ...asArray(signal.facets?.deal_stages),
      ...asArray(signal.facets?.partnerships)
    ].filter(Boolean));
  }

  function textBlob(signal) {
    return norm([
      signal.title,
      signal.source,
      signal.source_domain,
      signal.lane,
      signalTypeOf(signal),
      observationOf(signal),
      signal.why_it_matters,
      recommendationOf(signal),
      signal.internal_corroboration,
      accountTypeOf(signal),
      accountNamesOf(signal).join(" "),
      serviceLinesOf(signal).join(" "),
      regionsOf(signal).join(" "),
      regulatorsOf(signal).join(" "),
      tagsOf(signal).join(" ")
    ].join(" "));
  }

  function deriveSignal(signal) {
    return {
      ...signal,
      _timeValue: timeValue(signal),
      _signalType: signalTypeOf(signal),
      _accounts: accountNamesOf(signal),
      _serviceLines: serviceLinesOf(signal),
      _regions: regionsOf(signal),
      _regulators: regulatorsOf(signal),
      _sourceTypes: sourceTypesOf(signal),
      _accountType: accountTypeOf(signal),
      _score: scoreOf(signal),
      _priority: priorityOf(signal),
      _confidence: confidenceOf(signal),
      _observation: observationOf(signal),
      _recommendation: recommendationOf(signal),
      _readinessLane: readinessLaneOf(signal),
      _tags: tagsOf(signal),
      _textBlob: textBlob(signal)
    };
  }

  async function loadTargets() {
    const data = await fetchJson("/api/targets");
    const box = $("webSourceTargets");
    box.innerHTML = "";
    (data.targets || []).forEach(target => {
      const option = document.createElement("option");
      option.value = target.name;
      option.textContent = target.name;
      box.appendChild(option);
    });
  }

  function applyStateToForm(apiState) {
    const s = apiState.state || {};
    $("webKeyword").value = s.keyword || "";
    $("webCompany").value = s.company || "";
    $("webMode").value = s.mode || "broad_and_targeted";
    const wanted = new Set(s.sources || []);
    Array.from($("webSourceTargets").options || []).forEach(opt => {
      opt.selected = wanted.has(opt.value);
    });
    $("kpiAction").textContent = apiState.last_action || "Ready";
    $("kpiMode").textContent = apiState.last_mode_used || "—";
    $("kpiActionSub").textContent = apiState.last_updated ? `Updated ${formatDate(apiState.last_updated)}` : "stable workflow preserved";
    $("kpiModeSub").textContent = apiState.last_error ? `Last error: ${apiState.last_error}` : "ingest engine mode";
    updateDiagnostics(apiState);
    const kind = apiState.last_error ? "err" : ((apiState.last_action || "").includes("Added") ? "ok" : "warn");
    banner(
      `${apiState.last_action || "Ready"}${apiState.last_updated ? ` - ${formatDate(apiState.last_updated)}` : ""}${apiState.last_error ? ` - ${apiState.last_error}` : ""}`,
      kind
    );
  }

  function updateDiagnostics(apiState = null) {
    if (apiState) {
      $("diagBase").textContent = `Server base URL: ${apiState.base_url || "current hosted app"}`;
      $("diagFetch").textContent = `Last state fetch time: ${new Date().toLocaleString()}`;
      $("diagCount").textContent = `Loaded signals count: ${apiState.signals_count ?? state.signals.length}`;
      $("diagVersion").textContent = `Viewer version: ${apiState.version || "unknown"}`;
    } else {
      $("diagFetch").textContent = `Last state fetch time: ${new Date().toLocaleString()}`;
      $("diagCount").textContent = `Loaded signals count: ${state.signals.length}`;
    }
    $("diagFiltered").textContent = `Filtered signals shown: ${state.filteredSignals.length}`;
    $("diagError").textContent = `Last JS error: ${state.lastJsError || "none"}`;
  }

  function fillSelect(id, values, defaultLabel = "All") {
    const select = $(id);
    const previous = select.value;
    select.innerHTML = "";
    const allOpt = document.createElement("option");
    allOpt.value = "all";
    allOpt.textContent = defaultLabel;
    select.appendChild(allOpt);
    values.forEach(value => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value;
      select.appendChild(opt);
    });
    select.value = values.includes(previous) ? previous : "all";
  }

  function fillThresholdSelect(id) {
    const select = $(id);
    const prev = select.value;
    const options = [0, 0.25, 0.5, 0.6, 0.7, 0.8, 0.9];
    select.innerHTML = "";
    options.forEach(value => {
      const opt = document.createElement("option");
      opt.value = String(value);
      opt.textContent = value === 0 ? "Any" : `${value.toFixed(2)}+`;
      select.appendChild(opt);
    });
    select.value = options.map(String).includes(prev) ? prev : "0";
  }

  function populateDecisionLens() {
    const select = $("decisionLens");
    const previous = select.value;
    const options = [
      ["all", "All lenses"],
      ["growth", "Growth / pursuit"],
      ["risk", "Risk / protect"],
      ["regulatory", "Regulatory / compliance"],
      ["cyber", "Cyber / resilience"],
      ["partnerships", "Partnerships / M&A"],
      ["accounts", "Account moves"],
      ["capacity", "Capacity / site activity"]
    ];
    select.innerHTML = "";
    options.forEach(([value, label]) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
      select.appendChild(opt);
    });
    select.value = options.some(([value]) => value === previous) ? previous : "all";
  }

  function populateTimeWindow() {
    const select = $("timeWindow");
    const previous = select.value;
    const options = [
      ["all", "Any time"],
      ["7d", "Last 7 days"],
      ["30d", "Last 30 days"],
      ["90d", "Last 90 days"],
      ["365d", "Last 365 days"]
    ];
    select.innerHTML = "";
    options.forEach(([value, label]) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
      select.appendChild(opt);
    });
    select.value = options.some(([value]) => value === previous) ? previous : "all";
  }

  function buildMeta(items) {
    const meta = {
      regions: uniqueSorted(items.flatMap(item => item._regions)),
      accountNames: uniqueSorted(items.flatMap(item => item._accounts)),
      serviceLines: uniqueSorted(items.flatMap(item => item._serviceLines)),
      lanes: uniqueSorted(items.map(item => cleanText(item.lane)).filter(Boolean)),
      regulators: uniqueSorted(items.flatMap(item => item._regulators)),
      sources: uniqueSorted(items.flatMap(item => item._sourceTypes)),
      signalTypes: uniqueSorted(items.map(item => item._signalType).filter(Boolean)),
      accountTypes: uniqueSorted(items.map(item => item._accountType).filter(Boolean))
    };
    state.meta = meta;
    return meta;
  }

  function populateFilterControls(items) {
    const meta = buildMeta(items);
    populateDecisionLens();
    populateTimeWindow();
    fillSelect("filterRegion", meta.regions, "All regions");
    fillSelect("filterAccountFocus", meta.accountTypes, "All account focus");
    fillSelect("filterAccountName", meta.accountNames, "All accounts");
    fillSelect("filterServiceLine", meta.serviceLines, "All service lines");
    fillSelect("filterLane", meta.lanes, "All lanes");
    fillSelect("filterRegulator", meta.regulators, "All regulators");
    fillSelect("filterSource", meta.sources, "All sources");
    fillSelect("filterSignalType", meta.signalTypes, "All signal types");
    fillThresholdSelect("minScore");
    fillThresholdSelect("minConfidence");
    fillThresholdSelect("minPriority");
    renderQuickChips(meta);
  }

  function renderQuickChips(meta) {
    const box = $("quickChips");
    const chips = [
      { label: "Top priority", onClick: () => { $("minPriority").value = "0.7"; syncClientFiltersFromControls(); applyClientFilters(); } },
      { label: "High confidence", onClick: () => { $("minConfidence").value = "0.7"; syncClientFiltersFromControls(); applyClientFilters(); } },
      { label: "Cyber", onClick: () => { $("decisionLens").value = "cyber"; syncClientFiltersFromControls(); applyClientFilters(); } },
      { label: "Regulatory", onClick: () => { $("decisionLens").value = "regulatory"; syncClientFiltersFromControls(); applyClientFilters(); } },
      { label: "Growth", onClick: () => { $("decisionLens").value = "growth"; syncClientFiltersFromControls(); applyClientFilters(); } },
      { label: "Last 30 days", onClick: () => { $("timeWindow").value = "30d"; syncClientFiltersFromControls(); applyClientFilters(); } }
    ];
    if ((meta.regions || []).length) {
      chips.push({ label: `Region: ${meta.regions[0]}`, onClick: () => { $("filterRegion").value = meta.regions[0]; syncClientFiltersFromControls(); applyClientFilters(); } });
    }
    box.innerHTML = "";
    chips.forEach(chip => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chipBtn";
      btn.textContent = chip.label;
      btn.addEventListener("click", chip.onClick);
      box.appendChild(btn);
    });
  }

  function syncClientFiltersFromControls() {
    state.clientFilters = {
      decisionLens: $("decisionLens").value || "all",
      timeWindow: $("timeWindow").value || "all",
      region: $("filterRegion").value || "all",
      accountFocus: $("filterAccountFocus").value || "all",
      accountName: $("filterAccountName").value || "all",
      serviceLine: $("filterServiceLine").value || "all",
      lane: $("filterLane").value || "all",
      regulator: $("filterRegulator").value || "all",
      source: $("filterSource").value || "all",
      signalType: $("filterSignalType").value || "all",
      minScore: $("minScore").value || "0",
      minConfidence: $("minConfidence").value || "0",
      minPriority: $("minPriority").value || "0",
      freeText: $("filterText").value || "",
      sortBy: $("sortBy").value || "priority_desc"
    };
  }

  function decisionLensMatch(signal, lens) {
    if (lens === "all") return true;
    const hay = signal._textBlob;
    const lane = norm(signal.lane);
    const accountType = norm(signal._accountType);
    if (lens === "growth") return /expansion|growth|investment|facility|capacity|partner|pursuit|award|grant|build|launch|hiring/.test(hay) || ["capital_projects", "m_and_a", "partnerships"].includes(lane) || accountType === "client";
    if (lens === "risk") return /risk|warning|recall|shortage|inspection|vulnerability|breach|threat|watch|delay|disruption/.test(hay) || accountType === "competitor" || accountType === "watch";
    if (lens === "regulatory") return /fda|ema|warning letter|inspection|gmp|compliance|consent decree|483|regulatory/.test(hay) || lane === "regulatory";
    if (lens === "cyber") return /cve|kev|cyber|vulnerability|patch|exploit|ot|ics|security/.test(hay) || lane === "cybersecurity";
    if (lens === "partnerships") return /partnership|collaboration|acquisition|merger|license|deal/.test(hay) || lane === "m_and_a" || lane === "partnerships";
    if (lens === "accounts") return signal._accounts.length > 0 || ["client", "competitor", "watch"].includes(accountType);
    if (lens === "capacity") return /site|plant|facility|manufacturing|capacity|expansion|construction|capex/.test(hay) || lane === "capital_projects";
    return true;
  }

  function timeWindowMatch(signal, windowKey) {
    if (windowKey === "all") return true;
    if (!signal._timeValue) return false;
    const days = { "7d": 7, "30d": 30, "90d": 90, "365d": 365 }[windowKey];
    if (!days) return true;
    return signal._timeValue >= Date.now() - days * 24 * 60 * 60 * 1000;
  }

  function includesValue(values, wanted) {
    return wanted === "all" || values.map(norm).includes(norm(wanted));
  }

  function clientFilter(signal) {
    const f = state.clientFilters;
    if (!decisionLensMatch(signal, f.decisionLens)) return false;
    if (!timeWindowMatch(signal, f.timeWindow)) return false;
    if (!includesValue(signal._regions, f.region)) return false;
    if (f.accountFocus !== "all" && norm(signal._accountType) !== norm(f.accountFocus)) return false;
    if (!includesValue(signal._accounts, f.accountName)) return false;
    if (!includesValue(signal._serviceLines, f.serviceLine)) return false;
    if (f.lane !== "all" && norm(signal.lane) !== norm(f.lane)) return false;
    if (!includesValue(signal._regulators, f.regulator)) return false;
    if (!includesValue(signal._sourceTypes, f.source)) return false;
    if (f.signalType !== "all" && norm(signal._signalType) !== norm(f.signalType)) return false;
    if (signal._score < coerceNumber(f.minScore)) return false;
    if (signal._confidence < coerceNumber(f.minConfidence)) return false;
    if (signal._priority < coerceNumber(f.minPriority)) return false;
    if (norm(f.freeText) && !signal._textBlob.includes(norm(f.freeText))) return false;
    return true;
  }

  function compareSignals(a, b) {
    const sortBy = state.clientFilters.sortBy;
    if (sortBy === "confidence_desc") return b._confidence - a._confidence || b._priority - a._priority;
    if (sortBy === "score_desc") return b._score - a._score || b._priority - a._priority;
    if (sortBy === "newest") return b._timeValue - a._timeValue || b._priority - a._priority;
    if (sortBy === "oldest") return a._timeValue - b._timeValue || b._priority - a._priority;
    if (sortBy === "title_asc") return cleanText(a.title).localeCompare(cleanText(b.title));
    return b._priority - a._priority || b._confidence - a._confidence || b._timeValue - a._timeValue;
  }

  function facetSummaryItems(filtered) {
    const active = [];
    const f = state.clientFilters;
    const push = (label, value, key, resetTo = "all") => {
      if (value && value !== "all" && value !== "0") active.push({ label: `${label}: ${value}`, key, resetTo });
    };
    push("Lens", f.decisionLens, "decisionLens");
    push("Window", f.timeWindow, "timeWindow");
    push("Region", f.region, "filterRegion");
    push("Focus", f.accountFocus, "filterAccountFocus");
    push("Account", f.accountName, "filterAccountName");
    push("Service", f.serviceLine, "filterServiceLine");
    push("Lane", f.lane, "filterLane");
    push("Regulator", f.regulator, "filterRegulator");
    push("Source", f.source, "filterSource");
    push("Type", f.signalType, "filterSignalType");
    if (f.minScore !== "0") active.push({ label: `Score ≥ ${f.minScore}`, key: "minScore", resetTo: "0" });
    if (f.minConfidence !== "0") active.push({ label: `Confidence ≥ ${f.minConfidence}`, key: "minConfidence", resetTo: "0" });
    if (f.minPriority !== "0") active.push({ label: `Priority ≥ ${f.minPriority}`, key: "minPriority", resetTo: "0" });
    if (f.freeText) active.push({ label: `Search: ${f.freeText}`, key: "filterText", resetTo: "" });
    const box = $("facetChips");
    box.innerHTML = "";
    active.forEach(item => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chipBtn active";
      btn.textContent = `${item.label} ×`;
      btn.addEventListener("click", () => {
        $(item.key).value = item.resetTo;
        syncClientFiltersFromControls();
        applyClientFilters();
      });
      box.appendChild(btn);
    });
    if (!active.length && filtered.length) {
      const span = document.createElement("span");
      span.className = "labelPill";
      span.textContent = "Showing all loaded signals";
      box.appendChild(span);
    }
  }

  function countBy(items, getValues) {
    const map = new Map();
    items.forEach(item => {
      const values = getValues(item);
      const list = Array.isArray(values) ? values : [values];
      list.filter(Boolean).forEach(value => map.set(value, (map.get(value) || 0) + 1));
    });
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]).slice(0, 5);
  }

  function renderSmallList(id, rows, valueFormatter = value => value) {
    const box = $(id);
    box.innerHTML = "";
    if (!rows.length) {
      box.innerHTML = '<div class="empty">No data in current selection.</div>';
      return;
    }
    rows.forEach(([label, count]) => {
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `<span>${esc(label)}</span><strong>${esc(valueFormatter(count))}</strong>`;
      box.appendChild(row);
    });
  }

  function renderSnapshotList(id, items, emptyText) {
    const box = $(id);
    box.innerHTML = "";
    if (!items.length) {
      box.innerHTML = `<div class="empty">${esc(emptyText)}</div>`;
      return;
    }
    items.forEach(item => {
      const div = document.createElement("div");
      div.className = "snapshotRow";
      div.innerHTML = `<span>${esc(item.label)}</span><strong>${esc(item.value)}</strong>`;
      box.appendChild(div);
    });
  }


  function setText(id, text) {
    const el = $(id);
    if (el) el.textContent = text;
  }

  function shortTitle(signal) {
    const title = cleanText(signal?.title || "Untitled signal");
    return title.length > 92 ? `${title.slice(0, 89)}...` : title;
  }

  function highestPrioritySignal(items) {
    return [...items].sort((a, b) => (b._priority - a._priority) || (b._confidence - a._confidence) || (b._score - a._score))[0];
  }

  function pressureLabel(avgPriority, highCount, total) {
    if (!total) return "No pressure on the field yet.";
    if (avgPriority >= 0.72 || highCount >= 3) return "High: leadership should review the top signals before the next planning conversation.";
    if (avgPriority >= 0.48 || highCount >= 1) return "Moderate: enough signal exists to create a focused follow-up list.";
    return "Low: useful background scan, but no urgent executive escalation in this filtered view.";
  }

  function renderScoutBrief(filtered) {
    const total = filtered.length;
    if (!total) {
      setText("briefWhatChanged", "No signals match the current watch filters.");
      setText("briefWhyMatters", "Broaden the filters to rebuild the field view.");
      setText("briefDecisionPressure", "No pressure on the field yet.");
      setText("briefNextReview", "Clear filters, then review the strongest active signal first.");
      return;
    }
    const top = highestPrioritySignal(filtered);
    const avgPriority = filtered.reduce((sum, item) => sum + item._priority, 0) / total;
    const avgConfidence = filtered.reduce((sum, item) => sum + item._confidence, 0) / total;
    const highPriority = filtered.filter(item => item._priority >= 0.7).length;
    const topLane = countBy(filtered, item => cleanText(item.lane || item._signalType || "general"))[0]?.[0] || "mixed lanes";
    const topRegion = countBy(filtered, item => item._regions.length ? item._regions : ["unspecified region"])[0]?.[0] || "unspecified region";
    const why = cleanText(top.why_it_matters || top._observation || "The current view contains signals that may affect planning, prioritization, or leadership attention.");
    const action = cleanText(top._recommendation || "Open the lead signal, verify the source, and decide whether it belongs in the next executive review.");

    setText("briefWhatChanged", `${total} signal${total === 1 ? "" : "s"} in view. Top item: ${shortTitle(top)}`);
    setText("briefWhyMatters", `${topLane} is the hottest lane; ${topRegion} is the strongest visible terrain. ${why}`.slice(0, 230));
    setText("briefDecisionPressure", `${pressureLabel(avgPriority, highPriority, total)} Avg priority ${formatDecimal(avgPriority)}; confidence ${formatDecimal(avgConfidence)}.`);
    setText("briefNextReview", action.slice(0, 220));
  }

  function renderExecutiveSnapshot(filtered) {
    $("kpiSignals").textContent = String(filtered.length);
    $("kpiSignalsSub").textContent = `of ${state.signals.length} loaded`;
    const avgPriority = filtered.length ? filtered.reduce((sum, item) => sum + item._priority, 0) / filtered.length : 0;
    const avgConfidence = filtered.length ? filtered.reduce((sum, item) => sum + item._confidence, 0) / filtered.length : 0;
    $("kpiPriority").textContent = formatDecimal(avgPriority);
    $("kpiConfidence").textContent = formatDecimal(avgConfidence);

    const growthCandidates = filtered
      .filter(item => decisionLensMatch(item, "growth"))
      .slice(0, 3)
      .map(item => ({ label: cleanText(item.title || "Untitled"), value: `${cleanText(item.lane || item._signalType || "signal")} · ${formatPercentish(item._priority)}` }));
    const riskCandidates = filtered
      .filter(item => decisionLensMatch(item, "risk"))
      .slice(0, 3)
      .map(item => ({ label: cleanText(item.title || "Untitled"), value: `${cleanText(item.lane || item._signalType || "signal")} · ${formatPercentish(item._priority)}` }));

    renderSnapshotList("growthSummary", growthCandidates, "No clear growth themes in current selection.");
    renderSnapshotList("riskSummary", riskCandidates, "No clear risk themes in current selection.");
    renderSmallList("laneMix", countBy(filtered, item => cleanText(item.lane || item._signalType || "general")));
    renderSmallList("regionMix", countBy(filtered, item => item._regions.length ? item._regions : ["Unspecified"]));
    renderSmallList("accountMix", countBy(filtered, item => item._accounts.length ? item._accounts : [item._accountType || "Unspecified"]));
    renderScoutBrief(filtered);

    const now = Date.now();
    const changes = [
      { label: "New in last 7 days", value: String(filtered.filter(item => item._timeValue && item._timeValue >= now - 7 * 86400000).length) },
      { label: "High-priority signals", value: String(filtered.filter(item => item._priority >= 0.7).length) },
      { label: "Corroborated signals", value: String(filtered.filter(item => cleanText(item.internal_corroboration) && !/none detected/i.test(item.internal_corroboration)).length) }
    ];
    renderSnapshotList("changeSummary", changes, "No change indicators available.");
  }

  function renderSignals() {
    const list = $("signalsList");
    list.innerHTML = "";
    const filtered = state.filteredSignals;
    if (!filtered.length) {
      list.innerHTML = '<div class="empty">No signals match the current scout filters.</div>';
      $("signalDetail").innerHTML = '<div class="empty">Select a signal from the watchlist.</div>';
      updateDiagnostics();
      renderExecutiveSnapshot(filtered);
      facetSummaryItems(filtered);
      $("resultsMeta").textContent = `0 shown · sorted by ${$("sortBy").selectedOptions[0]?.textContent || "priority"}`;
      return;
    }

    let selected = filtered.find(item => item.id === state.selectedId) || filtered[0];
    state.selectedId = selected.id;

    filtered.forEach(signal => {
      const div = document.createElement("div");
      div.className = `item${signal.id === state.selectedId ? " active" : ""}`;
      const chips = [
        signal.lane,
        signal._regions[0],
        signal._accounts[0],
        signal._serviceLines[0]
      ].filter(Boolean).slice(0, 4).map(value => `<span class="labelPill">${esc(value)}</span>`).join("");

      div.innerHTML = `
        <div class="itemTop">
          <div style="min-width:0; flex:1;">
            <div class="title">${esc(signal.title || "Untitled")}</div>
            <div class="meta">${esc(signal.source || signal.sources || signal.source_domain || "source unknown")} · ${esc(formatDate(signal.latest_event_time_utc || signal.published || signal.time || ""))}</div>
          </div>
          <div class="badges">
            <span class="badge score">Score ${esc(formatPercentish(signal._score))}</span>
            <span class="badge conf">Conf ${esc(formatPercentish(signal._confidence))}</span>
            <span class="badge priority">Pri ${esc(formatPercentish(signal._priority))}</span>
          </div>
        </div>
        <div class="preview">${esc((signal._observation || "").slice(0, 220))}</div>
        <div class="signalChips" style="margin-top:8px;">${chips}</div>
      `;
      div.addEventListener("click", () => {
        state.selectedId = signal.id;
        renderSignals();
      });
      list.appendChild(div);
    });

    renderDetail(selected);
    renderExecutiveSnapshot(filtered);
    facetSummaryItems(filtered);
    $("resultsMeta").textContent = `${filtered.length} shown of ${state.signals.length} loaded · sorted by ${$("sortBy").selectedOptions[0]?.textContent || "priority"}`;
    updateDiagnostics();
  }

  function detailLabelChips(signal) {
    return [
      signal.lane,
      signal._signalType,
      signal._accountType,
      ...signal._regions,
      ...signal._accounts,
      ...signal._serviceLines,
      ...signal._regulators,
      ...signal._sourceTypes.slice(0, 2)
    ].filter(Boolean).slice(0, 16).map(value => `<span class="labelPill">${esc(value)}</span>`).join("");
  }

  function renderSignalMetaList(signal) {
    const rows = [
      ["Source", cleanText(signal.source || signal.sources || signal.source_domain || "Unknown")],
      ["Observed", formatDate(signal.latest_event_time_utc || signal.published || signal.time || "")],
      ["Lane", cleanText(signal.lane || "—")],
      ["Signal type", cleanText(signal._signalType || "—")],
      ["Signal focus", cleanText(signal._accountType || "—")],
      ["Score", formatPercentish(signal._score)],
      ["Confidence", formatPercentish(signal._confidence)],
      ["Priority", formatPercentish(signal._priority)]
    ];
    return rows.map(([label, value]) => `<div class="snapshotRow"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
  }

  function renderDetail(signal) {
    if (!signal) {
      $("signalDetail").innerHTML = '<div class="empty">Select a signal from the watchlist.</div>';
      return;
    }
    const accounts = signal._accounts.length ? signal._accounts.join(", ") : "Unspecified";
    const services = signal._serviceLines.length ? signal._serviceLines.join(", ") : "Unspecified";
    const regions = signal._regions.length ? signal._regions.join(", ") : "Unspecified";
    const regulators = signal._regulators.length ? signal._regulators.join(", ") : "Unspecified";
    const corroboration = cleanText(signal.internal_corroboration || "None detected in the current window.");
    const why = cleanText(signal.why_it_matters || "No why-it-matters note available.");
    const recommendation = cleanText(signal._recommendation || "No recommended action available.");
    const readinessLane = cleanText(signal._readinessLane || "No readiness lane available.");
    const link = cleanText(signal.url || signal.references?.[0]?.url || "");
    const refs = Array.isArray(signal.references) ? signal.references.filter(ref => ref?.url).slice(0, 4) : [];
    const scoring = `Score ${formatPercentish(signal._score)} · Confidence ${formatPercentish(signal._confidence)} · Priority ${formatPercentish(signal._priority)}`;

    $("signalDetail").innerHTML = `
      <div class="detailHeader">
        <h2>${esc(signal.title || "Untitled")}</h2>
        <div class="chipRow">${detailLabelChips(signal)}</div>
      </div>

      <div class="detailGrid" style="margin-top:12px;">
        <div>
          <div class="detailHead">Executive context</div>
          <div class="snapshotList">${renderSignalMetaList(signal)}</div>
        </div>
        <div>
          <div class="detailHead">Coverage labels</div>
          <div class="snapshotList">
            <div class="snapshotRow"><span>Organization / source focus</span><strong>${esc(accounts)}</strong></div>
            <div class="snapshotRow"><span>Operating region(s)</span><strong>${esc(regions)}</strong></div>
            <div class="snapshotRow"><span>Service line(s)</span><strong>${esc(services)}</strong></div>
            <div class="snapshotRow"><span>Regulator(s)</span><strong>${esc(regulators)}</strong></div>
          </div>
        </div>
      </div>

      <div class="detailSection">
        <div class="detailHead">Observation</div>
        <div class="detailBody">${esc(signal._observation || "No observation available.")}</div>
      </div>
      <div class="detailSection">
        <div class="detailHead">Why it matters</div>
        <div class="detailBody">${esc(why)}</div>
      </div>
      <div class="detailSection">
        <div class="detailHead">Pressure / opportunity lane</div>
        <div class="detailBody">${esc(readinessLane)}</div>
      </div>
      <div class="detailSection">
        <div class="detailHead">Recommended next move</div>
        <div class="detailBody">${esc(recommendation)}</div>
      </div>
      <div class="detailSection">
        <div class="detailHead">Internal corroboration</div>
        <div class="detailBody">${esc(corroboration)}</div>
      </div>
      <div class="detailSection">
        <div class="detailHead">Scoring explanation</div>
        <div class="detailBody">${esc(scoring)}. Higher priority and confidence float to the top; the list sort can be changed to score, confidence, date, or title.</div>
      </div>
      <div class="detailSection">
        <div class="detailHead">Facets / tags</div>
        <div class="detailBody"><div class="chipRow">${signal._tags.slice(0, 24).map(tag => `<span class="labelPill">${esc(tag)}</span>`).join("") || '<span class="muted">No tags available.</span>'}</div></div>
      </div>
      <div class="detailSection">
        <div class="detailHead">Link out</div>
        <div class="detailBody">${link ? `<a href="${esc(link)}" target="_blank" rel="noopener">${esc(link)}</a>` : 'No external link available.'}</div>
      </div>
      ${refs.length ? `<div class="detailSection"><div class="detailHead">Related references</div><div class="detailBody">${refs.map(ref => `<div style="margin-bottom:6px;"><a href="${esc(ref.url)}" target="_blank" rel="noopener">${esc(ref.label || ref.url)}</a></div>`).join("")}</div></div>` : ""}
    `;
  }

  function applyClientFilters() {
    syncClientFiltersFromControls();
    state.filteredSignals = state.signals.filter(clientFilter).sort(compareSignals);
    renderSignals();
  }

  async function refreshStateAndSignals() {
    const [apiState, apiSignals] = await Promise.all([fetchJson("/api/state"), fetchJson("/api/signals")]);
    state.apiState = apiState;
    applyStateToForm(apiState);
    state.signals = (apiSignals.items || []).filter(item => item && typeof item === "object").map(deriveSignal);
    $("kpiAdded").textContent = String(((apiState.last_action || "").match(/Added (\d+)/) || [0, 0])[1]);
    $("kpiAddedSub").textContent = apiState.last_updated ? `Last update ${formatDate(apiState.last_updated)}` : "new items in latest ingest";
    if (!state.controlsReady) {
      populateFilterControls(state.signals);
      wireExecutiveModeControls();
      state.controlsReady = true;
    } else {
      populateFilterControls(state.signals);
    }
    applyClientFilters();
  }

  function startPolling(seconds = 20) {
    state.pollingUntil = Date.now() + seconds * 1000;
  }

  async function pollLoop() {
    try {
      await refreshStateAndSignals();
    } catch (error) {
      banner(`Could not refresh viewer: ${error.message}`, "err");
      state.lastJsError = error.message;
      updateDiagnostics();
    }
    const active = Date.now() < state.pollingUntil;
    setTimeout(pollLoop, active ? 2000 : 10000);
  }

  async function postAndTrack(url, body, progressText) {
    banner(progressText, "warn");
    startPolling(25);
    const data = await fetchJson(url, { method: "POST", body: body ? JSON.stringify(body) : null });
    banner(data.message || "Done.", "ok");
    await refreshStateAndSignals();
    return data;
  }

  async function loadGoogleStatus() {
    try {
      const data = await fetchJson("/api/webassist/config");
      $("cfgStatus").textContent = data.message || "Google status loaded.";
    } catch (error) {
      $("cfgStatus").textContent = `Google status error: ${error.message}`;
    }
  }

  function clearExecutiveModeFilters() {
    [
      ["decisionLens", "all"], ["timeWindow", "all"], ["filterRegion", "all"], ["filterAccountFocus", "all"],
      ["filterAccountName", "all"], ["filterServiceLine", "all"], ["filterLane", "all"], ["filterRegulator", "all"],
      ["filterSource", "all"], ["filterSignalType", "all"], ["minScore", "0"], ["minConfidence", "0"],
      ["minPriority", "0"], ["filterText", ""], ["sortBy", "priority_desc"]
    ].forEach(([id, value]) => { $(id).value = value; });
    applyClientFilters();
  }

  function wireExecutiveModeControls() {
    [
      "decisionLens", "timeWindow", "filterRegion", "filterAccountFocus", "filterAccountName", "filterServiceLine",
      "filterLane", "filterRegulator", "filterSource", "filterSignalType", "minScore", "minConfidence", "minPriority", "sortBy"
    ].forEach(id => $(id).addEventListener("change", applyClientFilters));
    $("filterText").addEventListener("input", applyClientFilters);
    $("clearFiltersBtn").addEventListener("click", clearExecutiveModeFilters);
    $("refreshViewBtn").addEventListener("click", refreshStateAndSignals);
  }

  function openHelpModal() {
    $("helpModal").classList.add("show");
    $("helpModal").setAttribute("aria-hidden", "false");
  }

  function closeHelpModal() {
    $("helpModal").classList.remove("show");
    $("helpModal").setAttribute("aria-hidden", "true");
  }

  function wireHelpModal() {
    $("helpBtn").addEventListener("click", openHelpModal);
    $("helpCloseBtn").addEventListener("click", closeHelpModal);
    $("helpModal").addEventListener("click", event => {
      if (event.target === $("helpModal")) closeHelpModal();
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && $("helpModal").classList.contains("show")) {
        closeHelpModal();
      }
    });
  }

  function wireButtons() {
    $("demoFillBtn").addEventListener("click", async () => { await postAndTrack("/api/demo_fill", null, "Loading demo defaults..."); });
    $("demoRunBtn").addEventListener("click", async () => {
      await postAndTrack("/api/demo_fill", null, "Loading demo defaults...");
      await postAndTrack("/api/ingest", requestBody(), "Running demo ingest...");
    });
    $("ingestBtn").addEventListener("click", async () => { await postAndTrack("/api/ingest", requestBody(), "Running ingest..."); });
    $("refreshBtn").addEventListener("click", async () => { await postAndTrack("/api/refresh", null, "Refreshing radar... this can take a minute."); });
    $("runAllBtn").addEventListener("click", async () => { await postAndTrack("/api/run_all", null, "Running refresh + ingest..."); });
    $("saveCfgBtn").addEventListener("click", async () => {
      const data = await postAndTrack("/api/webassist/config", { api_key: $("gKey").value || "", cx: $("gCx").value || "" }, "Saving Google config...");
      $("cfgStatus").textContent = data.message || "Saved.";
    });
    $("testCfgBtn").addEventListener("click", async () => {
      try {
        const data = await postAndTrack("/api/webassist/test", null, "Testing Google config...");
        $("cfgStatus").textContent = data.message || "Google config works.";
      } catch (error) {
        $("cfgStatus").textContent = error.message;
        throw error;
      }
    });
  }

  async function init() {
    [
      "webKeyword", "webCompany", "gKey", "gCx", "webSourceTargets", "filterText",
      "decisionLens", "timeWindow", "filterRegion", "filterAccountFocus", "filterAccountName", "filterServiceLine",
      "filterLane", "filterRegulator", "filterSource", "filterSignalType", "minScore", "minConfidence", "minPriority", "sortBy"
    ].forEach(forceEditable);
    await loadTargets();
    wireButtons();
    wireHelpModal();
    await refreshStateAndSignals();
    await loadGoogleStatus();
    startPolling(6);
    pollLoop();
  }

  document.addEventListener("DOMContentLoaded", () => {
    init().catch(error => {
      state.lastJsError = error.message;
      updateDiagnostics();
      banner(`Page init error: ${error.message}`, "err");
      console.error(error);
    });
  });
})();

// PASS 13 - GLP-1 Manufacturing Pressure Radar START
window.SCOUT_HORIZON_PASS13_GLP1 = {
  projectName: "GLP-1 Manufacturing Pressure Radar",
  projectSubtitle: "Manufacturing-readiness, fill-finish, CDMO, validation, automation, and partner-capacity signals around high-demand injectable therapies.",
  mission: "Scan public/sample life-sciences signals for capacity pressure, operational readiness, and next-action review around GLP-1 and related injectable therapies.",
  lanes: ["fill-finish capacity", "CDMO outsourcing", "FDA/GMP pressure", "automation/BMS", "cold-chain logistics", "supplier qualification", "cyber/OT risk", "AI operations"],
  signals: [
  {
    "title": "GLP-1 fill-finish expansion signals sterile capacity pressure",
    "source": "Pharmaceutical Manufacturing",
    "domain": "pharmaceuticalmanufacturing.com",
    "observed": "2026-06-10T08:00:00",
    "region": "North America",
    "lane": "fill_finish_capacity",
    "signal_type": "manufacturing capacity",
    "signal_focus": "opportunity",
    "score": 0.94,
    "confidence": 0.84,
    "priority": 0.93,
    "tags": [
      "GLP-1",
      "fill-finish",
      "sterile manufacturing",
      "capacity expansion",
      "automation readiness",
      "validation planning"
    ],
    "summary": "Public/sample fill-finish expansion signals suggest demand for sterile capacity, commissioning readiness, automation support, and validation planning around high-demand injectable therapies.",
    "why_it_matters": "GLP-1 demand puts pressure on injectable manufacturing networks. Capacity additions usually create downstream needs for automation, environmental monitoring, validation packages, batch records, and operational readiness.",
    "pressure_opportunity": "Opportunity: sterile capacity growth can create near-term demand for automation, BAS/BMS integration, cleanroom monitoring, validation execution, and launch-readiness support.",
    "recommended_next_move": "Flag fill-finish expansion signals for follow-up and identify whether the site or partner network needs commissioning, validation, automation, or manufacturing-readiness support.",
    "link": "https://www.pharmaceuticalmanufacturing.com/"
  },
  {
    "title": "CDMO activity around injectable programs points to partner-readiness pressure",
    "source": "BioPharma Dive",
    "domain": "biopharmadive.com",
    "observed": "2026-06-09T09:00:00",
    "region": "Global",
    "lane": "cdmo_outsourcing",
    "signal_type": "partner activity",
    "signal_focus": "opportunity",
    "score": 0.91,
    "confidence": 0.8,
    "priority": 0.9,
    "tags": [
      "GLP-1",
      "CDMO",
      "outsourcing",
      "tech transfer",
      "supplier qualification",
      "partner readiness"
    ],
    "summary": "Public/sample CDMO activity suggests sponsors may be expanding injectable manufacturing partnerships, creating pressure around tech transfer, quality oversight, and partner readiness.",
    "why_it_matters": "When sponsors rely on external capacity, internal teams often need better visibility into partner qualification, process transfer, validation timing, deviation handling, and launch readiness.",
    "pressure_opportunity": "Opportunity: CDMO relationship signals can create demand for partner governance, tech-transfer readiness, validation planning, and external manufacturing oversight.",
    "recommended_next_move": "Review sponsor/CDMO relationships and determine whether the signal points to process transfer, validation capacity, quality oversight, or manufacturing project support.",
    "link": "https://www.biopharmadive.com/"
  },
  {
    "title": "Cold-chain and device logistics signals suggest injectable therapy launch complexity",
    "source": "Endpoints News",
    "domain": "endpts.com",
    "observed": "2026-06-08T11:00:00",
    "region": "North America",
    "lane": "cold_chain_logistics",
    "signal_type": "launch readiness",
    "signal_focus": "risk",
    "score": 0.86,
    "confidence": 0.78,
    "priority": 0.84,
    "tags": [
      "GLP-1",
      "cold chain",
      "device logistics",
      "launch readiness",
      "supply chain",
      "serialization"
    ],
    "summary": "Public/sample logistics signals suggest injectable therapy launches may face added cold-chain, device, serialization, and distribution-readiness complexity.",
    "why_it_matters": "High-volume injectable therapies can stress packaging, serialization, storage, device coordination, and distribution pathways. Operational misses can delay launch or reduce service levels.",
    "pressure_opportunity": "Risk and opportunity: supply-chain complexity may create demand for readiness assessments, digital records, packaging-line support, and cross-functional launch controls.",
    "recommended_next_move": "Map the signal to packaging, cold-chain, serialization, and launch-readiness owners; identify whether support is needed before scale-up milestones.",
    "link": "https://endpts.com/"
  },
  {
    "title": "FDA/GMP pressure on sterile operations raises validation-readiness signal",
    "source": "FDA Press Releases",
    "domain": "fda.gov",
    "observed": "2026-06-07T10:00:00",
    "region": "United States",
    "lane": "fda_gmp_pressure",
    "signal_type": "regulatory pressure",
    "signal_focus": "risk",
    "score": 0.84,
    "confidence": 0.82,
    "priority": 0.83,
    "tags": [
      "FDA",
      "GMP",
      "sterile operations",
      "validation",
      "quality systems",
      "inspection readiness"
    ],
    "summary": "Public/sample regulatory signals around sterile operations point to validation, documentation, deviation, and inspection-readiness pressure.",
    "why_it_matters": "Manufacturing scale-up around injectable products increases scrutiny on aseptic controls, environmental monitoring, change control, validation packages, and data integrity.",
    "pressure_opportunity": "Risk: weak validation or quality-system readiness can slow manufacturing expansion. Opportunity: support teams can reduce readiness gaps before inspection or launch milestones.",
    "recommended_next_move": "Review sterile manufacturing quality signals and identify whether validation, environmental monitoring, documentation, or inspection-readiness work should be prioritized.",
    "link": "https://www.fda.gov/news-events/fda-newsroom/press-announcements"
  },
  {
    "title": "Automation and environmental monitoring demand rises with injectable capacity projects",
    "source": "Pharma Manufacturing",
    "domain": "pharmamanufacturing.com",
    "observed": "2026-06-06T08:30:00",
    "region": "United States",
    "lane": "automation_bms",
    "signal_type": "automation readiness",
    "signal_focus": "opportunity",
    "score": 0.82,
    "confidence": 0.76,
    "priority": 0.81,
    "tags": [
      "automation",
      "BAS",
      "BMS",
      "environmental monitoring",
      "cleanroom",
      "manufacturing readiness"
    ],
    "summary": "Public/sample capacity and facility signals suggest increased need for automation, cleanroom monitoring, BMS/BAS integration, and operational readiness support.",
    "why_it_matters": "Sterile capacity projects often require coordinated automation, facility systems, monitoring, alarms, and validation evidence. These needs can appear before public project details mature.",
    "pressure_opportunity": "Opportunity: facility and automation readiness signals can create early advisory, integration, commissioning, and validation-support lanes.",
    "recommended_next_move": "Review facility expansion signals for automation scope, cleanroom controls, environmental monitoring, and commissioning readiness requirements.",
    "link": "https://www.pharmamanufacturing.com/"
  },
  {
    "title": "Supplier qualification pressure appears around injectable component networks",
    "source": "STAT",
    "domain": "statnews.com",
    "observed": "2026-06-05T12:00:00",
    "region": "Global",
    "lane": "supplier_qualification",
    "signal_type": "supplier readiness",
    "signal_focus": "risk",
    "score": 0.78,
    "confidence": 0.74,
    "priority": 0.77,
    "tags": [
      "GLP-1",
      "supplier qualification",
      "components",
      "single-use systems",
      "quality oversight",
      "supply resilience"
    ],
    "summary": "Public/sample supplier signals suggest component, material, device, and single-use system readiness may become a limiting factor for injectable therapy scale-up.",
    "why_it_matters": "Even when fill-finish capacity grows, component and supplier readiness can constrain launch timing. Supplier qualification and quality oversight often become hidden bottlenecks.",
    "pressure_opportunity": "Risk: supplier readiness gaps can delay manufacturing. Opportunity: qualification planning and supplier oversight support can reduce launch risk.",
    "recommended_next_move": "Identify supplier and component categories tied to the signal; review qualification, quality oversight, and alternate-source readiness.",
    "link": "https://www.statnews.com/"
  },
  {
    "title": "AI process monitoring signals point to data-integrity and validation opportunity",
    "source": "Fierce Pharma",
    "domain": "fiercepharma.com",
    "observed": "2026-06-04T09:30:00",
    "region": "North America",
    "lane": "ai_operations",
    "signal_type": "AI operations",
    "signal_focus": "opportunity",
    "score": 0.75,
    "confidence": 0.72,
    "priority": 0.74,
    "tags": [
      "AI operations",
      "process monitoring",
      "data integrity",
      "validation",
      "manufacturing analytics",
      "quality intelligence"
    ],
    "summary": "Public/sample AI operations signals suggest manufacturing teams may explore process monitoring, deviation prediction, and quality intelligence around high-volume injectable operations.",
    "why_it_matters": "AI-enabled manufacturing support can create value, but regulated environments require careful validation boundaries, data-integrity controls, model governance, and human review.",
    "pressure_opportunity": "Opportunity: AI process monitoring creates demand for validation-aware implementation, data governance, and practical operating models.",
    "recommended_next_move": "Review whether the signal belongs in AI monitoring, quality intelligence, or validation governance; identify decision owners before pursuing automation.",
    "link": "https://www.fiercepharma.com/"
  },
  {
    "title": "Manufacturing labor and commissioning signals create readiness bottleneck warning",
    "source": "SEC Filings (EDGAR)",
    "domain": "sec.gov",
    "observed": "2026-06-03T08:00:00",
    "region": "United States",
    "lane": "commissioning_readiness",
    "signal_type": "operational readiness",
    "signal_focus": "risk",
    "score": 0.73,
    "confidence": 0.7,
    "priority": 0.72,
    "tags": [
      "commissioning",
      "operational readiness",
      "manufacturing labor",
      "validation staffing",
      "scale-up",
      "project execution"
    ],
    "summary": "Public/sample filing and operational signals suggest staffing, commissioning, and validation execution may become bottlenecks in injectable manufacturing expansion.",
    "why_it_matters": "Capacity projects can be delayed when commissioning, validation, quality, and operations staffing do not ramp with the physical buildout.",
    "pressure_opportunity": "Risk: readiness bottlenecks may slow project execution. Opportunity: structured project support can improve launch confidence.",
    "recommended_next_move": "Review whether staffing, commissioning, validation execution, or operational readiness are named or implied in the signal set.",
    "link": "https://www.sec.gov/edgar/search/"
  },
  {
    "title": "Cyber/OT exposure rises as manufacturing sites add connected automation",
    "source": "CISA Advisories",
    "domain": "cisa.gov",
    "observed": "2026-06-02T13:00:00",
    "region": "United States",
    "lane": "cyber_ot_risk",
    "signal_type": "cyber/OT risk",
    "signal_focus": "risk",
    "score": 0.7,
    "confidence": 0.74,
    "priority": 0.7,
    "tags": [
      "cyber/OT",
      "manufacturing systems",
      "BMS",
      "automation",
      "segmentation",
      "resilience"
    ],
    "summary": "Public/sample cyber/OT signals suggest connected manufacturing expansion can increase exposure across automation, facility systems, and monitoring networks.",
    "why_it_matters": "As sterile sites add connected systems, risk expands across OT networks, BMS/BAS, monitoring, and vendor access. Leadership needs resilience planning alongside automation.",
    "pressure_opportunity": "Risk: cyber/OT weaknesses can disrupt production or slow digital expansion. Opportunity: readiness reviews can align automation growth with resilience controls.",
    "recommended_next_move": "Identify whether automation, facility systems, or vendor connectivity are part of the signal; review cyber/OT segmentation and resilience readiness.",
    "link": "https://www.cisa.gov/news-events/cybersecurity-advisories"
  },
  {
    "title": "Packaging and serialization capacity signals suggest launch-readiness opportunity",
    "source": "Packaging Digest",
    "domain": "packagingdigest.com",
    "observed": "2026-06-01T08:00:00",
    "region": "Global",
    "lane": "packaging_serialization",
    "signal_type": "launch readiness",
    "signal_focus": "opportunity",
    "score": 0.68,
    "confidence": 0.69,
    "priority": 0.68,
    "tags": [
      "packaging",
      "serialization",
      "device assembly",
      "launch readiness",
      "injectables",
      "supply chain"
    ],
    "summary": "Public/sample packaging and serialization signals suggest injectable therapy growth can pressure device assembly, labeling, packaging, and distribution readiness.",
    "why_it_matters": "For high-volume therapies, packaging and serialization are not afterthoughts. They can become launch-critical constraints as demand grows.",
    "pressure_opportunity": "Opportunity: packaging and serialization pressure can create readiness, validation, and project-management support needs.",
    "recommended_next_move": "Review packaging, serialization, and device assembly dependencies connected to the signal before launch-readiness planning.",
    "link": "https://www.packagingdigest.com/"
  },
  {
    "title": "Real-world evidence activity expands pressure for patient-access planning",
    "source": "ClinicalTrials.gov",
    "domain": "clinicaltrials.gov",
    "observed": "2026-05-31T10:00:00",
    "region": "Global",
    "lane": "rwe_access",
    "signal_type": "evidence and access",
    "signal_focus": "opportunity",
    "score": 0.64,
    "confidence": 0.66,
    "priority": 0.63,
    "tags": [
      "RWE",
      "patient access",
      "GLP-1",
      "evidence generation",
      "commercial readiness",
      "market access"
    ],
    "summary": "Public/sample evidence signals suggest GLP-1 and related injectable therapies may create continued pressure around patient access, outcomes evidence, and market readiness.",
    "why_it_matters": "Manufacturing readiness is only one side of the field change. Evidence, access, and reimbursement signals can shape launch timing and demand forecasting.",
    "pressure_opportunity": "Opportunity: evidence and access movement can guide prioritization of manufacturing, supply, and commercial readiness signals.",
    "recommended_next_move": "Keep evidence and access signals in the horizon view, but prioritize manufacturing-readiness signals for operational follow-up.",
    "link": "https://clinicaltrials.gov/"
  },
  {
    "title": "Global injectable demand signals strengthen long-horizon capacity watch",
    "source": "World Health / Market Watch",
    "domain": "public-sample",
    "observed": "2026-05-30T08:00:00",
    "region": "Global",
    "lane": "long_horizon_capacity",
    "signal_type": "horizon watch",
    "signal_focus": "opportunity",
    "score": 0.61,
    "confidence": 0.64,
    "priority": 0.61,
    "tags": [
      "injectables",
      "global demand",
      "capacity watch",
      "long horizon",
      "manufacturing strategy",
      "portfolio planning"
    ],
    "summary": "Public/sample demand signals support a long-horizon capacity watch for injectable therapies and adjacent metabolic, cardiometabolic, and chronic-care markets.",
    "why_it_matters": "Leadership needs near-term project signals and longer-horizon capacity context. Demand movement can justify early scouting for partners, sites, and readiness constraints.",
    "pressure_opportunity": "Opportunity: long-horizon capacity watch helps identify where future manufacturing, validation, and automation support may become relevant.",
    "recommended_next_move": "Maintain this in the watchlist as a strategic horizon signal rather than an immediate project action.",
    "link": "https://www.who.int/"
  }
]
};

(function () {
  function normalizeSignal(s, idx) {
    var observed = s.observed || "2026-06-10T08:00:00";
    return {
      id: s.id || ("glp1_pressure_" + (idx + 1)),
      title: s.title,
      source: s.source,
      domain: s.domain || "",
      observed: observed,
      date: observed,
      region: s.region || "Global",
      lane: s.lane || "glp1_pressure",
      signal_type: s.signal_type || "public/sample signal",
      signal_focus: s.signal_focus || "opportunity",
      score: s.score,
      confidence: s.confidence,
      priority: s.priority,
      tags: s.tags || [],
      summary: s.summary,
      observation: s.summary,
      why_it_matters: s.why_it_matters,
      pressure_opportunity: s.pressure_opportunity,
      recommended_next_move: s.recommended_next_move,
      link: s.link || "",
      url: s.link || "",
      service_lines: s.tags || [],
      coverage_labels: {
        organization_source_focus: s.lane || "GLP-1 pressure watch",
        operating_regions: s.region || "Global",
        service_lines: (s.tags || []).slice(0, 4).join(", "),
        regulators: (s.tags || []).indexOf("FDA") >= 0 ? "FDA" : ""
      }
    };
  }

  function applyPass13Demo() {
    var pack = window.SCOUT_HORIZON_PASS13_GLP1;
    var normalized = pack.signals.map(normalizeSignal);

    try {
      window.curatedDemoSignals = normalized;
      window.demoSignals = normalized;
      window.defaultSignals = normalized;
      window.seedSignals = normalized;
      window.signals = normalized;
    } catch (e) {}

    try {
      if (window.state && typeof window.state === "object") {
        window.state.mode = "glp1_pressure_radar";
        window.state.last_action = "GLP-1 Manufacturing Pressure Radar loaded";
        window.state.keyword = "";
        window.state.query = "";
        window.state.company = "";
        window.state.signals = normalized;
        window.state.loaded_signals = normalized;
      }
    } catch (e) {}

    try {
      document.dispatchEvent(new CustomEvent("scout:pass13:glp1", { detail: pack }));
    } catch (e) {}
  }

  window.applyScoutHorizonPass13GLP1 = applyPass13Demo;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyPass13Demo);
  } else {
    applyPass13Demo();
  }
})();
// PASS 13 - GLP-1 Manufacturing Pressure Radar END
