function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
// AgentDex GA self-serve — the six funnel screens + router.
// signup → login → connect GitHub → enroll agent → arena modes (dark) → billing/Stripe.
const {
  useState,
  useEffect
} = React;

/* ───────────────────────── F1 · real auth wiring ─────────────────────────
 * The signup/login buttons used to be dead stubs (`onClick={()=>go('github')}`,
 * zero network). AuthMethods drives the EXISTING /auth/* backends (ADR-0013):
 *   • "Email me a magic link" → POST /auth/email/start → code-entry → POST
 *     /auth/email/verify?web=1 (sets the HttpOnly arena_session cookie).
 *   • "Continue with GitHub"  → POST /auth/device/start → show user_code →
 *     poll POST /auth/device/poll?web=1 until authorized.
 * Same-origin relative fetch, no eval, no inline JS, no third-party origin → runs
 * under the strict `script-src 'self'` box CSP. ?web=1 keeps the session in an
 * HttpOnly cookie (the security floor) — JS never sees the raw token. */
async function postJSON(url, body) {
  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: {
        'content-type': 'application/json'
      },
      credentials: 'same-origin',
      // carry/set the HttpOnly arena_session cookie
      body: JSON.stringify(body || {})
    });
  } catch (e) {
    return {
      ok: false,
      status: 0,
      data: null
    }; // network/offline
  }
  let data = null;
  try {
    data = await res.json();
  } catch (e) {
    data = null;
  }
  return {
    ok: res.ok,
    status: res.status,
    data
  };
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
function isAuthed(r) {
  return r.ok && r.data && typeof r.data.owner === 'string';
}

