/* anim.js — one pass over the REAL battle log builds the animation + the per-decision
 * "mind readout". Each p1 decision card shows the move it made + a fixed-vocabulary
 * PRIMITIVE label (ours) + the agent's REAL rationale (codex_decide), greedily matched
 * to the move so a shown rationale is always the agent's actual word for THAT action. */
(function () {
  "use strict";
  const A = window.__ARENA2D;
  const { LOG, RATIONALES, SIDE_LABEL, F, slug, sprite, pubHp, sideOf, monOf } = A;

  /* ---------- pre-pass: steps[] (animation) + reads[] (one per p1 decision) ---------- */
  const steps = [];
  const reads = [];
  const active = { p1: blank(), p2: blank() };
  function blank() { return { name: null, lv: null, hp: 100 }; }

  let rp = 0; // rationale pointer — greedy, in order
  function matchRationale(moveOrSpecies) {
    const key = slug(moveOrSpecies);
    for (let i = rp; i < RATIONALES.length; i++) {
      if (slug(RATIONALES[i].move) === key) { rp = i + 1; return RATIONALES[i].rationale || ""; }
    }
    return "";
  }

  let started = false; // first |turn| — p1 switches before it are the lead, not a decision
  let curRead = null; // the in-progress p1 MOVE read, to refine its primitive from effects

  function newRead(kind, label, rationale) {
    const r = { kind, label, primitive: kind === "switch" ? "PIVOT" : "CHIP", rationale };
    reads.push(r);
    return r;
  }

  for (const ln of LOG) {
    const f = F(ln), t = f[1];
    if (t === "turn") { started = true; curRead = null; steps.push({ type: "turn", n: +f[2] }); continue; }

    if (t === "switch") {
      const side = sideOf(f[2]);
      // the FORM species from the details field (e.g. "Zamazenta-Crowned"), not the base
      // nickname — so a form-named decision matches its rationale + gets the right sprite.
      const name = (f[3] || "").split(",")[0].trim() || monOf(f[2]);
      const lv = f[3] && f[3].match(/L(\d+)/) ? +f[3].match(/L(\d+)/)[1] : null;
      if (name !== active[side].name) {
        active[side] = { name, lv, hp: 100 };
        const step = { type: "switch", side, name, lv };
        if (side === "p1" && started) {
          newRead("switch", name, matchRationale(name));
          step.readIdx = reads.length - 1;
          curRead = null;
        }
        steps.push(step);
      } else {
        const h = pubHp(f[4]); if (h != null) active[side].hp = h;
      }
      continue;
    }

    if (t === "move") {
      const side = sideOf(f[2]), mv = f[3];
      const step = { type: "banner", text: `${SIDE_LABEL[side]}'s ${active[side].name} used ${mv}!` };
      if (side === "p1") {
        curRead = newRead("move", mv, matchRationale(mv));
        step.readIdx = reads.length - 1;
      }
      steps.push(step);
      continue;
    }

    // effect lines refine the current p1 move's PRIMITIVE (our label over real events)
    if (curRead && curRead.kind === "move") {
      if (t === "-ability" && sideOf(f[2]) === "p2" && f[4] === "boost") curRead.primitive = "MISREAD";
      else if (t === "-immune" && sideOf(f[2]) === "p2") curRead.primitive = "MISREAD";
      else if (t === "-supereffective" && sideOf(f[2]) === "p2") curRead.primitive = "PUNISH";
      else if (t === "-resisted" && sideOf(f[2]) === "p2") curRead.primitive = "CHIP";
      else if (t === "faint" && sideOf(f[2]) === "p2") curRead.primitive = "PUNISH";
    }

    if (t === "-damage" || t === "-heal") {
      const side = sideOf(f[2]), h = pubHp(f[3]);
      if (h != null) { steps.push({ type: "hp", side, hp: h }); active[side].hp = h; }
      continue;
    }
    if (t === "faint") {
      const side = sideOf(f[2]);
      steps.push({ type: "faint", side, name: active[side].name });
      continue;
    }
  }

  /* ---------- DOM player ---------- */
  const $ = (s, r = document) => r.querySelector(s);
  const oppEl = $("#opp"), youEl = $("#you"), banner = $("#banner"), readsEl = $("#reads");
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
  let lastRead = null;
  function revealRead(idx) {
    const r = reads[idx]; if (!r) return;
    if (lastRead) lastRead.classList.remove("cur");
    const div = document.createElement("div");
    div.className = "read on cur";
    div.innerHTML = `<div class="top"><span class="chip ${r.primitive}">${r.primitive}</span>` +
      `<span class="mv"></span></div><div class="txt"></div>`;
    div.querySelector(".mv").textContent = (r.kind === "switch" ? "→ " : "") + r.label;
    const txt = div.querySelector(".txt");
    txt.textContent = r.rationale || "— (no rationale captured for this action)";
    if (!r.rationale) txt.classList.add("muted");
    readsEl.appendChild(div); readsEl.scrollTop = readsEl.scrollHeight;
    lastRead = div;
  }

  function apply(s) {
    if (s.type === "switch") { setMon(s.side, s.name, s.lv); banner.textContent = `${SIDE_LABEL[s.side]} sent out ${s.name}!`; }
    else if (s.type === "banner") banner.textContent = s.text;
    else if (s.type === "hp") { setHp(s.side, s.hp); if (s.hp < 100) { els[s.side].img.classList.remove("hit"); void els[s.side].img.offsetWidth; els[s.side].img.classList.add("hit"); } }
    else if (s.type === "faint") { els[s.side].slot.classList.add("fainted"); banner.textContent = `${s.name} fainted!`; }
    else if (s.type === "turn") { banner.textContent = `— Turn ${s.n} —`; }
    if (s.readIdx != null) revealRead(s.readIdx);
  }
  const DELAY = { turn: 260, banner: 820, hp: 540, switch: 720, faint: 760 };

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
  function start() { if (playing) return; playing = true; playBtn.textContent = "⏸ Pause"; loop(); }
  function stop() { playing = false; playBtn.textContent = "▶ Play"; clearTimeout(timer); }
  function reset() {
    stop(); i = 0; rp = 0; readsEl.innerHTML = ""; lastRead = null;
    banner.textContent = "Press ▶ to run the battle.";
    els.p1.nm.textContent = "—"; els.p2.nm.textContent = "—";
    els.p1.img.removeAttribute("src"); els.p2.img.removeAttribute("src");
    setHp("p1", 100); setHp("p2", 100);
    els.p1.slot.classList.remove("fainted"); els.p2.slot.classList.remove("fainted");
  }
  playBtn.onclick = () => (playing ? stop() : start());
  stepBtn.onclick = () => { stop(); one(); };
  restartBtn.onclick = reset;
  reset();
})();
