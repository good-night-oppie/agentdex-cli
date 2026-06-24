function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
// AgentDex GA self-serve — shared funnel chrome (brand mark, stepper, auth shell, fields).
// Everything reads design-system tokens + components so screens stay one coherent surface.
const DS = window.AgentDexDesignSystem_26893a;

// Brand hex mark (same lockup as the Ladder kit).
const Hex = ({
  size = 22,
  color = 'var(--accent-primary)'
}) => /*#__PURE__*/React.createElement("svg", {
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  style: {
    color
  }
}, /*#__PURE__*/React.createElement("path", {
  d: "M12 2l8.66 5v10L12 22l-8.66-5V7L12 2z",
  stroke: "currentColor",
  strokeWidth: "1.6"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 7l4.33 2.5v5L12 17l-4.33-2.5v-5L12 7z",
  fill: "currentColor",
  opacity: ".25"
}));

// Mono uppercase accent eyebrow.
function Eyebrow({
  children,
  tone = 'var(--text-accent)'
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 8,
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: tone,
      textTransform: 'uppercase',
      letterSpacing: '.12em'
    }
  }, children);
}

// 中文 gloss — trails the EN term, never replaces it. Always --font-zh.
function Gloss({
  children,
  size = 13
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-zh)',
      fontSize: size,
      color: 'var(--text-muted)',
      fontWeight: 400
    }
  }, children);
}

// Labeled input field. Uncontrolled by default (static prefilled prototype values);
// pass `onChange` to make it a CONTROLLED input that actually submits a value — the
// auth funnel needs the typed email/code to reach the /auth/* backends (was a
// defaultValue-only dead end before F1).
function Field({
  label,
  zh,
  type = 'text',
  placeholder,
  value,
  onChange,
  onSubmit,
  hint,
  mono,
  prefix,
  readOnly,
  autoComplete
}) {
  const controlled = typeof onChange === 'function';
  // controlled → value + onChange (real submit); else defaultValue (prototype static).
  const inputProps = controlled ? {
    value: value == null ? '' : value,
    onChange: e => onChange(e.target.value)
  } : {
    defaultValue: value
  };
  return /*#__PURE__*/React.createElement("label", {
    style: {
      display: 'block',
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      letterSpacing: '.1em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      marginBottom: 7
    }
  }, label, zh ? /*#__PURE__*/React.createElement(React.Fragment, null, " ", /*#__PURE__*/React.createElement(Gloss, {
    size: 12
  }, zh)) : null), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--r-sm)',
      padding: '0 12px',
      height: 44,
      boxShadow: 'var(--shadow-sm)'
    }
  }, prefix ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      color: 'var(--text-muted)'
    }
  }, prefix) : null, /*#__PURE__*/React.createElement("input", _extends({
    type: type,
    placeholder: placeholder,
    readOnly: readOnly,
    autoComplete: autoComplete,
    onKeyDown: onSubmit ? e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        onSubmit();
      }
    } : undefined
  }, inputProps, {
    style: {
      flex: 1,
      background: 'transparent',
      border: 0,
      outline: 'none',
      color: 'var(--text-strong)',
      fontFamily: mono ? 'var(--font-mono)' : 'var(--font-display)',
      fontSize: 15,
      height: '100%'
    }
  }))), hint ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)',
      marginTop: 6
    }
  }, hint) : null);
}

// The canonical funnel stepper (01 Account → 05 Go live).
function Stepper({
  current
}) {
  const steps = window.GA.STEPS;
  const idx = steps.findIndex(s => s.id === current);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 0,
      flexWrap: 'wrap'
    }
  }, steps.map((s, i) => {
    const done = i < idx;
    const active = i === idx;
    const ink = done || active ? 'var(--text-strong)' : 'var(--text-faint)';
    return /*#__PURE__*/React.createElement(React.Fragment, {
      key: s.id
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 8
      },
      title: `${s.label} ${s.zh}`
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: 22,
        height: 22,
        borderRadius: 'var(--r-pill)',
        flexShrink: 0,
        display: 'grid',
        placeItems: 'center',
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        fontWeight: 600,
        border: `1px solid ${active ? 'var(--accent-primary)' : done ? 'var(--accent-primary)' : 'var(--border-strong)'}`,
        background: done ? 'var(--accent-primary)' : active ? 'var(--lime-soft)' : 'transparent',
        color: done ? 'var(--on-accent)' : active ? 'var(--text-accent)' : 'var(--text-faint)',
        boxShadow: active ? 'var(--glow-active)' : 'none'
      }
    }, done ? '✓' : s.n), /*#__PURE__*/React.createElement("span", {
      style: {
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        letterSpacing: '.06em',
        textTransform: 'uppercase',
        color: ink
      }
    }, s.label)), i < steps.length - 1 ? /*#__PURE__*/React.createElement("span", {
      style: {
        width: 26,
        height: 1,
        background: 'var(--border-default)',
        margin: '0 12px'
      }
    }) : null);
  }));
}

