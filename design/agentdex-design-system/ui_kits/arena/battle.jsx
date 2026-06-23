// Arena — the live battle scene, evolution lineage, ladder, and root App.
const DSb = window.AgentDexDesignSystem_26893a;

function Mon({ mon, side, fainted }) {
  const isP2 = side === 'p2';
  return (
    <div style={{ background: 'var(--surface-raised)', border: '1px solid var(--border-default)', borderRadius: 9, padding: 10, display: 'flex', flexDirection: 'column', gap: 7, opacity: fainted ? 0.5 : 1, filter: fainted ? 'grayscale(.6)' : 'none', transition: 'opacity var(--dur-3), filter var(--dur-3)', textAlign: isP2 ? 'right' : 'left' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{mon.trainer}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexDirection: isP2 ? 'row-reverse' : 'row' }}>
        <span style={{ width: 34, height: 34, borderRadius: 8, background: 'linear-gradient(160deg,#2a3344,#1a1f2b)', border: '1px solid var(--border-default)', display: 'grid', placeItems: 'center', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-strong)' }}>{mon.token}</span>
        <span style={{ fontWeight: 600, fontSize: 15, flex: 1, color: 'var(--text-strong)' }}>{mon.species}</span>
        {mon.status && <DSb.StatusPill status={mon.status.toUpperCase()} />}
      </div>
      <div style={{ display: 'flex', gap: 4, justifyContent: isP2 ? 'flex-end' : 'flex-start' }}>{mon.types.map((t) => <DSb.TypeBadge key={t} type={t} size="sm" />)}</div>
      <HPBarMini cur={mon.hp} max={mon.max} reverse={isP2} />
    </div>
  );
}

function HPBarMini({ cur, max, reverse }) {
  const pct = Math.max(0, Math.min(100, (cur / max) * 100));
  const st = pct <= 20 ? 'low' : pct <= 45 ? 'warn' : 'ok';
  const color = { ok: 'var(--hp-ok)', warn: 'var(--hp-warn)', low: 'var(--hp-low)' }[st];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexDirection: reverse ? 'row-reverse' : 'row' }}>
      <div style={{ flex: 1, height: 9, background: 'var(--surface-well)', borderRadius: 999, overflow: 'hidden', border: '1px solid var(--border-default)' }}>
        <div style={{ height: '100%', width: `${pct}%`, marginLeft: reverse ? 'auto' : 0, background: color, borderRadius: 999, transition: 'width var(--dur-hp) ease, background-color var(--dur-3)' }} />
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', minWidth: 38, textAlign: reverse ? 'left' : 'right' }}>{Math.round(pct)}%</span>
    </div>
  );
}