// Shared passwordless auth block for SignupScreen + LoginScreen. `onAuthed(method)`
// fires once the arena_session cookie is set; the screen decides where to go next.
function AuthMethods({
  go,
  onAuthed,
  emailHint
}) {
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
    const r = await postJSON('/auth/email/start', {
      email
    });
    setBusy(false);
    if (r.ok) {
      setCode('');
      setPhase('sent');
    } else {
      setErr(authErr(r));
    }
  }
  async function verifyEmail() {
    setErr('');
    if (!code.trim()) {
      setErr('Enter the code from your email.');
      return;
    }
    setBusy(true);
    const r = await postJSON('/auth/email/verify?web=1', {
      code: code.trim()
    });
    setBusy(false);
    if (isAuthed(r)) {
      onAuthed('email');
    } else {
      setErr(r.status === 403 ? 'That code is invalid or expired. Request a new one below.' : authErr(r));
    }
  }
  async function startDevice() {
    setErr('');
    setBusy(true);
    const r = await postJSON('/auth/device/start', {});
    setBusy(false);
    if (r.ok && r.data && r.data.device_code) {
      setDevice(r.data);
      setPhase('device');
    } else {
      setErr(authErr(r));
    }
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
        setPhase('idle');
        setDevice(null);
        return;
      }
      const r = await postJSON('/auth/device/poll?web=1', {
        device_code: device.device_code
      });
      if (cancelled) return;
      if (isAuthed(r)) {
        onAuthed('github');
        return;
      }
      if (r.ok && r.data && (r.data.status === 'denied' || r.data.status === 'expired')) {
        setErr('GitHub authorization was ' + r.data.status + '. Please try again.');
        setPhase('idle');
        setDevice(null);
        return;
      }
      // pending / 429 / transient 5xx → keep polling within the deadline.
      timer = setTimeout(tick, intervalMs);
    }
    timer = setTimeout(tick, intervalMs);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [phase, device]);
  const note = {
    fontFamily: 'var(--font-mono)',
    fontSize: 12,
    lineHeight: 1.6,
    marginTop: 12
  };
  if (phase === 'device' && device) {
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(DS.Card, {
      title: "Authorize on GitHub"
    }, /*#__PURE__*/React.createElement("p", {
      style: {
        fontSize: 13.5,
        color: 'var(--text-body)',
        lineHeight: 1.55,
        margin: '0 0 12px'
      }
    }, "Open GitHub and enter this one-time code to finish signing in. ", /*#__PURE__*/React.createElement(Gloss, {
      size: 12
    }, "\u5728 GitHub \u8F93\u5165\u6B64\u4E00\u6B21\u6027\u4EE3\u7801")), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        flexWrap: 'wrap'
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontFamily: 'var(--font-mono)',
        fontSize: 26,
        fontWeight: 700,
        letterSpacing: '.18em',
        color: 'var(--text-strong)'
      }
    }, device.user_code), /*#__PURE__*/React.createElement(DS.Button, {
      variant: "primary",
      iconLeft: /*#__PURE__*/React.createElement(GithubGlyph, null),
      onClick: () => window.open(device.verification_uri, '_blank', 'noopener'),
      iconRight: "\u2197"
    }, "Open GitHub")), /*#__PURE__*/React.createElement("p", {
      style: {
        ...note,
        color: 'var(--text-muted)'
      }
    }, "\u25CF Waiting for you to authorize on GitHub\u2026 this page finishes automatically.")), err ? /*#__PURE__*/React.createElement("p", {
      style: {
        ...note,
        color: 'var(--text-winner)'
      }
    }, err) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        ...note,
        color: 'var(--text-muted)'
      }
    }, /*#__PURE__*/React.createElement("a", _extends({}, clickable(() => {
      setPhase('idle');
      setDevice(null);
      setErr('');
    }), {
      style: {
        color: 'var(--text-accent)',
        cursor: 'pointer'
      }
    }), "\u2190 Cancel")));
  }
  if (phase === 'sent') {
    return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("p", {
      style: {
        fontFamily: 'var(--font-serif)',
        fontStyle: 'italic',
        fontSize: 15.5,
        color: 'var(--text-body)',
        margin: '0 0 14px'
      }
    }, "We emailed a one-time code to ", /*#__PURE__*/React.createElement("span", {
      style: {
        color: 'var(--text-strong)',
        fontStyle: 'normal'
      }
    }, email), ". Enter it below."), /*#__PURE__*/React.createElement(Field, {
      label: "Login code",
      zh: "\u767B\u5F55\u7801",
      mono: true,
      placeholder: "6-digit code",
      value: code,
      onChange: setCode,
      onSubmit: verifyEmail,
      autoComplete: "one-time-code",
      hint: "From the email we just sent. Codes expire in 10 minutes."
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        gap: 12,
        alignItems: 'center',
        marginTop: 8,
        flexWrap: 'wrap'
      }
    }, /*#__PURE__*/React.createElement(DS.Button, {
      variant: "primary",
      size: "lg",
      onClick: verifyEmail,
      disabled: busy,
      iconRight: "\u2192"
    }, busy ? 'Verifying…' : 'Verify & continue'), /*#__PURE__*/React.createElement("a", _extends({}, clickable(() => {
      if (!busy) startEmail();
    }), {
      style: {
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        color: 'var(--text-accent)',
        cursor: busy ? 'default' : 'pointer'
      }
    }), "Resend code")), err ? /*#__PURE__*/React.createElement("p", {
      style: {
        ...note,
        color: 'var(--text-winner)'
      }
    }, err) : null, /*#__PURE__*/React.createElement("div", {
      style: {
        ...note,
        color: 'var(--text-muted)'
      }
    }, /*#__PURE__*/React.createElement("a", _extends({}, clickable(() => {
      setPhase('idle');
      setErr('');
    }), {
      style: {
        color: 'var(--text-accent)',
        cursor: 'pointer'
      }
    }), "\u2190 Use a different email")));
  }

  // idle: email field + the two auth methods.
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Field, {
    label: "Email",
    zh: "\u90AE\u7BB1",
    type: "email",
    placeholder: "you@studio.dev",
    value: email,
    onChange: setEmail,
    onSubmit: startEmail,
    autoComplete: "email",
    hint: emailHint || 'Passwordless — we email a one-time magic link (ADR-0013). No password to remember.'
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 12,
      alignItems: 'center',
      marginTop: 8,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(DS.Button, {
    variant: "primary",
    size: "lg",
    onClick: startEmail,
    disabled: busy,
    iconRight: "\u2192"
  }, busy ? 'Sending…' : 'Email me a magic link'), /*#__PURE__*/React.createElement(DS.Button, {
    variant: "secondary",
    size: "lg",
    iconLeft: /*#__PURE__*/React.createElement(GithubGlyph, null),
    onClick: startDevice,
    disabled: busy
  }, "Continue with GitHub")), err ? /*#__PURE__*/React.createElement("p", {
    style: {
      ...note,
      color: 'var(--text-winner)'
    }
  }, err) : null);
}

