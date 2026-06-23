// AgentDex GA self-serve — shared funnel chrome (brand mark, stepper, auth shell, fields).
// Everything reads design-system tokens + components so screens stay one coherent surface.
const DS = window.AgentDexDesignSystem_26893a;

// Brand hex mark (same lockup as the Ladder kit).
const Hex = ({ size = 22, color = 'var(--accent-primary)' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={{ color }}>
    <path d="M12 2l8.66 5v10L12 22l-8.66-5V7L12 2z" stroke="currentColor" strokeWidth="1.6" />
    <path d="M12 7l4.33 2.5v5L12 17l-4.33-2.5v-5L12 7z" fill="currentColor" opacity=".25" />
  </svg>
);

// Mono uppercase accent eyebrow.
function Eyebrow({ children, tone = 'var(--text-accent)' }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-mono)', fontSize: 12, color: tone, textTransform: 'uppercase', letterSpacing: '.12em' }}>{children}</span>
  );
}

// 中文 gloss — trails the EN term, never replaces it. Always --font-zh.
function Gloss({ children, size = 13 }) {
  return <span style={{ fontFamily: 'var(--font-zh)', fontSize: size, color: 'var(--text-muted)', fontWeight: 400 }}>{children}</span>;
}

// Labeled input field. Uncontrolled by default (static prefilled prototype values);
// pass `onChange` to make it a CONTROLLED input that actually submits a value — the
// auth funnel needs the typed email/code to reach the /auth/* backends (was a
// defaultValue-only dead end before F1).
function Field({ label, zh, type = 'text', placeholder, value, onChange, onSubmit, hint, mono, prefix, readOnly, autoComplete }) {
  const controlled = typeof onChange === 'function';
  // controlled → value + onChange (real submit); else defaultValue (prototype static).
  const inputProps = controlled
    ? { value: value == null ? '' : value, onChange: (e) => onChange(e.target.value) }
    : { defaultValue: value };
  return (
    <label style={{ display: 'block', marginBottom: 16 }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 7 }}>
        {label}{zh ? <> <Gloss size={12}>{zh}</Gloss></> : null}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--surface-card)', border: '1px solid var(--border-default)', borderRadius: 'var(--r-sm)', padding: '0 12px', height: 44, boxShadow: 'var(--shadow-sm)' }}>
        {prefix ? <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)' }}>{prefix}</span> : null}
        <input
          type={type} placeholder={placeholder} readOnly={readOnly}
          autoComplete={autoComplete}
          onKeyDown={onSubmit ? (e) => { if (e.key === 'Enter') { e.preventDefault(); onSubmit(); } } : undefined}
          {...inputProps}
          style={{ flex: 1, background: 'transparent', border: 0, outline: 'none', color: 'var(--text-strong)', fontFamily: mono ? 'var(--font-mono)' : 'var(--font-display)', fontSize: 15, height: '100%' }}
        />
      </div>
      {hint ? <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-faint)', marginTop: 6 }}>{hint}</div> : null}
    </label>
  );
}

// The canonical funnel stepper (01 Account → 05 Go live).
function Stepper({ current }) {
  const steps = window.GA.STEPS;
  const idx = steps.findIndex((s) => s.id === current);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0, flexWrap: 'wrap' }}>
      {steps.map((s, i) => {
        const done = i < idx, active = i === idx;
        const dot = done ? 'var(--accent-primary)' : active ? 'var(--accent-primary)' : 'var(--border-strong)';
        const ink = done || active ? 'var(--text-strong)' : 'var(--text-faint)';
        return (
          <React.Fragment key={s.id}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }} title={`${s.label} ${s.zh}`}>
              <span style={{
                width: 22, height: 22, borderRadius: 'var(--r-pill)', flexShrink: 0,
                display: 'grid', placeItems: 'center', fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600,
                border: `1px solid ${active ? 'var(--accent-primary)' : done ? 'var(--accent-primary)' : 'var(--border-strong)'}`,
                background: done ? 'var(--accent-primary)' : active ? 'var(--lime-soft)' : 'transparent',
                color: done ? 'var(--on-accent)' : active ? 'var(--text-accent)' : 'var(--text-faint)',
                boxShadow: active ? 'var(--glow-active)' : 'none',
              }}>{done ? '✓' : s.n}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: ink }}>{s.label}</span>
            </div>
            {i < steps.length - 1 ? <span style={{ width: 26, height: 1, background: 'var(--border-default)', margin: '0 12px' }} /> : null}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// Top funnel bar: brand + live stepper + a prototype screen-jumper (so reviewers click the whole flow).
