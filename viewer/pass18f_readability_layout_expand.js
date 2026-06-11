(function () {
  "use strict";

  function clean(v) {
    if (v === null || v === undefined) return "";
    return String(v).replace(/\s+/g, " ").trim();
  }

  function scoreRightRail(node) {
    const rect = node.getBoundingClientRect();
    if (!rect || rect.width < 260 || rect.height < 180) return -9999;
    const text = clean(node.textContent);
    let score = 0;
    if (rect.left > window.innerWidth * 0.50) score += 35;
    if (text.includes("Scout Brief")) score += 80;
    if (text.includes("Agent Reasoning")) score += 70;
    if (text.includes("Intel Stack")) score += 55;
    if (text.includes("What the scan uses")) score += 35;
    if (text.includes("What are you watching")) score -= 80;
    score -= Math.abs(rect.width - 560) / 120;
    return score;
  }

  function scoreLeftRail(node) {
    const rect = node.getBoundingClientRect();
    if (!rect || rect.width < 260 || rect.height < 160) return -9999;
    const text = clean(node.textContent);
    let score = 0;
    if (rect.left < window.innerWidth * 0.42) score += 35;
    if (text.includes("Scout Horizon")) score += 60;
    if (text.includes("What are you watching")) score += 80;
    if (text.includes("Run Scout Horizon")) score += 45;
    if (text.includes("Scout Brief")) score -= 90;
    return score;
  }

  function bestNode(scoreFn, threshold) {
    let best = null;
    let bestScore = -9999;
    const nodes = Array.from(document.querySelectorAll("aside, main, section, div"));
    for (const node of nodes) {
      const score = scoreFn(node);
      if (score > bestScore) {
        best = node;
        bestScore = score;
      }
    }
    return bestScore >= threshold ? best : null;
  }

  function markText() {
    const nodes = Array.from(document.querySelectorAll("h1, h2, h3, h4, h5, p, div, span, label, button"));
    for (const node of nodes) {
      const text = clean(node.textContent);
      if (!text) continue;

      if (/^(SCOUT BRIEF|Scout Brief)/i.test(text) || /^Scout Horizon$/i.test(text)) {
        node.classList.add("pass18f-headline");
      } else if (/^(Why this signal won|What the scan uses)$/i.test(text)) {
        node.classList.add("pass18f-section-heading");
      } else if (/^(WHAT HAPPENED\?|WHY LEADERSHIP SHOULD CARE|HOW STRONG IS THE SIGNAL\?|RECOMMENDED NEXT MOVE|AGENT REASONING|EVIDENCE STATUS|WHY SELECTED|AGENT RUN LOG|SOURCES|FOCUS|COMPANY HANDLING|OUTPUT)/i.test(text)) {
        node.classList.add("pass18f-label");
      } else if (text.length > 90) {
        node.classList.add("pass18f-readable");
      } else {
        node.classList.add("pass18f-small");
      }

      const style = window.getComputedStyle(node);
      if (style && (style.borderStyle !== "none" || style.backgroundColor !== "rgba(0, 0, 0, 0)")) {
        const rect = node.getBoundingClientRect();
        if (rect.width > 250 && rect.height > 40) node.classList.add("pass18f-inner-card");
      }
    }
  }

  function apply() {
    document.body.classList.add("pass18f-readable");

    const right = bestNode(scoreRightRail, 55);
    if (right) {
      right.classList.add("pass18f-right-rail");
      Array.from(right.children || []).forEach(child => child.classList.add("pass18f-card"));
    }

    const left = bestNode(scoreLeftRail, 60);
    if (left) {
      left.classList.add("pass18f-left-rail");
      const title = Array.from(left.querySelectorAll("*")).find(n => clean(n.textContent) === "Scout Horizon");
      if (title) title.classList.add("pass18f-title");
    }

    markText();
  }

  function boot() {
    apply();
    setTimeout(apply, 400);
    setTimeout(apply, 1400);
    setTimeout(apply, 2800);
    setInterval(apply, 5000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