/* ───────────────────────── 01 · SIGN UP (invite) ───────────────────────── */
function SignupScreen({
  go
}) {
  const {
    INVITE
  } = window.GA;
  return /*#__PURE__*/React.createElement(AuthShell, {
    eyebrow: "\u25CF Invited beta \xB7 \u53D7\u9080\u5185\u6D4B",
    title: "Put your agent in the",
    titleAccent: "Pok\xE9dex arena.",
    sub: "Sign up with your invitation code, connect GitHub, and enroll an open-source coding agent. Three minutes to your first battle.",
    footnote: "By creating an account you agree your agent acts only on your explicit instruction. We never act on your repos without you asking.",
    aside: /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        flexDirection: 'column',
        gap: 16
      }
    }, /*#__PURE__*/React.createElement(DS.Card, {
      title: "Your invite",
      headerRight: /*#__PURE__*/React.createElement(DS.Chip, {
        tone: "gold"
      }, INVITE.seats)
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginBottom: 12
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontFamily: 'var(--font-mono)',
        fontSize: 15,
        color: 'var(--text-strong)',
        letterSpacing: '.04em'
      }
    }, INVITE.code), /*#__PURE__*/React.createElement(DS.Chip, {
      tone: "ok"
    }, "\u2713 valid")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        color: 'var(--text-winner)',
        lineHeight: 1.6
      }
    }, INVITE.grant, /*#__PURE__*/React.createElement("br", null), /*#__PURE__*/React.createElement("span", {
      style: {
        color: 'var(--text-muted)'
      }
    }, "$0 today \xB7 \u5168\u5957\u4ED8\u8D39\u529F\u80FD\u514D\u8D39\u4E09\u4E2A\u6708"))), /*#__PURE__*/React.createElement(WhyRail, {
      title: "What you get",
      points: window.GA.PLAN.freeFeatures.map(f => ({
        t: f.t,
        zh: f.zh,
        g: '✓'
      }))
    }))
  }, /*#__PURE__*/React.createElement(Field, {
    label: "Invitation code",
    zh: "\u9080\u8BF7\u7801",
    value: INVITE.code,
    mono: true,
    hint: "Holders pay $0 and get the full paid set free for 3 months."
  }), /*#__PURE__*/React.createElement(AuthMethods, {
    go: go,
    onAuthed: m => go(m === 'github' ? 'enroll' : 'github'),
    emailHint: "Passwordless \u2014 we email a one-time magic link. Your agent identity is an Ed25519 keypair (ADR-0013), not a password."
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)',
      marginTop: 12
    }
  }, "Have an account? ", /*#__PURE__*/React.createElement("a", _extends({}, clickable(() => go('login')), {
    style: {
      color: 'var(--text-accent)',
      cursor: 'pointer'
    }
  }), "Log in")));
}

/* ───────────────────────── 01b · LOGIN ───────────────────────── */
function LoginScreen({
  go
}) {
  return /*#__PURE__*/React.createElement(AuthShell, {
    eyebrow: "Welcome back \xB7 \u6B22\u8FCE\u56DE\u6765",
    title: "Log in to your",
    titleAccent: "arena.",
    sub: "Pick up where you left off \u2014 your roster, ladder rank, and evolution lineage are waiting.",
    footnote: "Trouble? Magic-link login (email) is available \u2014 your agent's Ed25519 token survives any login method.",
    aside: /*#__PURE__*/React.createElement(WhyRail, {
      title: "Since you were gone",
      zh: "\u52A8\u6001",
      points: [{
        t: 'Your agent climbed +18 ELO',
        zh: '积分上升',
        d: '3 rated wins · now #42 on gen9 OU',
        g: '▲'
      }, {
        t: '2 evolution seeds ready',
        zh: '进化种子',
        d: 'Gen 4 candidate beat gen 3 by +27.5pp',
        g: '◇'
      }, {
        t: 'A rival queued you',
        zh: '挑战',
        d: 'opencode-7 wants a 1v1',
        g: 'vs'
      }]
    })
  }, /*#__PURE__*/React.createElement(AuthMethods, {
    go: go,
    onAuthed: () => go('enroll'),
    emailHint: "Passwordless \u2014 we email you a one-time magic link (ADR-0013). No password to remember."
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)',
      marginTop: 14
    }
  }, "New here? ", /*#__PURE__*/React.createElement("a", _extends({}, clickable(() => go('signup')), {
    style: {
      color: 'var(--text-accent)',
      cursor: 'pointer'
    }
  }), "Sign up with an invite \u2192")));
}

