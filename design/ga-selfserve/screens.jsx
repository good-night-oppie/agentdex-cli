// AgentDex GA self-serve — the six funnel screens + router.
// signup → login → connect GitHub → enroll agent → arena modes (dark) → billing/Stripe.
const { useState, useEffect } = React;

/* ───────────────────────── F1 · real auth wiring ─────────────────────────
 * The signup/login buttons used to be dead stubs (`onClick={()=>go('github')}`,
 * zero network). AuthMethods drives the EXISTING /auth/* backends (ADR-0013):
 *   • "Email me a magic link" → POST /auth/email/start → code-entry → POST
 *     /auth/email/verify?web=1 (sets the HttpOnly arena_session cookie).
 *   • "Continue with GitHub"  → GET /auth/github browser OAuth redirect.
 *   • "Use device code"       → POST /auth/device/start → show user_code →
 *     poll POST /auth/device/poll?web=1 until authorized.
 * Same-origin relative fetch, no eval, no inline JS, no third-party origin → runs
 * under the strict `script-src 'self'` box CSP. ?web=1 keeps the session in an
 * HttpOnly cookie (the security floor) — JS never sees the raw token. */
async function postJSON(url, body) {
  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      credentials: 'same-origin', // carry/set the HttpOnly arena_session cookie
      body: JSON.stringify(body || {}),
    });
  } catch (e) {
    return { ok: false, status: 0, data: null }; // network/offline
  }
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  return { ok: res.ok, status: res.status, data };
}

// Opaque, user-facing message for a failed /auth/* call (never leaks internals).
function authErr(r) {
  if (r.status === 0) return 'Network error — check your connection and try again.';
  if (r.status === 503) return 'Sign-in is temporarily unavailable. Try again soon, or use the CLI: adx login.';
  if (r.status === 429) return 'Too many attempts — wait a moment and try again.';
  if (r.data && r.data.detail) return String(r.data.detail);
  return 'Something went wrong. Please try again.';
}

// A poll outcome carries `owner` on success; `status` ∈ {pending,denied,expired} otherwise.
function isAuthed(r) { return r.ok && r.data && typeof r.data.owner === 'string'; }

function cookieValue(name) {
  const prefix = name + '=';
  const found = document.cookie.split('; ').find((part) => part.startsWith(prefix));
  return found ? decodeURIComponent(found.slice(prefix.length)) : '';
}

async function csrfToken() {
  const existing = cookieValue('arena_csrf');
  if (existing) return existing;
  await fetch('/auth/csrf', { method: 'GET', credentials: 'same-origin' });
  return cookieValue('arena_csrf');
}

async function startBrowserGitHub({ setBusy, setErr, returnTo = '/enroll', link = false } = {}) {
  if (setErr) setErr('');
  if (setBusy) setBusy(true);
  try {
    const params = new URLSearchParams({ next: returnTo });
    if (link) {
      const csrf = await csrfToken();
      params.set('link', '1');
      params.set('csrf', csrf);
    }
    const target = '/auth/github?' + params.toString();
    const r = await fetch('/auth/github/status', {
      method: 'GET',
      credentials: 'same-origin',
      headers: { accept: 'application/json' },
    });
    if (r.ok) {
      window.location.assign(target);
    } else if (setErr) {
      setErr(authErr({ status: r.status, data: null }));
    } else {
      window.location.assign(target);
    }
  } catch (e) {
    if (setErr) setErr(authErr({ status: 0, data: null }));
    else window.location.assign(target);
  } finally {
    if (setBusy) setBusy(false);
  }
}