function FunnelNav({ screen, setScreen, current }) {
  const jumps = [
    ['signup', 'Sign up'], ['login', 'Login'], ['github', 'GitHub'],
    ['enroll', 'Enroll'], ['modes', 'Modes'], ['billing', 'Billing'], ['launch', 'Go live'],
  ];
  return (
    <nav style={{ position: 'sticky', top: 0, zIndex: 20, background: 'color-mix(in srgb, var(--bg) 82%, transparent)', backdropFilter: 'blur(8px)', borderBottom: '1px solid var(--border-default)' }}>
      <div style={{ maxWidth: 1080, margin: '0 auto', padding: '0 24px', height: 58, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, fontWeight: 700, color: 'var(--text-strong)', flexShrink: 0 }}>
          <Hex /> agentdex<span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>/arena</span>
        </div>
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center', overflowX: 'auto' }}><Stepper current={current} /></div>
        <DS.Chip tone="data" style={{ flexShrink: 0 }}>GA · 合作竞争</DS.Chip>
      </div>
      {/* prototype-only screen jumper */}
      <div style={{ maxWidth: 1080, margin: '0 auto', padding: '0 24px 8px', display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--text-faint)', marginRight: 4 }}>prototype ›</span>
        {jumps.map(([id, lbl]) => (
          <button key={id} onClick={() => setScreen(id)} style={{
            cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '.06em', textTransform: 'uppercase',
            padding: '3px 9px', borderRadius: 'var(--r-xs)',
            border: `1px solid ${screen === id ? 'var(--accent-primary)' : 'var(--border-default)'}`,
            background: screen === id ? 'var(--lime-soft)' : 'transparent',
            color: screen === id ? 'var(--text-accent)' : 'var(--text-muted)',
          }}>{lbl}</button>
        ))}
      </div>
    </nav>
  );
}

// Centered two-column shell for account screens (form left, "why" rail right).
function AuthShell({ eyebrow, title, titleAccent, sub, children, aside, footnote }) {
  return (
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: '56px 24px 40px', display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,380px)', gap: 40, alignItems: 'start' }}>
      <div style={{ maxWidth: 460 }}>
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(28px,4vw,40px)', lineHeight: 1.08, letterSpacing: 'var(--ls-tight,-.02em)', fontWeight: 700, margin: '16px 0 10px', color: 'var(--text-strong)', textWrap: 'balance' }}>
          {title} {titleAccent ? <span style={{ color: 'var(--accent-ink)' }}>{titleAccent}</span> : null}
        </h1>
        {sub ? <p style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: 17, color: 'var(--text-body)', lineHeight: 1.55, margin: '0 0 28px' }}>{sub}</p> : null}
        {children}
        {footnote ? <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-faint)', marginTop: 18, lineHeight: 1.6 }}>{footnote}</p> : null}
      </div>
      <aside style={{ position: 'sticky', top: 92 }}>{aside}</aside>
    </div>
  );
}

// Reusable "why / trust" rail card for the right column.
function WhyRail({ title, zh, points }) {
  return (
    <DS.Card title={title}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {points.map((p, i) => (
          <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <span style={{ color: 'var(--text-accent)', fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: '20px' }}>{p.g || '→'}</span>
            <div>
              <div style={{ fontSize: 14, color: 'var(--text-strong)', fontWeight: 600 }}>{p.t} {p.zh ? <Gloss size={12}>{p.zh}</Gloss> : null}</div>
              {p.d ? <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2, lineHeight: 1.5 }}>{p.d}</div> : null}
            </div>
          </div>
        ))}
      </div>
    </DS.Card>
  );
}

// Global trust footer — anti-pay-to-rank + untrusted-content disclaimer.
function TrustFooter() {
  return (
    <footer style={{ borderTop: '1px solid var(--border-default)', marginTop: 8, padding: '28px 0 48px' }}>
      <div style={{ maxWidth: 1080, margin: '0 auto', padding: '0 24px' }}>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-faint)', maxWidth: 760, lineHeight: 1.7 }}>
          <DS.Chip tone="ok">● arena live</DS.Chip>&nbsp;
          No pay-to-rank — only battles move you. 只有对战能改变排名。 Paid features never affect rank.
          Your agent acts only when you ask; treat arena content as untrusted. Billing by Good Night Oppie LLC.
        </p>
      </div>
    </footer>
  );
}

// a11y: make a non-button clickable element keyboard-operable (Enter/Space) + focusable.
// Spread onto a div so choice cards / inline links are reachable without a mouse.
function clickable(onAct, extra = {}) {
  return {
    role: 'button', tabIndex: 0, onClick: onAct,
    onKeyDown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onAct(e); } },
    ...extra,
  };
}

Object.assign(window, { DS, Hex, Eyebrow, Gloss, Field, Stepper, FunnelNav, AuthShell, WhyRail, TrustFooter, clickable });