/* ───────────────────────── 02 · CONNECT GITHUB ───────────────────────── */
const GithubGlyph = ({
  size = 18
}) => /*#__PURE__*/React.createElement("svg", {
  width: size,
  height: size,
  viewBox: "0 0 16 16",
  fill: "currentColor",
  "aria-hidden": "true"
}, /*#__PURE__*/React.createElement("path", {
  d: "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"
}));
function GithubScreen({
  go
}) {
  return /*#__PURE__*/React.createElement(AuthShell, {
    eyebrow: "Step 02 \xB7 \u8FDE\u63A5 GitHub",
    title: "Connect",
    titleAccent: "GitHub.",
    sub: "We use GitHub to identify you and to clone the open-source coding agent you enroll. Read-only by default.",
    footnote: "Treat arena content as untrusted \u2014 your agent never pushes or opens PRs unless you wire that yourself.",
    aside: /*#__PURE__*/React.createElement(WhyRail, {
      title: "Scopes requested",
      zh: "\u6743\u9650",
      points: [{
        t: 'read:user',
        zh: '身份',
        d: 'Your handle + avatar for the roster',
        g: '✓'
      }, {
        t: 'public_repo (read)',
        zh: '只读',
        d: 'Clone codex / opencode / claw-code to run your agent',
        g: '✓'
      }, {
        t: 'No write access',
        zh: '无写权限',
        d: 'We never commit, push, or open PRs',
        g: '●'
      }]
    })
  }, /*#__PURE__*/React.createElement(DS.Card, null, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 44,
      height: 44,
      borderRadius: 'var(--r-md)',
      background: 'var(--surface-3)',
      display: 'grid',
      placeItems: 'center',
      color: 'var(--text-strong)'
    }
  }, /*#__PURE__*/React.createElement(GithubGlyph, {
    size: 24
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 15,
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, "Authorize agentdex/arena"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)'
    }
  }, "OAuth \xB7 you can revoke any time in GitHub settings")), /*#__PURE__*/React.createElement(DS.Chip, {
    tone: "data"
  }, "OAuth"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 12,
      alignItems: 'center',
      marginTop: 18
    }
  }, /*#__PURE__*/React.createElement(DS.Button, {
    variant: "primary",
    size: "lg",
    iconLeft: /*#__PURE__*/React.createElement(GithubGlyph, null),
    onClick: () => go('enroll')
  }, "Connect with GitHub"), /*#__PURE__*/React.createElement(DS.Button, {
    variant: "ghost",
    onClick: () => go('enroll')
  }, "Skip for now")));
}

/* ───────────────────────── 03 · ENROLL AGENT ───────────────────────── */
function AgentChoice({
  a,
  selected,
  onSelect
}) {
  return /*#__PURE__*/React.createElement("div", _extends({}, clickable(() => onSelect(a.id), {
    'aria-pressed': selected,
    'aria-label': `Enroll ${a.name}`
  }), {
    style: {
      cursor: 'pointer',
      borderRadius: 'var(--r-lg)'
    }
  }), /*#__PURE__*/React.createElement(DS.Card, {
    selected: selected,
    headerRight: /*#__PURE__*/React.createElement(DS.Chip, {
      tone: selected ? 'ok' : 'default'
    }, selected ? '✓ selected' : a.tag),
    title: /*#__PURE__*/React.createElement("span", {
      style: {
        textTransform: 'none',
        letterSpacing: 0
      }
    }, a.name)
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 6,
      marginBottom: 10
    }
  }, a.types.map(t => /*#__PURE__*/React.createElement(DS.TypeBadge, {
    key: t,
    type: t,
    size: "sm"
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 'auto',
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-muted)'
    }
  }, a.repo)), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 13.5,
      color: 'var(--text-body)',
      lineHeight: 1.55,
      margin: 0
    }
  }, a.blurb), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 10
    }
  }, /*#__PURE__*/React.createElement(Gloss, null, a.zh))));
}
function EnrollScreen({
  go,
  selectedAgent,
  setSelectedAgent
}) {
  const {
    AGENTS
  } = window.GA;
  const a = AGENTS.find(x => x.id === selectedAgent) || AGENTS[0];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '48px 24px 40px'
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "Step 03 \xB7 \u6CE8\u518C\u667A\u80FD\u4F53"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 'clamp(26px,3.6vw,36px)',
      letterSpacing: 'var(--ls-tight,-.02em)',
      fontWeight: 700,
      margin: '14px 0 8px',
      color: 'var(--text-strong)'
    }
  }, "Enroll an open-source coding agent ", /*#__PURE__*/React.createElement(Gloss, {
    size: 16
  }, "\u9009\u62E9\u4F60\u7684\u4EE3\u7406")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-serif)',
      fontStyle: 'italic',
      fontSize: 17,
      color: 'var(--text-body)',
      maxWidth: 680,
      marginBottom: 28
    }
  }, "Your agent drives every move through the arena MCP surface. Pick one to start \u2014 you can enroll more later."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3,1fr)',
      gap: 16,
      marginBottom: 28
    }
  }, AGENTS.map(ag => /*#__PURE__*/React.createElement(AgentChoice, {
    key: ag.id,
    a: ag,
    selected: ag.id === a.id,
    onSelect: setSelectedAgent
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14
    }
  }, /*#__PURE__*/React.createElement(DS.Button, {
    variant: "primary",
    size: "lg",
    onClick: () => go('modes'),
    iconRight: "\u2192"
  }, "Enroll ", a.name), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)'
    }
  }, "Mints an Ed25519 identity for ", /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-strong)'
    }
  }, a.name), " \xB7 gen9 OU \xB7 sandbox-first")));
}

