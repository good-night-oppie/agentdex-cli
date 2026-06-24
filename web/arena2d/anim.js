/* anim.js — single forward-only pass over the REAL battle log builds (a) the 2D
 * replay steps and (b) one decision "read" per agent action, each carrying a
 * ZERO-LEAKAGE opponent-model snapshot (captured at the turn boundary — the state
 * the agent actually knew when it chose; we err toward LESS info, never future-leak).
 * It then drives the left replay + the right MIND READOUT (mind.js) in sync, plus an
 * interactive decision timeline you can scrub. The PRIMITIVE is an OUTCOME, stamped
 * only AFTER the move resolves (no hindsight). */
(function () {
  "use strict";
  const A = window.__ARENA2D;
  const { LOG, RATIONALES, SIDE_LABEL, F, slug, sprite, pubHp, sideOf, monOf } = A;
  const DEX = window.__ARENA2D_DEX;

  /* ---------------- pre-pass: steps[] + reads[] (+ opponent snapshots) ------------- */
  const steps = [];
  const reads = [];
  const active = { p1: blank(), p2: blank() };
  function blank() { return { name: null, lv: null, hp: 100 }; }

  // running opponent (p2) model — revealed-only, mutated forward as the log is read.
  const p2 = { active: null, team: {} };
  function p2mon(name) {
    if (!p2.team[name]) p2.team[name] = { moves: [], hp: 100, item: null, ability: null, fainted: false };
    return p2.team[name];
  }
  function snapP2() {
    const m = p2.active ? p2.team[p2.active] : null;
    return {
      active: p2.active,
      hp: m ? m.hp : null,
      item: m ? m.item : null,
      ability: m ? m.ability : null,
      moves: m ? m.moves.slice() : [],
    };
  }
  let turnSnap = snapP2(); // p2 state captured at the most recent turn boundary
  let p1active = null;

  let rp = 0; // rationale pointer — greedy, in order
  function matchRationale(moveOrSpecies) {
    const key = slug(moveOrSpecies);
    for (let i = rp; i < RATIONALES.length; i++) {
      if (slug(RATIONALES[i].move) === key) { rp = i + 1; return RATIONALES[i].rationale || ""; }
    }
    return "";
  }

  let started = false;
  let curRead = null;             // in-progress p1 MOVE read (refine outcome from effects)
  let pendingOutcome = null;      // read index awaiting its outcome-stamp step

  function flushOutcome() {
    if (pendingOutcome != null) { steps.push({ type: "outcome", readIdx: pendingOutcome }); pendingOutcome = null; }
  }
  function newRead(kind, label, rationale, p1mon, p2name) {
    const r = {
      kind, label, rationale, p1mon, p2mon: p2name,
      primitive: kind === "switch" ? "PIVOT" : "CHIP",
      outcomeText: kind === "switch" ? "tactical switch" : "neutral hit",
      moveType: kind === "move" ? DEX.moveType(label) : null,
      decTurn: curTurn,
      oppModel: kind === "switch" ? snapP2() : turnSnap, // switch: state up to now; move: turn-start
      stepIdx: -1,
    };
    reads.push(r);
    return r;
  }

  let curTurn = null;
  for (const ln of LOG) {
    const f = F(ln), t = f[1];

    if (t === "turn") { flushOutcome(); started = true; curTurn = +f[2]; turnSnap = snapP2(); curRead = null; steps.push({ type: "turn", n: +f[2] }); continue; }
    if (t === "upkeep") { flushOutcome(); continue; }

    if (t === "switch" || t === "drag") {
      flushOutcome();
      const side = sideOf(f[2]);
      const name = (f[3] || "").split(",")[0].trim() || monOf(f[2]);
      const lv = f[3] && f[3].match(/L(\d+)/) ? +f[3].match(/L(\d+)/)[1] : null;
      if (side === "p2") { p2.active = name; const m = p2mon(name); m.fainted = false; const h = pubHp(f[4]); if (h != null) m.hp = h; }
      if (side === "p1") p1active = name;
      if (name !== active[side].name) {
        active[side] = { name, lv, hp: 100 };
        const step = { type: "switch", side, name, lv };
        if (side === "p1" && started) {
          const r = newRead("switch", name, matchRationale(name), name, p2.active);
          step.readIdx = reads.length - 1;
          r.stepIdx = steps.length; // this step's index once pushed
          pendingOutcome = reads.length - 1;
          curRead = null;
        }
        steps.push(step);
      } else {
        const h = pubHp(f[4]); if (h != null) active[side].hp = h;
      }
      continue;
    }

    if (t === "move") {
      flushOutcome();
      const side = sideOf(f[2]), mv = f[3];
      if (side === "p2" && p2.active) { const m = p2mon(p2.active); if (!m.moves.includes(mv)) m.moves.push(mv); }
      const step = { type: "banner", text: `${SIDE_LABEL[side]}'s ${active[side].name} used ${mv}!` };
      if (side === "p1") {
        curRead = newRead("move", mv, matchRationale(mv), p1active || active.p1.name, turnSnap.active);
        step.readIdx = reads.length - 1;
        curRead.stepIdx = steps.length;
        pendingOutcome = reads.length - 1;
      }
      steps.push(step);
      continue;
    }

    // effect lines refine the current p1 move's OUTCOME (our label over real events)
    if (curRead && curRead.kind === "move") {
      if (t === "-ability" && sideOf(f[2]) === "p2" && f[4] === "boost") { curRead.primitive = "MISREAD"; curRead.outcomeText = "opponent ability triggered"; }
      else if (t === "-immune" && sideOf(f[2]) === "p2") { curRead.primitive = "MISREAD"; curRead.outcomeText = "no effect — immune"; }
      else if (t === "-supereffective" && sideOf(f[2]) === "p2") { curRead.primitive = "PUNISH"; curRead.outcomeText = "super-effective hit"; }
      else if (t === "-resisted" && sideOf(f[2]) === "p2") { curRead.primitive = "CHIP"; curRead.outcomeText = "resisted — chip only"; }
    }

    if (t === "-ability") { const s = sideOf(f[2]); if (s === "p2") { const n = monOf(f[2]); if (n) p2mon(n).ability = f[3]; } continue; }
    if (t === "-item" || t === "-enditem") { const s = sideOf(f[2]); if (s === "p2") { const n = monOf(f[2]); if (n) p2mon(n).item = f[3]; } /* fallthrough to no step */ }

    if (t === "-damage" || t === "-heal") {
      const side = sideOf(f[2]), h = pubHp(f[3]);
      if (h != null) { steps.push({ type: "hp", side, hp: h }); active[side].hp = h; if (side === "p2" && p2.active) p2mon(p2.active).hp = h; }
      continue;
    }
    if (t === "faint") {
      const side = sideOf(f[2]);
      if (side === "p2" && curRead && curRead.kind === "move") { curRead.primitive = "PUNISH"; curRead.outcomeText = (curRead.outcomeText === "neutral hit" ? "clean KO" : curRead.outcomeText + " — KO"); }
      if (side === "p2") { const n = monOf(f[2]); if (n) p2mon(n).fainted = true; p2.active = null; }
      steps.push({ type: "faint", side, name: active[side].name });
      continue;
    }
  }
  flushOutcome();

  /* ---------------------------- DOM: battle replay ---------------------------- */
  const $ = (s, r = document) => r.querySelector(s);
  const oppEl = $("#opp"), youEl = $("#you"), banner = $("#banner");
  const els = {
    p2: { img: $("img", oppEl), nm: $(".nm", oppEl), lv: $(".lv", oppEl), bar: $(".bar", oppEl), fill: $(".bar > i", oppEl), num: $(".hp-num", oppEl), slot: oppEl },
    p1: { img: $("img", youEl), nm: $(".nm", youEl), lv: $(".lv", youEl), bar: $(".bar", youEl), fill: $(".bar > i", youEl), num: $(".hp-num", youEl), slot: youEl },
  };
  function setMon(side, name, lv) {
    const e = els[side];
    e.img.src = sprite(name, side === "p1");
    e.img.onerror = () => { e.img.style.opacity = .15; };
    e.nm.textContent = name; e.lv.textContent = lv ? "Lv" + lv : "";
    e.slot.classList.remove("fainted"); e.img.style.opacity = "";
    setHp(side, 100);
  }
  function setHp(side, hp) {
    const e = els[side];
    e.fill.style.width = Math.max(0, hp) + "%";
    e.bar.classList.toggle("warn", hp <= 50 && hp > 20);
    e.bar.classList.toggle("low", hp <= 20);
    e.num.textContent = Math.max(0, hp) + "%";
  }

  /* ------------------------------ decision timeline ------------------------------ */
  const tl = $("#timeline");
  reads.forEach((r, idx) => {
    const n = document.createElement("button");
    n.className = "tnode"; n.dataset.idx = idx;
    n.title = `Decision ${idx + 1} — turn ${r.decTurn ?? "—"} — ${r.kind === "switch" ? "switch → " : ""}${r.label}`;
    n.textContent = idx + 1;
    n.onclick = () => scrubTo(idx);
    tl.appendChild(n);
  });
  const tnodes = Array.from(tl.querySelectorAll(".tnode"));
  function colorNode(idx) { const n = tnodes[idx]; if (n) { n.className = "tnode done " + reads[idx].primitive; } }
  function markCur(idx) { tnodes.forEach((n, i) => n.classList.toggle("cur", i === idx)); }

  /* ------------------------------ step application ------------------------------ */
  function applyVisual(s) {
    if (s.type === "switch") { setMon(s.side, s.name, s.lv); banner.textContent = `${SIDE_LABEL[s.side]} sent out ${s.name}!`; }
    else if (s.type === "banner") banner.textContent = s.text;
    else if (s.type === "hp") { setHp(s.side, s.hp); if (s.hp < 100) { els[s.side].img.classList.remove("hit"); void els[s.side].img.offsetWidth; els[s.side].img.classList.add("hit"); } }
    else if (s.type === "faint") { els[s.side].slot.classList.add("fainted"); banner.textContent = `${s.name} fainted!`; }
    else if (s.type === "turn") { banner.textContent = `— Turn ${s.n} —`; }
  }
  function apply(s) {
    applyVisual(s);
    if (s.readIdx != null && s.type !== "outcome") { Mind.reveal(s.readIdx); markCur(s.readIdx); }
    if (s.type === "outcome") { Mind.outcome(s.readIdx, reads[s.readIdx].primitive, reads[s.readIdx].outcomeText); colorNode(s.readIdx); }
  }
  const DELAY = { turn: 240, banner: 780, hp: 520, switch: 700, faint: 720, outcome: 360 };

  /* --------------------------------- player ----------------------------------- */
  let i = 0, timer = null, playing = false;
  const playBtn = $("#play"), stepBtn = $("#step"), restartBtn = $("#restart"), spd = $("#spd");
  function scale() { return (7 - (+spd.value)) / 3; }
  function one() {
    if (i >= steps.length) { stop(); banner.textContent += "  ·  battle over — your agent WON."; return false; }
    apply(steps[i++]); return true;
  }
  function loop() {
    if (!playing) return;
    const s = steps[i];
    if (!one()) return;
    timer = setTimeout(loop, (DELAY[s ? s.type : "banner"] || 500) * scale());
  }
  function start() { if (playing) return; if (i >= steps.length) reset(); playing = true; playBtn.textContent = "⏸ Pause"; loop(); }
  function stop() { playing = false; playBtn.textContent = "▶ Play"; clearTimeout(timer); }

  // scrub to a decision: stop, rebuild battle visuals instantly up to its step, sync panel.
  function scrubTo(idx) {
    stop();
    resetVisual();
    const target = reads[idx] ? reads[idx].stepIdx : steps.length;
    for (let k = 0; k <= target && k < steps.length; k++) { applyVisual(steps[k]); if (steps[k].type === "outcome" && k < target) colorNode(steps[k].readIdx); }
    i = target + 1;
    Mind.jumpTo(idx);
    markCur(idx);
    for (let k = 0; k < idx; k++) colorNode(k);
  }
  function resetVisual() {
    banner.textContent = "Press ▶ to run the battle.";
    els.p1.nm.textContent = "—"; els.p2.nm.textContent = "—";
    els.p1.img.removeAttribute("src"); els.p2.img.removeAttribute("src");
    els.p1.lv.textContent = ""; els.p2.lv.textContent = "";
    setHp("p1", 100); setHp("p2", 100);
    els.p1.slot.classList.remove("fainted"); els.p2.slot.classList.remove("fainted");
  }
  function reset() {
    stop(); i = 0;
    resetVisual();
    Mind.reset();
    tnodes.forEach((n, k) => { n.className = "tnode"; });
  }

  playBtn.onclick = () => (playing ? stop() : start());
  stepBtn.onclick = () => { stop(); one(); };
  restartBtn.onclick = reset;

  Mind.init(reads);
  Mind.setScrubHandler(scrubTo);
  reset();
})();