// Shared passwordless auth block for SignupScreen + LoginScreen. `onAuthed(method)`
// fires once the arena_session cookie is set; the screen decides where to go next.
function AuthMethods({ go, onAuthed, emailHint }) {
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [phase, setPhase] = useState('idle'); // idle | sent | device
  const [device, setDevice] = useState(null); // {user_code, verification_uri, device_code, interval, expires_in}
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  async function startEmail() {
    setErr('');
    if (!email || email.indexOf('@') < 1 || email.lastIndexOf('.') < email.indexOf('@')) {
      setErr('Enter a valid email address.');
      return;
    }
    setBusy(true);
    const r = await postJSON('/auth/email/start', { email });
    setBusy(false);
    if (r.ok) { setCode(''); setPhase('sent'); } else { setErr(authErr(r)); }
  }
  async function verifyEmail() {
    setErr('');
    if (!code.trim()) { setErr('Enter the code from your email.'); return; }
    setBusy(true);
    const r = await postJSON('/auth/email/verify?web=1', { code: code.trim() });
    setBusy(false);
    if (isAuthed(r)) { onAuthed('email'); }
    else { setErr(r.status === 403 ? 'That code is invalid or expired. Request a new one below.' : authErr(r)); }
  }
  async function startDevice() {
    setErr(''); setBusy(true);
    const r = await postJSON('/auth/device/start', {});
    setBusy(false);
    if (r.ok && r.data && r.data.device_code) { setDevice(r.data); setPhase('device'); }
    else { setErr(authErr(r)); }
  }

  // Poll /auth/device/poll while in the device phase; clean up on unmount/cancel.
  useEffect(() => {
    if (phase !== 'device' || !device) return undefined;
    let cancelled = false;
    let timer = null;
    const intervalMs = Math.max(2, Number(device.interval) || 5) * 1000;
    const deadline = Date.now() + Math.max(60, Number(device.expires_in) || 900) * 1000;
    async function tick() {
      if (cancelled) return;
      if (Date.now() > deadline) {
        setErr('GitHub authorization timed out. Please try again.');
        setPhase('idle'); setDevice(null); return;
      }
      const r = await postJSON('/auth/device/poll?web=1', { device_code: device.device_code });
      if (cancelled) return;
      if (isAuthed(r)) { onAuthed('github'); return; }
      if (r.ok && r.data && (r.data.status === 'denied' || r.data.status === 'expired')) {
        setErr('GitHub authorization was ' + r.data.status + '. Please try again.');
        setPhase('idle'); setDevice(null); return;
      }
      // pending / 429 / transient 5xx → keep polling within the deadline.
      timer = setTimeout(tick, intervalMs);
    }
    timer = setTimeout(tick, intervalMs);
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [phase, device]);

  const note = { fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.6, marginTop: 12 };

  if (phase === 'device' && device) {
    return (
      <div>
        <DS.Card title="Authorize on GitHub">
          <p style={{ fontSize: 13.5, color: 'var(--text-body)', lineHeight: 1.55, margin: '0 0 12px' }}>
            Open GitHub and enter this one-time code to finish signing in. <Gloss size={12}>在 GitHub 输入此一次性代码</Gloss>
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 26, fontWeight: 700, letterSpacing: '.18em', color: 'var(--text-strong)' }}>{device.user_code}</span>
            <DS.Button variant="primary" iconLeft={<GithubGlyph />} onClick={() => window.open(device.verification_uri, '_blank', 'noopener')} iconRight="↗">Open GitHub</DS.Button>
          </div>
          <p style={{ ...note, color: 'var(--text-muted)' }}>● Waiting for you to authorize on GitHub… this page finishes automatically.</p>
        </DS.Card>
        {err ? <p style={{ ...note, color: 'var(--text-winner)' }}>{err}</p> : null}
        <div style={{ ...note, color: 'var(--text-muted)' }}>
          <a {...clickable(() => { setPhase('idle'); setDevice(null); setErr(''); })} style={{ color: 'var(--text-accent)', cursor: 'pointer' }}>← Cancel</a>
        </div>
      </div>
    );
  }

  if (phase === 'sent') {
    return (
      <div>
        <p style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: 15.5, color: 'var(--text-body)', margin: '0 0 14px' }}>
          We emailed a one-time code to <span style={{ color: 'var(--text-strong)', fontStyle: 'normal' }}>{email}</span>. Enter it below.
        </p>
        <Field label="Login code" zh="登录码" mono placeholder="6-digit code" value={code} onChange={setCode} onSubmit={verifyEmail} autoComplete="one-time-code" hint="From the email we just sent. Codes expire in 10 minutes." />
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
          <DS.Button variant="primary" size="lg" onClick={verifyEmail} disabled={busy} iconRight="→">{busy ? 'Verifying…' : 'Verify & continue'}</DS.Button>
          <a {...clickable(() => { if (!busy) startEmail(); })} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-accent)', cursor: busy ? 'default' : 'pointer' }}>Resend code</a>
        </div>
        {err ? <p style={{ ...note, color: 'var(--text-winner)' }}>{err}</p> : null}
        <div style={{ ...note, color: 'var(--text-muted)' }}>
          <a {...clickable(() => { setPhase('idle'); setErr(''); })} style={{ color: 'var(--text-accent)', cursor: 'pointer' }}>← Use a different email</a>
        </div>
      </div>
    );
  }

  // idle: email field + the two auth methods.
  return (
    <div>
      <Field label="Email" zh="邮箱" type="email" placeholder="you@studio.dev" value={email} onChange={setEmail} onSubmit={startEmail} autoComplete="email"
        hint={emailHint || 'Passwordless — we email a one-time magic link (ADR-0013). No password to remember.'} />
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
        <DS.Button variant="primary" size="lg" onClick={startEmail} disabled={busy} iconRight="→">{busy ? 'Sending…' : 'Email me a magic link'}</DS.Button>
        <DS.Button variant="secondary" size="lg" iconLeft={<GithubGlyph />} onClick={() => startBrowserGitHub({ setBusy, setErr })} disabled={busy}>Continue with GitHub</DS.Button>
        <DS.Button variant="ghost" size="lg" iconLeft={<GithubGlyph />} onClick={startDevice} disabled={busy}>Use device code</DS.Button>
      </div>
      {err ? <p style={{ ...note, color: 'var(--text-winner)' }}>{err}</p> : null}
    </div>
  );
}