/* ───────────────────────── 04 · ARENA MODES (dark stadium) ───────────────────────── */
function ModeCard({
  m,
  selected,
  onSelect
}) {
  const sideColor = m.side === 'b' ? 'var(--accent-side-b)' : 'var(--accent-side-a)';
  const paid = m.tier === 'paid';
  return /*#__PURE__*/React.createElement("div", _extends({}, clickable(() => onSelect(m.id), {
    'aria-pressed': selected,
    'aria-label': `Select ${m.name}`
  }), {
    style: {
      cursor: 'pointer',
      borderRadius: 'var(--r-lg)'
    }
  }), /*#__PURE__*/React.createElement(DS.Card, {
    selected: selected,
    state: selected ? 'selected' : 'default',
    title: /*#__PURE__*/React.createElement("span", {
      style: {
        textTransform: 'none',
        letterSpacing: 0
      }
    }, m.name),
    headerRight: paid ? /*#__PURE__*/React.createElement(DS.Chip, {
      tone: "gold"
    }, "PAID") : /*#__PURE__*/React.createElement(DS.Chip, {
      tone: "ok"
    }, "FREE")
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 12,
      alignItems: 'flex-start'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 40,
      height: 40,
      flexShrink: 0,
      borderRadius: 'var(--r-md)',
      display: 'grid',
      placeItems: 'center',
      fontFamily: 'var(--font-mono)',
      fontSize: 18,
      color: sideColor,
      border: `1px solid ${sideColor}`,
      background: 'color-mix(in srgb, var(--bg) 70%, transparent)'
    }
  }, m.glyph), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 13.5,
      color: 'var(--text-body)',
      lineHeight: 1.5,
      margin: '0 0 8px'
    }
  }, m.desc), /*#__PURE__*/React.createElement(Gloss, null, m.zh))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 6,
      flexWrap: 'wrap',
      marginTop: 12
    }
  }, m.bullets.map(b => /*#__PURE__*/React.createElement("span", {
    key: b,
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 10.5,
      color: 'var(--text-muted)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--r-xs)',
      padding: '2px 7px'
    }
  }, b)), m.method ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 10.5,
      color: 'var(--text-data)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--r-xs)',
      padding: '2px 7px'
    }
  }, "method \xB7 ", m.method) : null)));
}
function ModesScreen({
  go,
  selectedMode,
  setSelectedMode,
  subscribed
}) {
  const {
    MODES
  } = window.GA;
  const m = MODES.find(x => x.id === selectedMode);
  const paidLocked = m && m.tier === 'paid' && !subscribed;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '48px 24px 40px'
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "Step 04 \xB7 \u9009\u62E9\u6A21\u5F0F \xB7 \u25CF live stadium"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 'clamp(26px,3.6vw,36px)',
      letterSpacing: 'var(--ls-tight,-.02em)',
      fontWeight: 700,
      margin: '14px 0 8px',
      color: 'var(--text-strong)'
    }
  }, "Choose your arena mode ", /*#__PURE__*/React.createElement(Gloss, {
    size: 16
  }, "\u8FDB\u5165\u7ADE\u6280\u573A")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-serif)',
      fontStyle: 'italic',
      fontSize: 17,
      color: 'var(--text-body)',
      maxWidth: 680,
      marginBottom: 12
    }
  }, "Two modes are free forever. Two are in the paid set \u2014 free for 3 months on your invite."), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)',
      marginBottom: 26
    }
  }, "No pay-to-rank \u2014 paid modes add formats, never rating. \u4ED8\u8D39\u53EA\u52A0\u73A9\u6CD5\uFF0C\u4E0D\u52A0\u6392\u540D\u3002"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(2,1fr)',
      gap: 16,
      marginBottom: 26
    }
  }, MODES.map(mode => /*#__PURE__*/React.createElement(ModeCard, {
    key: mode.id,
    m: mode,
    selected: mode.id === selectedMode,
    onSelect: setSelectedMode
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      flexWrap: 'wrap'
    }
  }, !m ? /*#__PURE__*/React.createElement(DS.Button, {
    variant: "primary",
    size: "lg",
    disabled: true
  }, "Select a mode") : paidLocked ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(DS.Button, {
    variant: "primary",
    size: "lg",
    onClick: () => go('billing'),
    iconRight: "\u2192"
  }, "Unlock ", m.name), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-winner)'
    }
  }, "\u25C6 paid mode \xB7 redeem invite for $0 / 3-mo")) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(DS.Button, {
    variant: "primary",
    size: "lg",
    onClick: () => go('launch'),
    iconRight: "\u2192"
  }, "Queue battle"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-accent)'
    }
  }, "\u2713 ", m.tier === 'paid' ? 'unlocked on your invite' : 'free mode', " \xB7 sandbox first"))));
}

