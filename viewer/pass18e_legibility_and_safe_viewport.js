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
    if (rect.left > window.innerWidth * 0.52) score += 30;
    if (text.includes("Scout Brief")) score += 75;
    if (text.includes("Intel Stack")) score += 55;
    if (text.includes("Agent Reasoning")) score += 45;
    if (text.includes("What the scan uses")) score += 30;
    if (text.includes("Recommended next move")) score += 20;
    if (text.includes("Scout Horizon") && rect.left < window.innerWidth * 0.5) score -= 80;
    score -= Math.abs(rect.width - 520) / 90;
    return score;
  }

  function findRightRail() {
    const nodes = Array.from(document.querySelectorAll("aside, main, section, div"));
    let best = null;
    let bestScore = -9999;
    for (const node of nodes) {
      const score = scoreRightRail(node);
      if (score > bestScore) {
        best = node;
        bestScore = score;
      }
    }
    return bestScore > 35 ? best : null;
  }

  function scoreLeftWorkbench(node) {
    const rect = node.getBoundingClientRect();
    if (!rect || rect.width < 300 || rect.height < 150) return -9999;
    const text = clean(node.textContent);
    let score = 0;
    if (rect.left < window.innerWidth * 0.4) score += 25;
    if (text.includes("Scout Horizon")) score += 50;
    if (text.includes("What are you watching")) score += 60;
    if (text.includes("Run Scout Horizon")) score += 30;
    if (text.includes("Scout Brief")) score -= 90;
    return score;
  }

  function findLeftWorkbench() {
    const nodes = Array.from(document.querySelectorAll("aside, main, section, div"));
    let best = null;
    let bestScore = -9999;
    for (const node of nodes) {
      const score = scoreLeftWorkbench(node);
      if (score > bestScore) {
        best = node;
        bestScore = score;
      }
    }
    return bestScore > 40 ? best : null;
  }

  function classifyText() {
    const all = Array.from(document.querySelectorAll("h1, h2, h3, h4, h5, p, div, span, button, input, select, label"));
    for (const node of all) {
      const text = clean(node.textContent || node.value || "");
      if (!text) continue;
      if (/^(Scout Horizon|Scout Brief)/i.test(text) || text === "What the scan uses" || text === "Why this signal won") {
        node.classList.add("pass18e-title");
      } else if (/^(Agent Reasoning|Intel Stack|What happened\?|Why leadership should care|How strong is the signal\?|Recommended next move|Sources|Focus|Company handling|Output)/i.test(text)) {
        node.classList.add("pass18e-label");
      } else if (text.length < 60) {
        node.classList.add("pass18e-small");
      } else {
        node.classList.add("pass18e-readable");
      }
    }
  }

  function markCardBlocks(rail) {
    if (!rail) return;
    const children = Array.from(rail.children || []);
    for (const child of children) {
      const text = clean(child.textContent);
      if (text.includes("Scout Brief") || text.includes("Agent Reasoning") || text.includes("Intel Stack") || text.includes("What the scan uses")) {
        child.classList.add("pass18e-card-block");
      }
    }
  }

  function apply() {
    document.body.classList.add("pass18e-legibility");
    const rightRail = findRightRail();
    if (rightRail) {
      rightRail.classList.add("pass18e-right-rail");
      markCardBlocks(rightRail);
    }
    const left = findLeftWorkbench();
    if (left) left.classList.add("pass18e-left-workbench");
    classifyText();
  }

  function boot() {
    apply();
    setTimeout(apply, 500);
    setTimeout(apply, 1600);
    setInterval(apply, 5000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