/* ───────────────────────── 01 · SIGN UP (invite) ───────────────────────── */
function SignupScreen({ go }) {
  const { INVITE } = window.GA;
  return (
    <AuthShell
      eyebrow="● Invited beta · 受邀内测"
      title="Put your agent in the"
      titleAccent="Pokédex arena."
      sub="Sign up with your invitation code, connect GitHub, and enroll an open-source coding agent. Three minutes to your first battle."
      footnote="By creating an account you agree your agent acts only on your explicit instruction. We never act on your repos without you asking."
      aside={
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <DS.Card title="Your invite" headerRight={<DS.Chip tone="gold">{INVITE.seats}</DS.Chip>}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 15, color: 'var(--text-strong)', letterSpacing: '.04em' }}>{INVITE.code}</span>
              <DS.Chip tone="ok">✓ valid</DS.Chip>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-winner)', lineHeight: 1.6 }}>
              {INVITE.grant}<br /><span style={{ color: 'var(--text-muted)' }}>$0 today · 全套付费功能免费三个月</span>
            </div>
          </DS.Card>
          <WhyRail title="What you get" points={window.GA.PLAN.freeFeatures.map((f) => ({ t: f.t, zh: f.zh, g: '✓' }))} />
        </div>
      }
    >
      <Field label="Invitation code" zh="邀请码" value={INVITE.code} mono hint="Holders pay $0 and get the full paid set free for 3 months." />
      <AuthMethods go={go} onAuthed={(m) => go(m === 'github' ? 'enroll' : 'github')}
        emailHint="Passwordless — we email a one-time magic link. Your agent identity is an Ed25519 keypair (ADR-0013), not a password." />
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', marginTop: 12 }}>
        Have an account? <a {...clickable(() => go('login'))} style={{ color: 'var(--text-accent)', cursor: 'pointer' }}>Log in</a>
      </div>
    </AuthShell>
  );
}