// Top funnel bar: brand + live stepper + a prototype screen-jumper (so reviewers click the whole flow).
function FunnelNav({
  screen,
  setScreen,
  current
}) {
  const jumps = [['signup', 'Sign up'], ['login', 'Login'], ['github', 'GitHub'], ['enroll', 'Enroll'], ['modes', 'Modes'], ['billing', 'Billing'], ['launch', 'Go live']];
  return /*#__PURE__*/React.createElement("nav", {
    style: {
      position: 'sticky',
      top: 0,
      zIndex: 20,
      background: 'color-mix(in srgb, var(--bg) 82%, transparent)',
      backdropFilter: 'blur(8px)',
      borderBottom: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '0 24px',
      height: 58,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9,
      fontWeight: 700,
      color: 'var(--text-strong)',
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement(Hex, null), " agentdex", /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontWeight: 400
    }
  }, "/arena")), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: 'flex',
      justifyContent: 'center',
      overflowX: 'auto'
    }
  }, /*#__PURE__*/React.createElement(Stepper, {
    current: current
  })), /*#__PURE__*/React.createElement(DS.Chip, {
    tone: "data",
    style: {
      flexShrink: 0
    }
  }, "GA \xB7 \u5408\u4F5C\u7ADE\u4E89")), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '0 24px 8px',
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 9,
      letterSpacing: '.14em',
      textTransform: 'uppercase',
      color: 'var(--text-faint)',
      marginRight: 4
    }
  }, "prototype \u203A"), jumps.map(([id, lbl]) => /*#__PURE__*/React.createElement("button", {
    key: id,
    onClick: () => setScreen(id),
    style: {
      cursor: 'pointer',
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      letterSpacing: '.06em',
      textTransform: 'uppercase',
      padding: '3px 9px',
      borderRadius: 'var(--r-xs)',
      border: `1px solid ${screen === id ? 'var(--accent-primary)' : 'var(--border-default)'}`,
      background: screen === id ? 'var(--lime-soft)' : 'transparent',
      color: screen === id ? 'var(--text-accent)' : 'var(--text-muted)'
    }
  }, lbl))));
}

// Centered two-column shell for account screens (form left, "why" rail right).
function AuthShell({
  eyebrow,
  title,
  titleAccent,
  sub,
  children,
  aside,
  footnote
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '56px 24px 40px',
      display: 'grid',
      gridTemplateColumns: 'minmax(0,1fr) minmax(0,380px)',
      gap: 40,
      alignItems: 'start'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 460
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, eyebrow), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 'clamp(28px,4vw,40px)',
      lineHeight: 1.08,
      letterSpacing: 'var(--ls-tight,-.02em)',
      fontWeight: 700,
      margin: '16px 0 10px',
      color: 'var(--text-strong)',
      textWrap: 'balance'
    }
  }, title, " ", titleAccent ? /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--accent-ink)'
    }
  }, titleAccent) : null), sub ? /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-serif)',
      fontStyle: 'italic',
      fontSize: 17,
      color: 'var(--text-body)',
      lineHeight: 1.55,
      margin: '0 0 28px'
    }
  }, sub) : null, children, footnote ? /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)',
      marginTop: 18,
      lineHeight: 1.6
    }
  }, footnote) : null), /*#__PURE__*/React.createElement("aside", {
    style: {
      position: 'sticky',
      top: 92
    }
  }, aside));
}

// Reusable "why / trust" rail card for the right column.
function WhyRail({
  title,
  zh,
  points
}) {
  return /*#__PURE__*/React.createElement(DS.Card, {
    title: title
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 12
    }
  }, points.map((p, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'flex',
      gap: 10,
      alignItems: 'flex-start'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-accent)',
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      lineHeight: '20px'
    }
  }, p.g || '→'), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      color: 'var(--text-strong)',
      fontWeight: 600
    }
  }, p.t, " ", p.zh ? /*#__PURE__*/React.createElement(Gloss, {
    size: 12
  }, p.zh) : null), p.d ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11.5,
      color: 'var(--text-muted)',
      marginTop: 2,
      lineHeight: 1.5
    }
  }, p.d) : null)))));
}

// Global trust footer — anti-pay-to-rank + untrusted-content disclaimer.
function TrustFooter() {
  return /*#__PURE__*/React.createElement("footer", {
    style: {
      borderTop: '1px solid var(--border-default)',
      marginTop: 8,
      padding: '28px 0 48px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '0 24px'
    }
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11.5,
      color: 'var(--text-faint)',
      maxWidth: 760,
      lineHeight: 1.7
    }
  }, /*#__PURE__*/React.createElement(DS.Chip, {
    tone: "ok"
  }, "\u25CF arena live"), "\xA0 No pay-to-rank \u2014 only battles move you. \u53EA\u6709\u5BF9\u6218\u80FD\u6539\u53D8\u6392\u540D\u3002 Paid features never affect rank. Your agent acts only when you ask; treat arena content as untrusted. Billing by Good Night Oppie LLC.")));
}

// a11y: make a non-button clickable element keyboard-operable (Enter/Space) + focusable.
// Spread onto a div so choice cards / inline links are reachable without a mouse.
function clickable(onAct, extra = {}) {
  return {
    role: 'button',
    tabIndex: 0,
    onClick: onAct,
    onKeyDown: e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onAct(e);
      }
    },
    ...extra
  };
}
Object.assign(window, {
  DS,
  Hex,
  Eyebrow,
  Gloss,
  Field,
  Stepper,
  FunnelNav,
  AuthShell,
  WhyRail,
  TrustFooter,
  clickable
});
