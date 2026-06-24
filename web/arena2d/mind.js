/* mind.js — the deep-thinking MIND READOUT panel (right pane). Owns its DOM.
 *
 * EPISTEMIC BOUNDARY (the honesty contract):
 *   · OPPONENT MODEL + TYPE MATCHUP = DERIVED. Reconstructed by us, forward-only,
 *     from the real battle log up to THIS decision (fog of war — no future leak).
 *   · AGENT — the streamed rationale = the agent's REAL words (codex_decide), verbatim.
 *   · OUTCOME = what the game actually did, stamped ONLY after the move resolves
 *     (never shown next to the pre-move rationale — no hindsight).
 *
 * anim.js builds reads[] (one per agent decision, each with a zero-leakage oppModel
 * snapshot) and drives this panel: reveal(idx) at the move, outcome(idx,...) after
 * effects, jumpTo(idx) on scrub/pause. The panel is fully explorable when paused. */
window.Mind = (function () {
  "use strict";
  const DEX = window.__ARENA2D_DEX;
  let reads = [];
  let root = null;
  let cur = -1;
  let typer = null;
  let onScrub = function () {};

  const el = (tag, cls, html) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  };
  const typePills = (types) =>
    (types || []).map((t) => `<span class="ty ${t}">${t}</span>`).join("");

  /* ---- the interactive type-matchup widget for one decision ---- */
  function matchup(r) {
    const youT = DEX.speciesTypes(r.p1mon);
    const oppT = DEX.speciesTypes(r.p2mon);
    if (!youT || !oppT) return "";
    // attack lenses = the agent mon's STAB types; default lens = chosen move's type.
    const lensTypes = youT.slice();
    const moveT = r.moveType && !lensTypes.includes(r.moveType) ? r.moveType : r.moveType;
    const def = r.moveType || youT[0];
    const lenses = Array.from(new Set([r.moveType, ...youT].filter(Boolean)));
    const lensHtml = lenses
      .map((t) => `<button class="lens ty ${t}${t === def ? " on" : ""}" data-lens="${t}">${t}</button>`)
      .join("");
    return (
      `<div class="matchup" data-opp='${JSON.stringify(oppT)}'>` +
      `<div class="verdict" data-default="${def}"></div>` +
      `<div class="lensrow"><span class="lenslab">attack&nbsp;lens</span>${lensHtml}` +
      (r.moveType ? `<span class="movehint">chosen: ${r.label} · ${r.moveType}</span>` : "") +
      `</div></div>`
    );
  }
  function renderVerdict(card, lensType) {
    const mu = card.querySelector(".matchup");
    if (!mu) return;
    const oppT = JSON.parse(mu.dataset.opp);
    const m = DEX.effectiveness(lensType, oppT);
    const v = DEX.verdict(m);
    const oppName = card.dataset.opp || "";
    mu.querySelector(".verdict").className = "verdict " + v.k;
    mu.querySelector(".verdict").innerHTML =
      `<span class="vx">${v.x}</span> <b>${v.t}</b> ` +
      `<span class="vsub"><span class="ty ${lensType}">${lensType}</span> → ${oppName} ${typePills(oppT)}</span>`;
    mu.querySelectorAll(".lens").forEach((b) =>
      b.classList.toggle("on", b.dataset.lens === lensType)
    );
  }

  function cardHtml(r, idx) {
    const youT = DEX.speciesTypes(r.p1mon) || [];
    const oppT = DEX.speciesTypes(r.p2mon) || [];
    const om = r.oppModel || {};
    const moves = (om.moves || []).slice(0, 4);
    const slots = moves.map((m) => `<span class="mvpill">${m}</span>`);
    while (slots.length < 4) slots.push(`<span class="mvpill q">???</span>`);
    const item = om.item ? `<span class="kv">item ${om.item}</span>` : "";
    const abil = om.ability ? `<span class="kv">ability ${om.ability}</span>` : "";
    const hp = om.hp == null ? "?" : om.hp + "%";

    return (
      `<div class="dhead"><span class="dnum">DEC ${idx + 1}</span>` +
      `<span class="dturn">turn ${r.decTurn != null ? r.decTurn : "—"}</span>` +
      `<span class="daction">${r.kind === "switch" ? "switch → " : "move · "}<b>${r.label}</b></span></div>` +

      `<div class="block sys">` +
      `<div class="emlabel">OPPONENT MODEL <i>· reconstructed from the log · fog of war</i></div>` +
      `<div class="vs">` +
      `<span class="who you"><span class="wl">YOU</span> <b>${r.p1mon || "?"}</b> ${typePills(youT)}</span>` +
      `<span class="who opp"><span class="wl">OPP</span> <b>${r.p2mon || "?"}</b> ${typePills(oppT)} <i class="ohp">${hp}</i></span>` +
      `</div>` +
      `<div class="moves"><span class="ml">revealed moves</span>${slots.join("")} ${item} ${abil}</div>` +
      matchup(r) +
      `</div>` +

      `<div class="block agent">` +
      `<div class="emlabel agentlabel">AGENT <i>· its own words · codex_decide</i></div>` +
      `<div class="ratio mono" data-text="${(r.rationale || "").replace(/"/g, "&quot;")}"></div>` +
      `</div>` +

      `<div class="outcome off"><span class="ochip"></span><span class="otext"></span></div>`
    );
  }

  function init(readsIn, opts) {
    reads = readsIn || [];
    root = document.getElementById("reads");
    root.innerHTML = "";
    reads.forEach((r, idx) => {
      const c = el("div", "dcard future");
      c.dataset.idx = idx;
      c.dataset.opp = r.p2mon || "";
      c.innerHTML = cardHtml(r, idx);
      root.appendChild(c);
      const def = c.querySelector(".verdict");
      if (def) renderVerdict(c, def.dataset.default);
    });
    // interactivity: attack-lens toggle + click-to-inspect a past card.
    root.addEventListener("click", (e) => {
      const lens = e.target.closest(".lens");
      if (lens) {
        renderVerdict(lens.closest(".dcard"), lens.dataset.lens);
        e.stopPropagation();
        return;
      }
      const card = e.target.closest(".dcard.past");
      if (card) {
        root.querySelectorAll(".dcard.peek").forEach((c) => c.classList.remove("peek"));
        card.classList.add("peek");
        card.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  }

  function stream(node, text, instant) {
    if (typer) { clearTimeout(typer); typer = null; }
    if (instant || !text) {
      node.textContent = text || "";
      node.classList.remove("typing");
      return;
    }
    node.textContent = "";
    node.classList.add("typing");
    const words = text.split(/(\s+)/);
    let i = 0;
    (function go() {
      if (i >= words.length) { node.classList.remove("typing"); return; }
      node.textContent += words[i++];
      typer = setTimeout(go, 34);
    })();
  }

  function setState(card, st) {
    card.classList.remove("future", "active", "past", "peek");
    card.classList.add(st);
  }

  // reveal a decision live: opponent model + rationale stream; outcome stays hidden.
  function reveal(idx) {
    if (idx == null || idx === cur) return;
    cur = idx;
    reads.forEach((r, i) => {
      const c = root.children[i];
      if (!c) return;
      const ratio = c.querySelector(".ratio");
      if (i < idx) {
        setState(c, "past");
        ratio.textContent = ratio.dataset.text;
        ratio.classList.remove("typing");
      } else if (i === idx) {
        setState(c, "active");
        stream(ratio, ratio.dataset.text, false);
        c.scrollIntoView({ behavior: "smooth", block: "center" });
      } else {
        setState(c, "future");
        ratio.textContent = "";
        c.querySelector(".outcome").className = "outcome off";
      }
    });
  }

  // stamp what the game actually did — AFTER the move resolved (no hindsight).
  function outcome(idx, primitive, text) {
    const c = root.children[idx];
    if (!c) return;
    const o = c.querySelector(".outcome");
    o.className = "outcome on " + primitive;
    o.querySelector(".ochip").textContent = primitive;
    o.querySelector(".otext").textContent = text || "";
  }

  // instant sync for scrub/pause: decisions < idx are full history (with outcomes),
  // idx shows its pre-move state only (its outcome hasn't happened yet).
  function jumpTo(idx) {
    cur = idx;
    reads.forEach((r, i) => {
      const c = root.children[i];
      if (!c) return;
      const ratio = c.querySelector(".ratio");
      const o = c.querySelector(".outcome");
      if (i < idx) {
        setState(c, "past");
        ratio.textContent = ratio.dataset.text;
        ratio.classList.remove("typing");
        if (r.primitive) { o.className = "outcome on " + r.primitive; o.querySelector(".ochip").textContent = r.primitive; o.querySelector(".otext").textContent = r.outcomeText || ""; }
      } else if (i === idx) {
        setState(c, "active");
        stream(ratio, ratio.dataset.text, true);
        o.className = "outcome off";
        c.scrollIntoView({ behavior: "auto", block: "center" });
      } else {
        setState(c, "future");
        ratio.textContent = "";
        o.className = "outcome off";
      }
    });
  }

  function reset() {
    cur = -1;
    if (typer) { clearTimeout(typer); typer = null; }
    reads.forEach((r, i) => {
      const c = root.children[i];
      if (!c) return;
      setState(c, "future");
      c.querySelector(".ratio").textContent = "";
      c.querySelector(".outcome").className = "outcome off";
    });
  }

  return {
    init,
    reveal,
    outcome,
    jumpTo,
    reset,
    setScrubHandler: (fn) => (onScrub = fn || onScrub),
    _scrub: (i) => onScrub(i),
  };
})();