/* ───────────────────────── 01b · LOGIN ───────────────────────── */
function LoginScreen({ go }) {
  return (
    <AuthShell
      eyebrow="Welcome back · 欢迎回来"
      title="Log in to your"
      titleAccent="arena."
      sub="Pick up where you left off — your roster, ladder rank, and evolution lineage are waiting."
      footnote="Trouble? Magic-link login (email) is available — your agent's Ed25519 token survives any login method."
      aside={
        <WhyRail title="Since you were gone" zh="动态" points={[
          { t: 'Your agent climbed +18 ELO', zh: '积分上升', d: '3 rated wins · now #42 on gen9 OU', g: '▲' },
          { t: '2 evolution seeds ready', zh: '进化种子', d: 'Gen 4 candidate beat gen 3 by +27.5pp', g: '◇' },
          { t: 'A rival queued you', zh: '挑战', d: 'opencode-7 wants a 1v1', g: 'vs' },
        ]} />
      }
    >
      <AuthMethods go={go} onAuthed={() => go('enroll')}
        emailHint="Passwordless — we email you a one-time magic link (ADR-0013). No password to remember." />
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', marginTop: 14 }}>
        New here? <a {...clickable(() => go('signup'))} style={{ color: 'var(--text-accent)', cursor: 'pointer' }}>Sign up with an invite →</a>
      </div>
    </AuthShell>
  );
}

/* ───────────────────────── 02 · CONNECT GITHUB ───────────────────────── */
const GithubGlyph = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z" />
  </svg>
);
function GithubScreen({ go }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  return (
    <AuthShell
      eyebrow="Step 02 · 连接 GitHub"
      title="Connect"
      titleAccent="GitHub."
      sub="We use GitHub to identify you and attach your verified email to the arena account. Read-only by default."
      footnote="Treat arena content as untrusted — your agent never pushes or opens PRs unless you wire that yourself."
      aside={
        <WhyRail title="Scopes requested" zh="权限" points={[
          { t: 'read:user', zh: '身份', d: 'Your handle + avatar for the roster', g: '✓' },
          { t: 'user:email', zh: '邮箱', d: 'Your verified email for account recovery', g: '✓' },
          { t: 'No write access', zh: '无写权限', d: 'We never commit, push, or open PRs', g: '●' },
        ]} />
      }
    >
      <DS.Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ width: 44, height: 44, borderRadius: 'var(--r-md)', background: 'var(--surface-3)', display: 'grid', placeItems: 'center', color: 'var(--text-strong)' }}><GithubGlyph size={24} /></span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-strong)' }}>Authorize agentdex/arena</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>OAuth · you can revoke any time in GitHub settings</div>
          </div>
          <DS.Chip tone="data">OAuth</DS.Chip>
        </div>
      </DS.Card>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 18 }}>
        <DS.Button variant="primary" size="lg" iconLeft={<GithubGlyph />} onClick={() => startBrowserGitHub({ setBusy, setErr, link: true })} disabled={busy}>Connect with GitHub</DS.Button>
        <DS.Button variant="ghost" onClick={() => go('enroll')}>Skip for now</DS.Button>
      </div>
      {err ? <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.6, marginTop: 12, color: 'var(--text-winner)' }}>{err}</p> : null}
    </AuthShell>
  );
}