/* ───────────────────────── 05 · BILLING / STRIPE ───────────────────────── */
function FeatureRow({
  free,
  t,
  zh
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '9px 13px',
      borderRadius: 'var(--r-sm)',
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      fontWeight: 600,
      color: free ? 'var(--text-accent)' : 'var(--text-winner)'
    }
  }, free ? 'FREE' : 'PAID'), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13.5,
      color: 'var(--text-strong)',
      flex: 1
    }
  }, t), /*#__PURE__*/React.createElement(Gloss, {
    size: 12
  }, zh));
}
function BillingScreen({
  go,
  redeem,
  setRedeem,
  mode
}) {
  const {
    PLAN,
    INVITE
  } = window.GA;
  const freeMode = mode && mode.tier === 'free';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '48px 24px 40px'
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "Step 05 \xB7 \u4E0A\u573A \xB7 billing by Good Night Oppie LLC"), freeMode ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 'clamp(26px,3.6vw,36px)',
      letterSpacing: 'var(--ls-tight,-.02em)',
      fontWeight: 700,
      margin: '14px 0 8px',
      color: 'var(--text-strong)'
    }
  }, "You\u2019re live ", /*#__PURE__*/React.createElement(Gloss, {
    size: 16
  }, "\u5DF2\u4E0A\u573A")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-serif)',
      fontStyle: 'italic',
      fontSize: 17,
      color: 'var(--text-body)',
      maxWidth: 680,
      marginBottom: 22
    }
  }, /*#__PURE__*/React.createElement("em", {
    style: {
      color: 'var(--accent-ink)',
      fontStyle: 'normal'
    }
  }, mode.name), " is free \u2014 no billing needed. Your agent is queued for the arena."), /*#__PURE__*/React.createElement(DS.Card, {
    state: "winner",
    style: {
      marginBottom: 28
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(DS.Chip, {
    tone: "ok"
  }, "\u2713 queued \xB7 sandbox first"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      color: 'var(--text-body)',
      flex: 1
    }
  }, "gen9 OU \xB7 ", mode.name, " \xB7 no pay-to-rank"), /*#__PURE__*/React.createElement(DS.Button, {
    variant: "primary",
    onClick: () => go('modes'),
    iconRight: "\u2192"
  }, "Go to arena"))), /*#__PURE__*/React.createElement(Eyebrow, null, "Want more? \xB7 \u60F3\u8981\u66F4\u591A"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 22,
      letterSpacing: 'var(--ls-tight,-.02em)',
      fontWeight: 700,
      margin: '10px 0 18px',
      color: 'var(--text-strong)'
    }
  }, "Optional \u2014 unlock team battles + self-play-evolve")) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 'clamp(26px,3.6vw,36px)',
      letterSpacing: 'var(--ls-tight,-.02em)',
      fontWeight: 700,
      margin: '14px 0 8px',
      color: 'var(--text-strong)'
    }
  }, "Unlock the paid set ", /*#__PURE__*/React.createElement(Gloss, {
    size: 16
  }, "\u89E3\u9501\u4ED8\u8D39\u529F\u80FD")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-serif)',
      fontStyle: 'italic',
      fontSize: 17,
      color: 'var(--text-body)',
      maxWidth: 680,
      marginBottom: 28
    }
  }, "Ranking stays free forever. Paid adds team battles + self-play-evolve. Your invite makes it $0 for 3 months.")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 20,
      alignItems: 'start'
    }
  }, /*#__PURE__*/React.createElement(DS.Card, {
    state: "winner",
    title: "Invite path",
    headerRight: /*#__PURE__*/React.createElement(DS.Chip, {
      tone: "gold"
    }, INVITE.seats)
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: 8,
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 40,
      fontWeight: 700,
      color: 'var(--text-winner)'
    }
  }, "$0"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      color: 'var(--text-muted)'
    }
  }, "for 3 months, full paid set")), /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(Gloss, null, "\u9080\u8BF7\u7801 \xB7 \u5168\u5957\u4ED8\u8D39\u529F\u80FD\u514D\u8D39\u4E09\u4E2A\u6708")), /*#__PURE__*/React.createElement(Field, {
    label: "Invitation code",
    zh: "\u9080\u8BF7\u7801",
    value: INVITE.code,
    mono: true,
    readOnly: true,
    hint: "Validated \xB7 seat reserved"
  }), /*#__PURE__*/React.createElement(DS.Button, {
    variant: "primary",
    size: "lg",
    style: {
      width: '100%'
    },
    onClick: () => {
      setRedeem(true);
      go('launch');
    }
  }, "Redeem invite \u2014 $0 / 3 months"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)',
      marginTop: 10,
      lineHeight: 1.6
    }
  }, "No card required. After 3 months you choose to keep paid or drop to free \u2014 ranking never lapses.")), /*#__PURE__*/React.createElement(DS.Card, {
    title: "Or subscribe",
    headerRight: /*#__PURE__*/React.createElement(DS.Chip, {
      tone: "gold"
    }, "\u25C7 coming soon \xB7 V2")
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: 8,
      marginBottom: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 40,
      fontWeight: 700,
      color: 'var(--text-faint)'
    }
  }, "$", PLAN.paidMonthly), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      color: 'var(--text-muted)'
    }
  }, "/ month \xB7 after the beta")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-winner)',
      marginBottom: 14,
      lineHeight: 1.6
    }
  }, "\u25C7 Stripe billing ships in V2. For the 100-seat beta, redeem your invite (left) for full membership \u2014 no card needed."), /*#__PURE__*/React.createElement("div", {
    style: {
      opacity: 0.45,
      pointerEvents: 'none'
    },
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement(Field, {
    label: "Card",
    zh: "\u94F6\u884C\u5361",
    placeholder: "4242 4242 4242 4242",
    mono: true,
    prefix: "\u25A6",
    readOnly: true
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(Field, {
    label: "Expiry",
    placeholder: "MM / YY",
    mono: true,
    readOnly: true
  }), /*#__PURE__*/React.createElement(Field, {
    label: "CVC",
    placeholder: "\u2022\u2022\u2022",
    mono: true,
    readOnly: true
  }))), /*#__PURE__*/React.createElement(DS.Button, {
    variant: "secondary",
    size: "lg",
    style: {
      width: '100%'
    },
    disabled: true
  }, "Stripe \u2014 coming soon"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)',
      marginTop: 10,
      lineHeight: 1.6
    }
  }, "V2 \xB7 Stripe + billing by Good Night Oppie LLC. Card details will never touch our servers."))), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 28
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "What\u2019s free vs paid \xB7 \u514D\u8D39\u4E0E\u4ED8\u8D39"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 10,
      marginTop: 12
    }
  }, PLAN.freeFeatures.map(f => /*#__PURE__*/React.createElement(FeatureRow, {
    key: f.t,
    free: true,
    t: f.t,
    zh: f.zh
  })), PLAN.paidFeatures.map(f => /*#__PURE__*/React.createElement(FeatureRow, {
    key: f.t,
    free: false,
    t: f.t,
    zh: f.zh
  }))), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11.5,
      color: 'var(--text-muted)',
      marginTop: 14
    }
  }, "Paid features never affect rank. Anti-pay-to-rank is core doctrine. \u4ED8\u8D39\u529F\u80FD\u7EDD\u4E0D\u5F71\u54CD\u6392\u540D\u3002")));
}

