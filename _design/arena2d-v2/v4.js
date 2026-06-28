/* arena2d v4 — focus plane + neuron-core mind readout.
 * Top: battle viewer + vertical decision tree. The focus turn slides to the
 * focus window (bottom of the tree); its neuron-core mind readout expands in the
 * fixed horizontal plane below (INPUTS → CANDIDATE FAN → FIRING CORE → CHOSEN). */
(function(){
  const D = window.A2D_V2_DATA;
  const $ = (s,r=document) => r.querySelector(s);

  /* ---------- meta + footer ---------- */
  const tk = D.meta.tokens, tot = tk.cached+tk.uncached+tk.completion;
  $("#m-agent").textContent = D.meta.agent; $("#m-elo").textContent = D.meta.elo_you;
  $("#m-turns").textContent = D.turns.length; $("#m-tokens").textContent = (tot/1000).toFixed(1)+"K";
  $("#m-cost").textContent = "$"+D.meta.cost_usd.toFixed(3);
  $("#tk-total").textContent = tot.toLocaleString();
  $("#tk-cached").style.width=(tk.cached/tot*100).toFixed(1)+"%"; $("#tk-uncached").style.width=(tk.uncached/tot*100).toFixed(1)+"%"; $("#tk-completion").style.width=(tk.completion/tot*100).toFixed(1)+"%";
  $("#tk-cached-n").textContent=tk.cached.toLocaleString(); $("#tk-uncached-n").textContent=tk.uncached.toLocaleString(); $("#tk-completion-n").textContent=tk.completion.toLocaleString();
  $("#tk-cost").textContent="$"+D.meta.cost_usd.toFixed(3);
  $("#pv-fused").textContent=D.meta.fused_hash+"…"; $("#pv-prompt").textContent=D.meta.prompt_hash+"…";
  $("#pv-result").textContent=D.meta.result+" ("+D.meta.result_note+")"; $("#pv-replay").href=D.meta.replay_url;
  $("#acl-badge").className="acl "+D.meta.acl; $("#acl-badge").textContent=D.meta.acl==="spectator"?"SPECTATOR · public projection":"OWNER · full info";
  const sg=$("#pv-signed"); if(sg) sg.textContent=D.meta.agent;

  /* ---------- team rail (shrunk; active mon highlights with the focus turn) ---------- */
  D.team_you.forEach(m => { const el=document.createElement("div"); el.className="mon"; el.dataset.species=m.species;
    el.classList.toggle("faint",(m.hp??100)<=0);
    el.innerHTML=`<img src="https://play.pokemonshowdown.com/sprites/ani/${m.species}.gif" alt="${m.name}">`
      +`<div class="mon-id"><div class="mn"><span class="nm-t">${m.name}</span></div><div class="mhp"><i style="width:${m.hp}%"></i></div></div>`;
    $("#team-grid").appendChild(el); });
  $("#opp-rev").textContent = D.team_opp_revealed.map(m=>m.name).join(" · ");

  /* active-mon highlight: the focus turn's `you` glows cyan + shows its live HP */
  function markActiveTeam(turn){
    document.querySelectorAll(".team-rail .mon").forEach(el=>{
      const isActive = el.dataset.species===turn.you.species;
      el.classList.toggle("active", isActive);
      const mn=el.querySelector(".mn"), mk=mn.querySelector(".act-mark"); if(mk) mk.remove();
      if(isActive){
        const hpbar=el.querySelector(".mhp"); hpbar.firstElementChild.style.width=turn.you.hp+"%";
        hpbar.className="mhp"+(turn.you.hp<=20?" low":turn.you.hp<=50?" warn":"");
        const s=document.createElement("span"); s.className="act-mark"; s.textContent="▸ ACTIVE"; mn.appendChild(s);
      }
    });
  }

  /* ---------- type helpers ---------- */
  const CHART=D.type_chart;
  const mult1=(a,d)=>{const c=CHART[a];if(!c)return 1;if(c.imm.includes(d))return 0;if(c.sup.includes(d))return 2;if(c.res.includes(d))return 0.5;return 1;};
  const eff=(a,defs)=>(defs||[]).reduce((m,d)=>m*mult1(a,d),1);
  const typePills=ts=>(ts||[]).map(t=>`<span class="ty ${t}"><span>${t}</span></span>`).join(" ");
  const mulStr=e=>e===0?"×0":e===0.25?"×¼":e===0.5?"×½":"×"+e;
  const UTILITY=new Set(["stealthrock","thunderwave","chillyreception","dragontail","swordsdance","rapidspin","encore"]);

  function weightOf(turn, a){
    if(a.kind==="move" && a.type && !UTILITY.has(a.id)){
      const e=eff(a.type,turn.opp.types), stab=turn.you.types.includes(a.type)?1.5:1.0, w=+(e*stab).toFixed(2);
      const word=e===0?"immune":e>=4?"4× super":e>=2?"super-eff":e<=0.5?"resisted":"neutral";
      return {w, calc:`${a.type}→${turn.opp.types.join("/")} ${mulStr(e)} ${word} · STAB ×${stab}`, cls:e>=2?"sup":e<=0.5?"res":""};
    }
    if(a.kind==="move" && UTILITY.has(a.id))
      return {w:0.6, calc:`utility · ${a.id==="stealthrock"?"sets hazard":a.id==="thunderwave"?"status":"tempo"} · no damage`, cls:"piv"};
    return {w:1.6, calc:`defensive pivot · resist score (illustrative)`, cls:"piv"};
  }

  /* ---------- neuron-core mind readout for a turn ---------- */
  function renderCore(turnIdx){
    const turn=D.turns[turnIdx], chosen=turn.chosen;
    $("#mr-turn").textContent=turn.n; $("#mr-dec").textContent=turn.n;
    $("#lens-turn").textContent=turn.n;
    $("#mr-prov").textContent=`[LIVE · ${D.meta.llm} · ${turn.time}]`;
    markActiveTeam(turn);

    // INPUTS
    $("#in-opp-nm").textContent=turn.opp.name; $("#in-opp-ty").innerHTML=typePills(turn.opp.types);
    $("#in-opp-hp").style.width=turn.opp.hp+"%"; $("#in-opp-pct").textContent=turn.opp.hp+"%";
    $("#in-you-nm").textContent=turn.you.name; $("#in-you-ty").innerHTML=typePills(turn.you.types);
    $("#in-you-hp").style.width=turn.you.hp+"%"; $("#in-you-pct").textContent=turn.you.hp+"%";
    $("#in-field").textContent = turn.field || "no hazards · no weather";

    // FAN — chosen + candidates, each weighted, sorted by weight desc
    const items=[{a:chosen,isChosen:true},...turn.candidates.map(a=>({a,isChosen:false}))]
      .map(o=>({...o,...weightOf(turn,o.a)}));
    const maxW=Math.max(...items.map(i=>i.w));
    const sorted=[...items].sort((x,y)=>y.w-x.w);
    const chosenItem=items.find(i=>i.isChosen);
    $("#fan").innerHTML=sorted.map((it,i)=>{
      const sw=it.a.kind==="switch";
      return `<div class="cand ${it.isChosen?'chosen':''}" id="c${i}" data-chosen="${it.isChosen}">
        ${it.isChosen?'<div class="chosenflag">◀ codex pick</div>':''}
        <div class="cr"><span class="cm ${sw?'switch':''}">${it.a.label.replace(/^→\s*/,'')}</span>${it.a.type?`<span class="ty ${it.a.type}"><span>${it.a.type}</span></span>`:`<span class="ty Normal"><span>${sw?'switch':'util'}</span></span>`}</div>
        <div class="calc">${it.calc} = <b>${it.w.toFixed(1)}</b></div>
        <div class="wrow"><div class="wbar"><i class="${it.cls}" style="width:${Math.max(8,it.w/Math.max(maxW,1)*100)}%"></i></div><span class="wnum">${it.w.toFixed(1)}</span></div>
      </div>`;
    }).join("");

    // CORE
    $("#core-w").textContent=chosenItem.w.toFixed(1);
    $("#core-l").textContent=(chosen.type?chosen.type:chosen.kind==="switch"?"pivot":"util")+" ▸";
    const isMax=Math.abs(chosenItem.w-maxW)<0.01;
    $("#core-threat").textContent=isMax?"argmax = codex pick ✓":"codex pick ≠ type-max";
    const dv=$("#core-diverge");
    if(isMax){ dv.classList.remove("on"); dv.textContent=""; }
    else { dv.classList.add("on"); dv.textContent="codex overrode type-score ↓ (reads hazards / pivots / long-game)"; }

    // OUTPUT
    $("#out-act").textContent=chosen.label.replace(/^→\s*/,(chosen.kind==="switch"?"switch → ":""));
    $("#out-into").textContent=(chosen.kind==="switch"?"vs ":"into ")+turn.opp.name;
    $("#out-ratio").innerHTML=`<b>"</b>${chosen.rationale}<b>"</b>`;
    $("#out-outcome").innerHTML=`<span class="ochip ${turn.outcome}">${turn.outcome}</span> resolved → <span style="color:var(--ink)">${turn.outcomeText}</span>`;

    // TICKER (honest: from log state, not fabricated telemetry)
    $("#ticker").innerHTML=[
      {v:turn.opp.hp+"%",k:"opp HP",dim:false},
      {v:turn.you.hp+"%",k:"your HP",dim:false},
      {v:turn.outcome,k:"primitive",dim:false},
      {v:chosen.kind.toUpperCase(),k:"action kind",dim:true},
      {v:(turn.candidates.length+1),k:"considered",dim:true},
    ].map(m=>`<div class="metric ${m.dim?'dim':''}"><div class="mv">${m.v}</div><div class="mk">${m.k}</div></div>`).join("");

    requestAnimationFrame(drawWires);
  }

  /* ---------- SVG wires: candidate dendrites → core → output ---------- */
  function center(el,side){const g=$("#graph").getBoundingClientRect(),b=el.getBoundingClientRect();
    return {x:(side==='r'?b.right:side==='l'?b.left:(b.left+b.right)/2)-g.left, y:b.top-g.top+b.height/2};}
  function curve(a,z,cls,w,op){const mx=(a.x+z.x)/2,p=document.createElementNS('http://www.w3.org/2000/svg','path');
    p.setAttribute('d',`M${a.x},${a.y} C${mx},${a.y} ${mx},${z.y} ${z.x},${z.y}`);p.setAttribute('class',cls);
    if(w)p.setAttribute('stroke-width',w); if(op!=null)p.setAttribute('opacity',op); $("#wires").appendChild(p);}
  function drawWires(){
    const svg=$("#wires"); [...svg.querySelectorAll('path,circle')].forEach(n=>n.remove());
    const you=center($("#nYou"),'r'), opp=center($("#nOpp"),'r');
    const core=$("#nCore"), coreL=center(core,'l'), coreR=center(core,'r'), out=center($("#nOut"),'l');
    const cands=[...document.querySelectorAll('.cand')];
    cands.forEach(c=>curve(you,center(c,'l'),'wire ctx'));
    curve(opp,coreL,'wire ctx opp');
    let maxW=0; cands.forEach(c=>{const w=parseFloat(c.querySelector('.wnum').textContent)||0; if(w>maxW)maxW=w;});
    cands.forEach(c=>{const cr=center(c,'r'),w=parseFloat(c.querySelector('.wnum').textContent)||0;
      if(c.dataset.chosen==="true") curve(cr,coreL,'wire cand chosen');
      else curve(cr,coreL,'wire cand',(1.1+(w/Math.max(maxW,1))*2.6).toFixed(1),(0.22+w/Math.max(maxW,1)*0.4).toFixed(2));});
    curve(coreR,out,'wire axon');
    const tokC=document.createElementNS('http://www.w3.org/2000/svg','circle');
    const chosenEl=document.querySelector('.cand[data-chosen="true"]'); if(chosenEl){const cr=center(chosenEl,'r');
      tokC.setAttribute('cx',(cr.x+coreL.x)/2);tokC.setAttribute('cy',(cr.y+coreL.y)/2);tokC.setAttribute('r',3.6);tokC.setAttribute('class','tok');svg.appendChild(tokC);}
    const tokA=document.createElementNS('http://www.w3.org/2000/svg','circle');
    tokA.setAttribute('cx',(coreR.x+out.x)/2);tokA.setAttribute('cy',(coreR.y+out.y)/2);tokA.setAttribute('r',3.6);tokA.setAttribute('class','tok real');svg.appendChild(tokA);
  }
  window.addEventListener('resize',()=>requestAnimationFrame(drawWires));

  // expose for the tree/cadence module (loaded next)
  window.__A2D = { D, $, renderCore, drawWires, eff, typePills };
})();