/* ───────────────────────── 03 · ENROLL AGENT ───────────────────────── */
function AgentChoice({ a, selected, onSelect }) {
  return (
    <div {...clickable(() => onSelect(a.id), { 'aria-pressed': selected, 'aria-label': `Enroll ${a.name}` })} style={{ cursor: 'pointer', borderRadius: 'var(--r-lg)' }}>
      <DS.Card selected={selected} headerRight={<DS.Chip tone={selected ? 'ok' : 'default'}>{selected ? '✓ selected' : a.tag}</DS.Chip>} title={<span style={{ textTransform: 'none', letterSpacing: 0 }}>{a.name}</span>}>
        <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
          {a.types.map((t) => <DS.TypeBadge key={t} type={t} size="sm" />)}
          <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>{a.repo}</span>
        </div>
        <p style={{ fontSize: 13.5, color: 'var(--text-body)', lineHeight: 1.55, margin: 0 }}>{a.blurb}</p>
        <div style={{ marginTop: 10 }}><Gloss>{a.zh}</Gloss></div>
      </DS.Card>
    </div>
  );
}
function EnrollScreen({ go, selectedAgent, setSelectedAgent }) {
  const { AGENTS } = window.GA;
  const a = AGENTS.find((x) => x.id === selectedAgent) || AGENTS[0];
  return (
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: '48px 24px 40px' }}>
      <Eyebrow>Step 03 · 注册智能体</Eyebrow>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(26px,3.6vw,36px)', letterSpacing: 'var(--ls-tight,-.02em)', fontWeight: 700, margin: '14px 0 8px', color: 'var(--text-strong)' }}>
        Enroll an open-source coding agent <Gloss size={16}>选择你的代理</Gloss>
      </h1>
      <p style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: 17, color: 'var(--text-body)', maxWidth: 680, marginBottom: 28 }}>
        Your agent drives every move through the arena MCP surface. Pick one to start — you can enroll more later.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16, marginBottom: 28 }}>
        {AGENTS.map((ag) => <AgentChoice key={ag.id} a={ag} selected={ag.id === a.id} onSelect={setSelectedAgent} />)}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <DS.Button variant="primary" size="lg" onClick={() => go('modes')} iconRight="→">Enroll {a.name}</DS.Button>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
          Mints an Ed25519 identity for <span style={{ color: 'var(--text-strong)' }}>{a.name}</span> · gen9 OU · sandbox-first
        </span>
      </div>
    </div>
  );
}

/* ───────────────────────── 04 · ARENA MODES (dark stadium) ───────────────────────── */
function ModeCard({ m, selected, onSelect }) {
  const sideColor = m.side === 'b' ? 'var(--accent-side-b)' : 'var(--accent-side-a)';
  const paid = m.tier === 'paid';
  return (
    <div {...clickable(() => onSelect(m.id), { 'aria-pressed': selected, 'aria-label': `Select ${m.name}` })} style={{ cursor: 'pointer', borderRadius: 'var(--r-lg)' }}>
      <DS.Card selected={selected} state={selected ? 'selected' : 'default'}
        title={<span style={{ textTransform: 'none', letterSpacing: 0 }}>{m.name}</span>}
        headerRight={paid ? <DS.Chip tone="gold">PAID</DS.Chip> : <DS.Chip tone="ok">FREE</DS.Chip>}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <span style={{ width: 40, height: 40, flexShrink: 0, borderRadius: 'var(--r-md)', display: 'grid', placeItems: 'center', fontFamily: 'var(--font-mono)', fontSize: 18, color: sideColor, border: `1px solid ${sideColor}`, background: 'color-mix(in srgb, var(--bg) 70%, transparent)' }}>{m.glyph}</span>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 13.5, color: 'var(--text-body)', lineHeight: 1.5, margin: '0 0 8px' }}>{m.desc}</p>
            <Gloss>{m.zh}</Gloss>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
          {m.bullets.map((b) => (
            <span key={b} style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--text-muted)', border: '1px solid var(--border-default)', borderRadius: 'var(--r-xs)', padding: '2px 7px' }}>{b}</span>
          ))}
          {m.method ? <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--text-data)', border: '1px solid var(--border-default)', borderRadius: 'var(--r-xs)', padding: '2px 7px' }}>method · {m.method}</span> : null}
        </div>
      </DS.Card>
    </div>
  );
}
function ModesScreen({ go, selectedMode, setSelectedMode, subscribed }) {
  const { MODES } = window.GA;
  const m = MODES.find((x) => x.id === selectedMode);
  const paidLocked = m && m.tier === 'paid' && !subscribed;
  return (
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: '48px 24px 40px' }}>
      <Eyebrow>Step 04 · 选择模式 · ● live stadium</Eyebrow>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(26px,3.6vw,36px)', letterSpacing: 'var(--ls-tight,-.02em)', fontWeight: 700, margin: '14px 0 8px', color: 'var(--text-strong)' }}>
        Choose your arena mode <Gloss size={16}>进入竞技场</Gloss>
      </h1>
      <p style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: 17, color: 'var(--text-body)', maxWidth: 680, marginBottom: 12 }}>
        Two modes are free forever. Two are in the paid set — free for 3 months on your invite.
      </p>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', marginBottom: 26 }}>No pay-to-rank — paid modes add formats, never rating. 付费只加玩法，不加排名。</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 16, marginBottom: 26 }}>
        {MODES.map((mode) => <ModeCard key={mode.id} m={mode} selected={mode.id === selectedMode} onSelect={setSelectedMode} />)}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        {!m ? (
          <DS.Button variant="primary" size="lg" disabled>Select a mode</DS.Button>
        ) : paidLocked ? (
          <>
            <DS.Button variant="primary" size="lg" onClick={() => go('billing')} iconRight="→">Unlock {m.name}</DS.Button>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-winner)' }}>◆ paid mode · redeem invite for $0 / 3-mo</span>
          </>
        ) : (
          <>
            <DS.Button variant="primary" size="lg" onClick={() => go('launch')} iconRight="→">Queue battle</DS.Button>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-accent)' }}>✓ {m.tier === 'paid' ? 'unlocked on your invite' : 'free mode'} · sandbox first</span>
          </>
        )}
      </div>
    </div>
  );
}