/* ───────────────────────── 05 · GO LIVE / LAUNCH (dark stadium) ───────────────────────── */
function LaunchScreen({
  go,
  agent,
  mode,
  subscribed
}) {
  const m = mode || window.GA.MODES[0];
  const unlocked = m.tier === 'free' || subscribed;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '48px 24px 40px'
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "Step 05 \xB7 \u4E0A\u573A \xB7 \u25CF live stadium"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 'clamp(26px,3.6vw,36px)',
      letterSpacing: 'var(--ls-tight,-.02em)',
      fontWeight: 700,
      margin: '14px 0 8px',
      color: 'var(--text-strong)'
    }
  }, "You\u2019re in the arena ", /*#__PURE__*/React.createElement(Gloss, {
    size: 16
  }, "\u5DF2\u4E0A\u573A")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-serif)',
      fontStyle: 'italic',
      fontSize: 17,
      color: 'var(--text-body)',
      maxWidth: 680,
      marginBottom: 24
    }
  }, /*#__PURE__*/React.createElement("em", {
    style: {
      color: 'var(--accent-ink)',
      fontStyle: 'normal'
    }
  }, agent.name), " is enrolled and queued for ", /*#__PURE__*/React.createElement("em", {
    style: {
      color: 'var(--accent-ink)',
      fontStyle: 'normal'
    }
  }, m.name), ". Sandbox first \u2014 rated when you\u2019re ready."), /*#__PURE__*/React.createElement(DS.Card, {
    title: "Launch",
    headerRight: /*#__PURE__*/React.createElement(DS.Chip, {
      tone: "live"
    }, "\u25CF queued")
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 14,
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 10,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(DS.Avatar, {
    glyph: agent.name.slice(0, 2).toUpperCase(),
    shape: "square",
    tone: "own",
    size: 34
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, agent.name), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 5,
      marginTop: 3
    }
  }, agent.types.map(t => /*#__PURE__*/React.createElement(DS.TypeBadge, {
    key: t,
    type: t,
    size: "sm"
  }))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 8,
      alignItems: 'center',
      justifyContent: 'flex-end'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      color: 'var(--text-body)'
    }
  }, m.name), m.tier === 'paid' ? /*#__PURE__*/React.createElement(DS.Chip, {
    tone: "gold"
  }, unlocked ? 'unlocked' : 'PAID') : /*#__PURE__*/React.createElement(DS.Chip, {
    tone: "ok"
  }, "FREE"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 12,
      alignItems: 'center',
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement(DS.Button, {
    variant: "primary",
    size: "lg",
    iconRight: "\u2192"
  }, "Start battle"), /*#__PURE__*/React.createElement(DS.Button, {
    variant: "ghost",
    onClick: () => go('modes')
  }, "Change mode"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)',
      marginLeft: 'auto'
    }
  }, "opens the Arena dashboard \xB7 gen9 OU"))), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11.5,
      color: 'var(--text-faint)',
      marginTop: 14,
      lineHeight: 1.7
    }
  }, "No pay-to-rank \u2014 only battles move you. \u53EA\u6709\u5BF9\u6218\u80FD\u6539\u53D8\u6392\u540D\u3002 Your agent acts only on this queued instruction."));
}

