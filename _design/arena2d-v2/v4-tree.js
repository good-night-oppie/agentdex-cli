/* arena2d v4 — vertical tree + viewport + subtitle + auto-cadence + focus-slide.
 * The focus turn slides to the focus window (bottom of the tree); renderCore()
 * (from v4.js) expands its neuron-core mind readout in the fixed plane below. */
(function(){
  const { D, $, renderCore } = window.__A2D;
  const typePills = ts => (ts||[]).map(t=>`<span class="ty ${t}"><span>${t}</span></span>`).join(" ");
  const RM = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  const reduce = () => !!(RM && RM.matches);

  /* ---------- viewport ---------- */
  function paintViewport(turn){
    $("#vp-turn").textContent=`DEC ${turn.n} · TURN ${turn.n}`;
    $("#you-img").src=`https://play.pokemonshowdown.com/sprites/ani-back/${turn.you.species}.gif`;
    $("#opp-img").src=`https://play.pokemonshowdown.com/sprites/ani/${turn.opp.species}.gif`;
    $("#you-img").alt=turn.you.name; $("#opp-img").alt=turn.opp.name;
    $("#you-nm").textContent=turn.you.name; $("#opp-nm").textContent=turn.opp.name;
    $("#you-hp").textContent=turn.you.hp+"%"; $("#opp-hp").textContent=turn.opp.hp+"%";
    $("#you-bar").firstElementChild.style.width=turn.you.hp+"%"; $("#opp-bar").firstElementChild.style.width=turn.opp.hp+"%";
    $("#you-bar").className="bar"+(turn.you.hp<=20?" low":turn.you.hp<=50?" warn":"");
    $("#opp-bar").className="bar"+(turn.opp.hp<=20?" low":turn.opp.hp<=50?" warn":"");
  }

  /* ---------- subtitle (codex reason as caption) ---------- */
  let typer=null;
  function typeSubtitle(text, stream){
    const sub=$("#cap-sub"); if(typer){clearInterval(typer);typer=null;}
    if(!stream){sub.textContent=text;return;}
    sub.innerHTML='<span class="cursor">&nbsp;</span>';
    const words=text.split(/(\s+)/); let i=0;
    typer=setInterval(()=>{ if(i>=words.length){clearInterval(typer);typer=null;sub.textContent=text;return;}
      sub.innerHTML=words.slice(0,++i).join("")+'<span class="cursor">&nbsp;</span>'; },38);
  }
  function renderSubtitle(turn, stream){
    const sw=turn.chosen.kind==="switch";
    $("#cap-head").innerHTML=`<span>DEC ${turn.n}</span><span class="ch-spk">codex ▸</span>`
      +`<span class="ch-act ${sw?'switch':''}">${turn.you.name} · ${turn.chosen.label}</span>`
      +`<span class="ch-oc ${turn.outcome}">${turn.outcome}</span>`;
    typeSubtitle(turn.chosen.rationale, stream);
  }

  /* ---------- build vertical tree ---------- */
  const vtree=$("#vtree");
  const root=document.createElement("div"); root.className="vroot";
  root.innerHTML=`<span class="rdot"></span>START · gen9oulongtimer`; vtree.appendChild(root);

  D.turns.forEach((turn,i)=>{
    const lvl=document.createElement("div"); lvl.className="lvl"+(turn.candidates.length?" has-cands":""); lvl.dataset.idx=i;
    const sw=turn.chosen.kind==="switch";
    lvl.innerHTML=`
      <div class="spine-row" role="button" tabindex="0" aria-expanded="false" aria-label="Turn ${turn.n}: ${turn.chosen.label} — ${turn.outcome}. Activate to inspect this decision; ${turn.candidates.length} considered alternative${turn.candidates.length===1?'':'s'}.">
        <span class="dot ${turn.outcome}">${turn.n}</span>
        <div class="srow-top"><span class="tn">T${turn.n}</span><span class="lab ${sw?'switch':''}">${turn.chosen.label}</span><span class="oc ${turn.outcome}">${turn.outcome}</span></div>
        <div class="srow-meta"><span class="pb">[LIVE · ${D.meta.llm} · ${turn.time}]</span><span class="au">[?]</span><span class="toggle"><span class="car">▸</span> ${turn.candidates.length} considered</span></div>
      </div>
      <div class="sibs">${turn.candidates.map((c,ci)=>`
        <div class="sib" data-ci="${ci}" role="button" tabindex="0" aria-label="Rejected candidate: ${c.label}. ${c.rationale}"><span class="sdot"></span><span class="smark">rejected</span>
          <div class="sname ${c.kind==='switch'?'switch':''}">${c.label}</div><div class="srat">${c.rationale}</div></div>`).join("")}</div>`;
    vtree.appendChild(lvl);
    const sr=lvl.querySelector(".spine-row");
    const openLevel=()=>{
      pause();
      // re-clicking the already-focused-open row collapses it; focusTurn force-opens (auto-cadence spotlight relies on that)
      const collapse = lvl.classList.contains("is-focus") && lvl.classList.contains("open");
      focusTurn(i,false);
      if(collapse){ lvl.classList.remove("open"); sr.setAttribute("aria-expanded","false"); }
    };
    sr.addEventListener("click",openLevel);
    sr.addEventListener("keydown",e=>{ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); openLevel(); } });
    lvl.querySelectorAll(".sib").forEach(s=>{
      const pickSib=()=>{ pause(); focusTurn(i,false);
        document.querySelectorAll(".sib.sel-sib").forEach(x=>x.classList.remove("sel-sib")); // exclusive selection — one rejected candidate highlighted at a time
        s.classList.add("sel-sib"); };
      s.addEventListener("click",e=>{ e.stopPropagation(); pickSib(); });
      s.addEventListener("keydown",e=>{ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); e.stopPropagation(); pickSib(); } });
    });
  });
  $("#exp-all").addEventListener("click",()=>{pause();document.querySelectorAll(".lvl").forEach(l=>l.classList.add("open"));});
  $("#col-all").addEventListener("click",()=>document.querySelectorAll(".lvl").forEach(l=>l.classList.remove("open")));

  /* ---------- A3 lens connector: the focused turn (focus-rail) → its readout (lens-tag) ---------- */
  const mainEl=document.querySelector("main.v4"), lc=$("#lens-connector");
  function drawLensConnector(){
    if(!lc||!mainEl) return;
    if(getComputedStyle(lc).display==="none"){ lc.innerHTML=""; return; }   // collapsed breakpoint
    const railEl=$("#focus-rail"), lensEl=$("#lens-tag");
    if(!railEl||!lensEl) return;
    const m=mainEl.getBoundingClientRect(), r=railEl.getBoundingClientRect(), l=lensEl.getBoundingClientRect();
    const ax=r.left+r.width*0.5-m.left, ay=r.bottom-m.top;     // bottom-center of focus window
    const bx=l.left+l.width*0.5-m.left, by=l.top-m.top;        // top-center of lens tag
    const midY=ay+(by-ay)*0.5;
    const d=`M${ax.toFixed(1)},${ay.toFixed(1)} C${ax.toFixed(1)},${midY.toFixed(1)} ${bx.toFixed(1)},${midY.toFixed(1)} ${bx.toFixed(1)},${(by-7).toFixed(1)}`;
    lc.setAttribute("width",m.width); lc.setAttribute("height",m.height); lc.setAttribute("viewBox",`0 0 ${m.width} ${m.height}`);
    lc.innerHTML=`<defs><marker id="lc-arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--cyan)"/></marker></defs><path d="${d}" class="lc-path" marker-end="url(#lc-arrow)"/>`;
  }

  /* ---------- focus = slide to window + render neuron core ---------- */
  let cur=0;
  function focusTurn(i, stream){
    cur=Math.max(0,Math.min(D.turns.length-1,i));
    const turn=D.turns[cur];
    document.querySelectorAll(".lvl").forEach((l,k)=>{ const f=k===cur; l.classList.toggle("is-focus",f); l.classList.toggle("open",f);
      const sr=l.querySelector(".spine-row"); if(sr) sr.setAttribute("aria-expanded",String(l.classList.contains("open"))); });
    // slide the focused level to the bottom of the tree viewport (the focus window)
    const el=document.querySelectorAll(".lvl")[cur]; if(el) el.scrollIntoView({block:"end",behavior:reduce()?"auto":"smooth"});
    $("#fr-turn").textContent="TURN "+turn.n;
    paintViewport(turn);
    renderSubtitle(turn, stream);
    renderCore(cur);
    requestAnimationFrame(drawLensConnector);
  }
  window.addEventListener("resize",()=>requestAnimationFrame(drawLensConnector));

  /* ---------- auto-cadence ---------- */
  let playing=false, timer=null, speed=1; const BASE=4600;
  function tick(){ if(!playing)return; if(cur>=D.turns.length-1){pause();return;} focusTurn(cur+1,true); timer=setTimeout(tick,BASE/speed); }
  function play(){ if(playing)return; playing=true; $("#vp-ctrl").classList.remove("paused"); $("#vp-play").textContent="⏸";
    if(cur>=D.turns.length-1) focusTurn(0,true); timer=setTimeout(tick,BASE/speed); }
  function pause(){ playing=false; if(timer){clearTimeout(timer);timer=null;} $("#vp-ctrl").classList.add("paused"); $("#vp-play").textContent="▶"; }
  window.pause=pause;
  $("#vp-play").addEventListener("click",()=>playing?pause():play());
  $("#vp-spd-btn").addEventListener("click",()=>{ speed=speed===1?2:speed===2?0.5:1; $("#vp-spd").textContent=speed+"×"; if(playing){clearTimeout(timer);timer=setTimeout(tick,BASE/speed);} });
  document.addEventListener("keydown",e=>{
    // Space toggles play ONLY when nothing focusable is focused — otherwise the focused
    // row/button handles its own Enter/Space (no double-fire).
    if(e.key===" " && e.target===document.body){e.preventDefault();playing?pause():play();}
    if(e.key==="ArrowDown"){pause();focusTurn(cur+1,false);} if(e.key==="ArrowUp"){pause();focusTurn(cur-1,false);} });

  /* default: auto-cadence ON from T1 — honor prefers-reduced-motion (no autoplay, no type-stream) */
  if(reduce()){ focusTurn(0,false); pause(); } else { focusTurn(0,true); play(); }
})();