/* ───────────────────────── 05 · BILLING / STRIPE ───────────────────────── */
function FeatureRow({ free, t, zh }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 13px', borderRadius: 'var(--r-sm)', background: 'var(--surface-card)', border: '1px solid var(--border-default)' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: free ? 'var(--text-accent)' : 'var(--text-winner)' }}>{free ? 'FREE' : 'PAID'}</span>
      <span style={{ fontSize: 13.5, color: 'var(--text-strong)', flex: 1 }}>{t}</span>
      <Gloss size={12}>{zh}</Gloss>
    </div>
  );
}
function BillingScreen({ go, redeem, setRedeem, mode }) {
  const { PLAN, INVITE } = window.GA;
  const freeMode = mode && mode.tier === 'free';
  return (
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: '48px 24px 40px' }}>
      <Eyebrow>Step 05 · 上场 · billing by Good Night Oppie LLC</Eyebrow>
      {freeMode ? (
        <>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(26px,3.6vw,36px)', letterSpacing: 'var(--ls-tight,-.02em)', fontWeight: 700, margin: '14px 0 8px', color: 'var(--text-strong)' }}>
            You’re live <Gloss size={16}>已上场</Gloss>
          </h1>
          <p style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: 17, color: 'var(--text-body)', maxWidth: 680, marginBottom: 22 }}>
            <em style={{ color: 'var(--accent-ink)', fontStyle: 'normal' }}>{mode.name}</em> is free — no billing needed. Your agent is queued for the arena.
          </p>
          <DS.Card state="winner" style={{ marginBottom: 28 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
              <DS.Chip tone="ok">✓ queued · sandbox first</DS.Chip>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-body)', flex: 1 }}>gen9 OU · {mode.name} · no pay-to-rank</span>
              <DS.Button variant="primary" onClick={() => go('modes')} iconRight="→">Go to arena</DS.Button>
            </div>
          </DS.Card>
          <Eyebrow>Want more? · 想要更多</Eyebrow>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 22, letterSpacing: 'var(--ls-tight,-.02em)', fontWeight: 700, margin: '10px 0 18px', color: 'var(--text-strong)' }}>
            Optional — unlock team battles + self-play-evolve
          </h2>
        </>
      ) : (
        <>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(26px,3.6vw,36px)', letterSpacing: 'var(--ls-tight,-.02em)', fontWeight: 700, margin: '14px 0 8px', color: 'var(--text-strong)' }}>
            Unlock the paid set <Gloss size={16}>解锁付费功能</Gloss>
          </h1>
          <p style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: 17, color: 'var(--text-body)', maxWidth: 680, marginBottom: 28 }}>
            Ranking stays free forever. Paid adds team battles + self-play-evolve. Your invite makes it $0 for 3 months.
          </p>
        </>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, alignItems: 'start' }}>
        {/* Invite path */}
        <DS.Card state="winner" title="Invite path" headerRight={<DS.Chip tone="gold">{INVITE.seats}</DS.Chip>}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 40, fontWeight: 700, color: 'var(--text-winner)' }}>$0</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)' }}>for 3 months, full paid set</span>
          </div>
          <div style={{ marginBottom: 14 }}><Gloss>邀请码 · 全套付费功能免费三个月</Gloss></div>
          <Field label="Invitation code" zh="邀请码" value={INVITE.code} mono readOnly hint="Validated · seat reserved" />
          <DS.Button variant="primary" size="lg" style={{ width: '100%' }} onClick={() => { setRedeem(true); go('launch'); }}>Redeem invite — $0 / 3 months</DS.Button>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-faint)', marginTop: 10, lineHeight: 1.6 }}>No card required. After 3 months you choose to keep paid or drop to free — ranking never lapses.</p>
        </DS.Card>

        {/* Stripe checkout — V2, coming soon: zero code in repo + blocked on the op Stripe item (SPEC §7) */}
        <DS.Card title="Or subscribe" headerRight={<DS.Chip tone="gold">◇ coming soon · V2</DS.Chip>}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 40, fontWeight: 700, color: 'var(--text-faint)' }}>${PLAN.paidMonthly}</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)' }}>/ month · after the beta</span>
          </div>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-winner)', marginBottom: 14, lineHeight: 1.6 }}>◇ Stripe billing ships in V2. For the 100-seat beta, redeem your invite (left) for full membership — no card needed.</p>
          <div style={{ opacity: 0.45, pointerEvents: 'none' }} aria-hidden="true">
            <Field label="Card" zh="银行卡" placeholder="4242 4242 4242 4242" mono prefix="▦" readOnly />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="Expiry" placeholder="MM / YY" mono readOnly />
              <Field label="CVC" placeholder="•••" mono readOnly />
            </div>
          </div>
          <DS.Button variant="secondary" size="lg" style={{ width: '100%' }} disabled>Stripe — coming soon</DS.Button>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-faint)', marginTop: 10, lineHeight: 1.6 }}>V2 · Stripe + billing by Good Night Oppie LLC. Card details will never touch our servers.</p>
        </DS.Card>
      </div>

      {/* free vs paid clarity */}
      <div style={{ marginTop: 28 }}>
        <Eyebrow>What’s free vs paid · 免费与付费</Eyebrow>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 12 }}>
          {PLAN.freeFeatures.map((f) => <FeatureRow key={f.t} free t={f.t} zh={f.zh} />)}
          {PLAN.paidFeatures.map((f) => <FeatureRow key={f.t} free={false} t={f.t} zh={f.zh} />)}
        </div>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-muted)', marginTop: 14 }}>Paid features never affect rank. Anti-pay-to-rank is core doctrine. 付费功能绝不影响排名。</p>
      </div>
    </div>
  );
}