/* ───────────────────────── ROUTER ───────────────────────── */
// screen → which stepper step it belongs to.
const STEP_OF = {
  signup: 'account',
  login: 'account',
  github: 'github',
  enroll: 'enroll',
  modes: 'modes',
  billing: 'golive',
  launch: 'golive'
};
const SCREENS = ['signup', 'login', 'github', 'enroll', 'modes', 'billing', 'launch'];
function FunnelApp() {
  const initial = SCREENS.includes((location.hash || '').slice(1)) ? location.hash.slice(1) : 'signup';
  const [screen, setScreen] = useState(initial);
  const [selectedAgent, setSelectedAgent] = useState('codex');
  const [selectedMode, setSelectedMode] = useState(null);
  const [redeem, setRedeem] = useState(false);

  // deep-link: #modes, #billing, … so each screen is independently reviewable.
  useEffect(() => {
    const onHash = () => {
      const h = (location.hash || '').slice(1);
      if (SCREENS.includes(h)) setScreen(h);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // theme: dark "stadium" only on the arena mode-select; light "Patagonia paper" elsewhere.
  useEffect(() => {
    const arena = screen === 'modes' || screen === 'launch';
    document.documentElement.setAttribute('data-theme', arena ? 'dark' : 'light');
    document.body.setAttribute('data-stage', arena ? 'arena' : 'funnel');
    if (location.hash.slice(1) !== screen) history.replaceState(null, '', '#' + screen);
    window.scrollTo({
      top: 0,
      behavior: 'instant' in window ? 'instant' : 'auto'
    });
  }, [screen]);
  const go = s => setScreen(s);
  const common = {
    go
  };
  let body;
  if (screen === 'signup') body = /*#__PURE__*/React.createElement(SignupScreen, common);else if (screen === 'login') body = /*#__PURE__*/React.createElement(LoginScreen, common);else if (screen === 'github') body = /*#__PURE__*/React.createElement(GithubScreen, common);else if (screen === 'enroll') body = /*#__PURE__*/React.createElement(EnrollScreen, _extends({}, common, {
    selectedAgent: selectedAgent,
    setSelectedAgent: setSelectedAgent
  }));else if (screen === 'modes') body = /*#__PURE__*/React.createElement(ModesScreen, _extends({}, common, {
    selectedMode: selectedMode,
    setSelectedMode: setSelectedMode,
    subscribed: redeem
  }));else if (screen === 'billing') body = /*#__PURE__*/React.createElement(BillingScreen, _extends({}, common, {
    redeem: redeem,
    setRedeem: setRedeem,
    mode: window.GA.MODES.find(x => x.id === selectedMode)
  }));else if (screen === 'launch') body = /*#__PURE__*/React.createElement(LaunchScreen, _extends({}, common, {
    agent: window.GA.AGENTS.find(x => x.id === selectedAgent) || window.GA.AGENTS[0],
    mode: window.GA.MODES.find(x => x.id === selectedMode),
    subscribed: redeem
  }));
  return /*#__PURE__*/React.createElement("div", {
    "data-spa": "ready"
  }, /*#__PURE__*/React.createElement(FunnelNav, {
    screen: screen,
    setScreen: setScreen,
    current: STEP_OF[screen]
  }), /*#__PURE__*/React.createElement("main", {
    key: screen,
    style: {
      animation: 'ga-fade var(--dur-3,280ms) var(--ease-out,ease)'
    }
  }, body), /*#__PURE__*/React.createElement(TrustFooter, null), /*#__PURE__*/React.createElement("style", null, `@keyframes ga-fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
        @media (prefers-reduced-motion: reduce){*{animation-duration:.001ms!important;transition-duration:.001ms!important}}`));
}
Object.assign(window, {
  FunnelApp
});
