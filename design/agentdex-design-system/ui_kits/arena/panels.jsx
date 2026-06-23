// Arena UI kit screens — composes the AgentDex DS components.
const DS = window.AgentDexDesignSystem_26893a;
const { Button, Chip, Avatar, TypeBadge, Tier, StatusPill,
        HPBar, StatBar, MoveButton, AgentCard,
        MetricStat, Tabs, LogLine } = DS;

const HexMark = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={{ color: 'var(--accent-primary)' }}>
    <path d="M12 2l8.66 5v10L12 22l-8.66-5V7L12 2z" stroke="currentColor" strokeWidth="1.6" />
    <path d="M12 7l4.33 2.5v5L12 17l-4.33-2.5v-5L12 7z" fill="currentColor" opacity=".25" />
  </svg>
);

// ── Panel chrome shared by every arena card ──────────────────────────
function Panel({ title, zh, right, children, bodyStyle, style }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, background: 'var(--surface-card)', border: '1px solid var(--border-default)', borderRadius: 'var(--r-lg)', overflow: 'hidden', ...style }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 14px', borderBottom: '1px solid var(--border-default)', flexShrink: 0 }}>
        <h3 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
          {title}{zh && <span style={{ fontFamily: 'var(--font-zh)', marginLeft: 7, color: 'var(--text-faint)' }}>{zh}</span>}
        </h3>
        {right && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-faint)' }}>{right}</div>}
      </div>
      <div style={{ padding: 14, overflow: 'auto', minHeight: 0, flex: 1, ...bodyStyle }}>{children}</div>
    </div>
  );
}

// ── Topbar ────────────────────────────────────────────────────────────
function Topbar({ owner }) {
  return (
    <header style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '0 18px', height: 'var(--topbar-h)', borderBottom: '1px solid var(--border-default)', background: 'linear-gradient(#11141c,#0e1018)', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontWeight: 700, letterSpacing: '.02em' }}>
        <HexMark />
        <span style={{ color: 'var(--text-strong)' }}>agentdex<span style={{ color: 'var(--text-accent)' }}>/arena</span></span>
      </div>
      <Chip>build-ahead · fixtures</Chip>
      <div style={{ flex: 1 }} />
      <Chip tone="ok">◇ INVITE BETA</Chip>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
        <Avatar label={owner.initial} size={28} />
        <div style={{ fontSize: 12 }}>
          <div style={{ color: 'var(--text-strong)' }}>{owner.name}</div>
          <div style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>{owner.gh}</div>
        </div>
      </div>
    </header>
  );
}

// ── Roster rail ─────────────────────────────────────────────────────────
function RosterRail({ roster, selId, onSelect }) {
  return (
    <aside style={{ borderRight: '1px solid var(--border-default)', background: 'var(--surface-card)', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 14px 9px', borderBottom: '1px solid var(--border-default)' }}>
        <h2 style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>My Agents <span style={{ fontFamily: 'var(--font-zh)' }}>阵容</span></h2>
        <Button variant="ghost" size="sm">+ new</Button>
      </div>
      <div style={{ overflow: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 6, minHeight: 0 }}>
        {roster.map((a) => (
          <AgentCard key={a.id} name={a.name} types={a.types} gen={a.gen} status={a.status}
            pending={a.pending} rating={a.elo} selected={a.id === selId} onClick={() => onSelect(a.id)} />
        ))}
      </div>
    </aside>
  );
}

// ── Agent Pane (genome HUD) ─────────────────────────────────────────────
function AgentPane({ agent }) {
  const [tab, setTab] = React.useState('genome');
  const g = agent.genome;
  return (
    <Panel title="Agent" zh="智能体" right={<Tier tier={agent.tier} />}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 13 }}>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700, color: 'var(--text-strong)' }}>{agent.name}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: agent.pending ? 'var(--text-winner)' : 'var(--text-accent)', border: `1px solid ${agent.pending ? 'rgba(244,183,49,.4)' : 'rgba(166,226,46,.4)'}`, borderRadius: 5, padding: '1px 6px' }}>gen {agent.gen}</span>
        <div style={{ display: 'flex', gap: 4, marginLeft: 'auto' }}>{agent.types.map((t) => <TypeBadge key={t} type={t} size="sm" />)}</div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 9, marginBottom: 14 }}>
        <MetricStat label="ELO" zh="积分" value={agent.elo} sub={`±${agent.rd} RD`} tone="elo" />
        <MetricStat label="Win rate" zh="胜率" value={`${agent.wr}%`} sub={`${agent.win}–${agent.loss}`} tone="win" />
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[
        { id: 'genome', label: 'Genome', zh: '基因' },
        { id: 'stats', label: 'Stats', zh: '数值' },
        { id: 'prompt', label: 'Prompt', zh: '提示' },
      ]} />
      <div style={{ paddingTop: 13 }}>
        {tab === 'genome' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {Object.entries(g).map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                <span style={{ color: 'var(--text-muted)' }}>{k}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, border: '1px solid var(--border-default)', borderRadius: 5, padding: '1px 7px', color: (v === 'on' || v === 'aggressive') ? 'var(--text-accent)' : 'var(--text-body)', background: (v === 'on' || v === 'aggressive') ? 'var(--lime-soft)' : 'transparent', borderColor: (v === 'on' || v === 'aggressive') ? 'rgba(166,226,46,.4)' : 'var(--border-default)' }}>{String(v)}</span>
              </div>
            ))}
          </div>
        )}
        {tab === 'stats' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <StatBar label="HP" zh="生命" value={agent.stats.hp} max={450} />
            <StatBar label="Atk" zh="攻击" value={agent.stats.atk} />
            <StatBar label="Def" zh="防御" value={agent.stats.def} />
            <StatBar label="SpA" zh="特攻" value={agent.stats.spa} highlight={agent.stats.spa >= 140} />
            <StatBar label="SpD" zh="特防" value={agent.stats.spd} />
            <StatBar label="Spe" zh="速度" value={agent.stats.spe} highlight={agent.stats.spe >= 135} />
          </div>
        )}
        {tab === 'prompt' && (
          agent.prompt
            ? <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, lineHeight: 1.5, color: 'var(--text-body)', background: 'var(--surface-well)', border: '1px solid var(--border-default)', borderLeft: '3px solid var(--accent-primary)', borderRadius: 7, padding: '9px 11px' }}>{agent.prompt}</div>
            : <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-winner)', background: 'var(--gold-soft)', border: '1px dashed rgba(244,183,49,.4)', borderRadius: 7, padding: 11 }}>No prompt yet — evolution pending. 进化待定。</div>
        )}
      </div>
    </Panel>
  );
}

Object.assign(window, { Panel, Topbar, RosterRail, AgentPane, HexMark });