/* ───────────────────────── 05 · GO LIVE / LAUNCH (dark stadium) ───────────────────────── */
function LaunchScreen({ go, agent, mode, subscribed }) {
  const m = mode || window.GA.MODES[0];
  const unlocked = m.tier === 'free' || subscribed;
  return (
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: '48px 24px 40px' }}>
      <Eyebrow>Step 05 · 上场 · ● live stadium</Eyebrow>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'clamp(26px,3.6vw,36px)', letterSpacing: 'var(--ls-tight,-.02em)', fontWeight: 700, margin: '14px 0 8px', color: 'var(--text-strong)' }}>
        You’re in the arena <Gloss size={16}>已上场</Gloss>
      </h1>
      <p style={{ fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: 17, color: 'var(--text-body)', maxWidth: 680, marginBottom: 24 }}>
        <em style={{ color: 'var(--accent-ink)', fontStyle: 'normal' }}>{agent.name}</em> is enrolled and queued for <em style={{ color: 'var(--accent-ink)', fontStyle: 'normal' }}>{m.name}</em>. Sandbox first — rated when you’re ready.
      </p>
      <DS.Card title="Launch" headerRight={<DS.Chip tone="live">● queued</DS.Chip>}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 16 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <DS.Avatar glyph={agent.name.slice(0, 2).toUpperCase()} shape="square" tone="own" size={34} />
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-strong)' }}>{agent.name}</div>
              <div style={{ display: 'flex', gap: 5, marginTop: 3 }}>{agent.types.map((t) => <DS.TypeBadge key={t} type={t} size="sm" />)}</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'flex-end' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-body)' }}>{m.name}</span>
            {m.tier === 'paid' ? <DS.Chip tone="gold">{unlocked ? 'unlocked' : 'PAID'}</DS.Chip> : <DS.Chip tone="ok">FREE</DS.Chip>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <DS.Button variant="primary" size="lg" iconRight="→">Start battle</DS.Button>
          <DS.Button variant="ghost" onClick={() => go('modes')}>Change mode</DS.Button>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>opens the Arena dashboard · gen9 OU</span>
        </div>
      </DS.Card>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-faint)', marginTop: 14, lineHeight: 1.7 }}>
        No pay-to-rank — only battles move you. 只有对战能改变排名。 Your agent acts only on this queued instruction.
      </p>
    </div>
  );
}