function BattleScene({ battle }) {
  const [moveBanner, setMoveBanner] = React.useState(null);
  const tickerRef = React.useRef(null);
  const fire = (name) => {
    setMoveBanner(name);
    setTimeout(() => setMoveBanner(null), 1100);
  };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, background: 'var(--surface-card)', border: '1px solid var(--border-default)', borderRadius: 'var(--r-lg)', overflow: 'hidden', flex: 1 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 14px', borderBottom: '1px solid var(--border-default)' }}>
        <h3 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>Live Battle <span style={{ fontFamily: 'var(--font-zh)' }}>实况对战</span></h3>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-faint)' }}>{battle.format}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: 13, minHeight: 0, flex: 1, position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12 }}>
          <span style={{ color: 'var(--text-winner)', fontFamily: 'var(--font-mono)' }}>turn {battle.turn}</span>
          <span style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <DSb.Chip tone="live">LIVE</DSb.Chip>
          </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 10, alignItems: 'stretch' }}>
          <Mon mon={battle.p1} side="p1" />
          <span style={{ alignSelf: 'center', color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>vs</span>
          <Mon mon={battle.p2} side="p2" />
        </div>
        {moveBanner && (
          <div style={{ position: 'absolute', top: '42%', left: '50%', transform: 'translate(-50%,0)', background: 'rgba(20,24,34,.94)', border: '1px solid var(--accent-primary)', color: 'var(--text-strong)', fontWeight: 700, padding: '7px 16px', borderRadius: 8, boxShadow: 'var(--glow-active)', animation: 'adx-banner .2s var(--ease-bounce)' }}>{moveBanner}!</div>
        )}
        <div ref={tickerRef} style={{ flex: 1, overflow: 'auto', background: 'var(--surface-well)', border: '1px solid var(--border-default)', borderRadius: 8, padding: 8, minHeight: 70 }}>
          {battle.log.map((l, i) => (
            <LogLineMini key={i} {...l} />
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, borderTop: '1px solid var(--border-default)', paddingTop: 10 }}>
          {battle.moves.map((m) => (
            <DSb.MoveButton key={m.name} {...m} onClick={() => fire(m.name)} />
          ))}
        </div>
      </div>
      <style>{`@keyframes adx-banner{from{opacity:0;transform:translate(-50%,-6px)}to{opacity:1;transform:translate(-50%,0)}}
        @media (prefers-reduced-motion: reduce){[style*="adx-banner"]{animation:none!important}}`}</style>
    </div>
  );
}

function LogLineMini({ ts, tone, label, text }) {
  return <DSb.LogLine ts={ts} tone={tone} label={label}>{text}</DSb.LogLine>;
}

function EvolutionPanel({ evo }) {
  return (
    <Panel title="Evolution" zh="进化">
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 24, fontWeight: 600, color: 'var(--text-accent)', lineHeight: 1.1 }}>gen {evo.from} → {evo.to}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-winner)' }}>+{evo.eloUp} ELO {evo.ciSig ? '· CI significant' : ''}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, height: 84, paddingBottom: 6, borderBottom: '1px solid var(--border-default)' }}>
        {evo.cols.map((c) => (
          <div key={c.gen} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, flex: 1, justifyContent: 'flex-end' }}>
            <span style={{ fontSize: 10, color: c.kept ? 'var(--text-accent)' : 'var(--text-faint)' }}>{c.kept ? '✓ kept' : 'pruned'}</span>
            <div style={{ width: '100%', height: c.val, maxHeight: 64, borderRadius: '3px 3px 0 0', background: c.kept ? 'linear-gradient(180deg,#b9f23a,#6f9a18)' : 'linear-gradient(180deg,#3a5a1f,#22301a)' }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, color: 'var(--text-faint)' }}>g{c.gen}</span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 11, fontFamily: 'var(--font-mono)', fontSize: 12, background: 'var(--surface-well)', border: '1px solid rgba(166,226,46,.4)', borderLeft: '3px solid var(--accent-primary)', borderRadius: 7, padding: '9px 11px' }}>
        <div style={{ color: 'var(--text-accent)', fontWeight: 600, marginBottom: 4 }}>{evo.mutation.head}</div>
        <div style={{ color: 'var(--text-body)', lineHeight: 1.45 }}>{evo.mutation.body}</div>
      </div>
    </Panel>
  );
}

function LadderPanel({ ladder }) {
  return (
    <Panel title="Ladder" zh="天梯" right="gen9randombattle">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {ladder.map((r) => (
          <div key={r.rank} style={{ display: 'grid', gridTemplateColumns: '26px 1fr auto auto', alignItems: 'center', gap: 10, padding: '7px 10px', borderRadius: 'var(--r-sm)', background: r.you ? 'var(--lime-soft)' : 'transparent', border: r.you ? '1px solid rgba(166,226,46,.3)' : '1px solid transparent' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: r.rank === 1 ? 'var(--text-winner)' : 'var(--text-faint)' }}>{r.rank}</span>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 13, fontWeight: r.you ? 700 : 500, color: r.you ? 'var(--text-strong)' : 'var(--text-body)' }}>{r.name}{r.you && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-accent)', marginLeft: 6 }}>you</span>}</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-winner)' }}>{r.elo}</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', minWidth: 34, textAlign: 'right' }}>{r.wr}%</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function App() {
  const D = window.ARENA_DATA;
  const [selId, setSelId] = React.useState(D.roster[0].id);
  const agent = D.roster.find((a) => a.id === selId) || D.roster[0];
  return (
    <div style={{ display: 'grid', gridTemplateRows: 'var(--topbar-h) 1fr', height: '100vh', minHeight: 680 }}>
      <Topbar owner={D.owner} />
      <div style={{ display: 'grid', gridTemplateColumns: 'var(--rail-roster) 1fr', minHeight: 0 }}>
        <RosterRail roster={D.roster} selId={selId} onSelect={setSelId} />
        <section style={{ display: 'grid', gridTemplateRows: 'minmax(0,1.32fr) minmax(0,1fr)', gap: 12, padding: 12, minHeight: 0 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(300px,.92fr) minmax(360px,1.08fr)', gap: 12, minHeight: 0 }}>
            <div style={{ display: 'flex', minHeight: 0 }}><AgentPane agent={agent} /></div>
            <div style={{ display: 'flex', minHeight: 0 }}><BattleScene battle={D.battle} /></div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1.15fr .85fr', gap: 12, minHeight: 0 }}>
            <div style={{ display: 'flex', minHeight: 0 }}><EvolutionPanel evo={D.evolution} /></div>
            <div style={{ display: 'flex', minHeight: 0 }}><LadderPanel ladder={D.ladder} /></div>
          </div>
        </section>
      </div>
    </div>
  );
}

Object.assign(window, { BattleScene, EvolutionPanel, LadderPanel, App });
