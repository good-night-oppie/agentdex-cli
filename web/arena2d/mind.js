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
    // MOVE decision -> OFFENSIVE matchup: the chosen move's type into the foe.
    // SWITCH decision -> DEFENSIVE matchup: how the incoming mon RESISTS the foe's
    // STABs (its own types are defenders, the foe's types are the attack lenses) —
    // showing the incoming mon's first attack type would misframe a defensive pivot.
    const def = r.kind === "switch" ? "def" : "off";
    const lenses = def === "off"
      ? Array.from(new Set([r.moveType, ...youT].filter(Boolean)))
      : oppT.slice();
    const defLens = def === "off" ? (r.moveType || youT[0]) : oppT[0];
    const lensHtml = lenses
      .map((t) => `<button class="lens ty ${t}${t === defLens ? " on" : ""}" data-lens="${t}">${t}</button>`)
      .join("");
    const label = def === "off" ? "attack&nbsp;lens" : "foe&nbsp;STAB";
    const hint = def === "off"
      ? (r.moveType ? `<span class="movehint">chosen: ${r.label} · ${r.moveType}</span>` : "")
      : `<span class="movehint">how ${r.p1mon} takes it</span>`;
    return (
      `<div class="matchup" data-mode="${def}" data-default="${defLens}"` +
      ` data-you='${JSON.stringify(youT)}' data-opp='${JSON.stringify(oppT)}'>` +
      `<div class="verdict"></div>` +
      `<div class="lensrow"><span class="lenslab">${label}</span>${lensHtml}${hint}</div></div>`
    );
  }
  function renderVerdict(card, lensType) {
    const mu = card.querySelector(".matchup");
    if (!mu) return;
    const youT = JSON.parse(mu.dataset.you);
    const oppT = JSON.parse(mu.dataset.opp);
    const off = mu.dataset.mode === "off";
    // offensive: my move-type INTO the foe. defensive: the foe's type INTO me.
    const defenders = off ? oppT : youT;
    const m = DEX.effectiveness(lensType, defenders);
    const v = DEX.verdict(m);
    const youName = card.dataset.you || "", oppName = card.dataset.opp || "";
    const sub = off
      ? `<span class="ty ${lensType}">${lensType}</span> → ${oppName} ${typePills(oppT)}`
      : `${oppName}'s <span class="ty ${lensType}">${lensType}</span> → ${youName} ${typePills(youT)}`;
    mu.querySelector(".verdict").className = "verdict " + v.k;
    mu.querySelector(".verdict").innerHTML =
      `<span class="vx">${v.x}</span> <b>${v.t}</b> <span class="vsub">${sub}</span>`;
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
      fanHtml(r, oppT) +
      `</div>` +

      `<div class="outcome off"><span class="ochip"></span><span class="otext"></span></div>`
    );
  }

  /* ---- the ATTESTED candidate fan: what the agent weighed + rejected ----
   * `r.considered` is real (codex_decide_explain) — the move + the agent's own
   * `why_not`. We ground each with OUR derived type read (dex.js) so a "resisted"
   * claim is checkable; the chosen move "fires" at the top. The why_not is attested;
   * the ×badge is derived (the same honesty split the rest of the panel keeps). */
  function fanHtml(r, oppT) {
    const cons = (r.considered || []).filter((c) => c && c.move);
    const chosenType = r.moveType ? `<span class="ty ${r.moveType}">${r.moveType}</span>` : "";
    const chosen =
      `<div class="fanrow chosen"><span class="firedot"></span>` +
      `<span class="fanmv">${r.label}</span>${chosenType}<span class="fanwhy">▶ chosen</span></div>`;
    if (!cons.length) {
      // no attested fan for this decision — show only the chosen "fired" node, no fakery.
      return `<div class="fan"><div class="emlabel fanlabel">CANDIDATES <i>· codex_decide_explain</i></div>${chosen}</div>`;
    }
    const rows = cons
      .map((c) => {
        const mt = DEX.moveType(c.move);
        let badge = "";
        if (mt && oppT && oppT.length) {
          const v = DEX.verdict(DEX.effectiveness(mt, oppT));
          badge = `<span class="ty ${mt}">${mt}</span><span class="fanx ${v.k}">${v.x}</span>`;
        }
        const why = (c.why_not || "").replace(/</g, "&lt;");
        return `<div class="fanrow"><span class="fanmv">${c.move}</span>${badge}<span class="fanwhy">${why}</span></div>`;
      })
      .join("");
    return (
      `<div class="fan">` +
      `<div class="emlabel fanlabel">CANDIDATES <i>· weighed + rejected · codex_decide_explain</i></div>` +
      chosen +
      rows +
      `</div>`
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
      c.dataset.you = r.p1mon || "";
      c.innerHTML = cardHtml(r, idx);
      root.appendChild(c);
      const mu = c.querySelector(".matchup");
      if (mu) renderVerdict(c, mu.dataset.default);
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