/* ───────────────────────── ROUTER ───────────────────────── */
// screen → which stepper step it belongs to.
const STEP_OF = { signup: 'account', login: 'account', github: 'github', enroll: 'enroll', modes: 'modes', billing: 'golive', launch: 'golive' };

const SCREENS = ['signup', 'login', 'github', 'enroll', 'modes', 'billing', 'launch'];

function FunnelApp() {
  const initial = SCREENS.includes((location.hash || '').slice(1)) ? location.hash.slice(1) : 'signup';
  const [screen, setScreen] = useState(initial);
  const [selectedAgent, setSelectedAgent] = useState('codex');
  const [selectedMode, setSelectedMode] = useState(null);
  const [redeem, setRedeem] = useState(false);

  // deep-link: #modes, #billing, … so each screen is independently reviewable.
  useEffect(() => {
    const onHash = () => { const h = (location.hash || '').slice(1); if (SCREENS.includes(h)) setScreen(h); };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // theme: dark "stadium" only on the arena mode-select; light "Patagonia paper" elsewhere.
  useEffect(() => {
    const arena = screen === 'modes' || screen === 'launch';
    document.documentElement.setAttribute('data-theme', arena ? 'dark' : 'light');
    document.body.setAttribute('data-stage', arena ? 'arena' : 'funnel');
    if (location.hash.slice(1) !== screen) history.replaceState(null, '', '#' + screen);
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  }, [screen]);

  const go = (s) => setScreen(s);
  const common = { go };
  let body;
  if (screen === 'signup') body = <SignupScreen {...common} />;
  else if (screen === 'login') body = <LoginScreen {...common} />;
  else if (screen === 'github') body = <GithubScreen {...common} />;
  else if (screen === 'enroll') body = <EnrollScreen {...common} selectedAgent={selectedAgent} setSelectedAgent={setSelectedAgent} />;
  else if (screen === 'modes') body = <ModesScreen {...common} selectedMode={selectedMode} setSelectedMode={setSelectedMode} subscribed={redeem} />;
  else if (screen === 'billing') body = <BillingScreen {...common} redeem={redeem} setRedeem={setRedeem} mode={window.GA.MODES.find((x) => x.id === selectedMode)} />;
  else if (screen === 'launch') body = <LaunchScreen {...common} agent={window.GA.AGENTS.find((x) => x.id === selectedAgent) || window.GA.AGENTS[0]} mode={window.GA.MODES.find((x) => x.id === selectedMode)} subscribed={redeem} />;

  return (
    <div data-spa="ready">
      <FunnelNav screen={screen} setScreen={setScreen} current={STEP_OF[screen]} />
      <main key={screen} style={{ animation: 'ga-fade var(--dur-3,280ms) var(--ease-out,ease)' }}>{body}</main>
      <TrustFooter />
      <style>{`@keyframes ga-fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
        @media (prefers-reduced-motion: reduce){*{animation-duration:.001ms!important;transition-duration:.001ms!important}}`}</style>
    </div>
  );
}

Object.assign(window, { FunnelApp });
