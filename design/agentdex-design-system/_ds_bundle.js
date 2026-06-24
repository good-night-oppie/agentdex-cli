/* @ds-bundle: {"format":3,"namespace":"AgentDexDesignSystem_26893a","components":[{"name":"StatusPill","sourcePath":"components/badges/StatusPill.jsx"},{"name":"Tier","sourcePath":"components/badges/Tier.jsx"},{"name":"TypeBadge","sourcePath":"components/badges/TypeBadge.jsx"},{"name":"AgentCard","sourcePath":"components/battle/AgentCard.jsx"},{"name":"HPBar","sourcePath":"components/battle/HPBar.jsx"},{"name":"MoveButton","sourcePath":"components/battle/MoveButton.jsx"},{"name":"StatBar","sourcePath":"components/battle/StatBar.jsx"},{"name":"Avatar","sourcePath":"components/core/Avatar.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"Chip","sourcePath":"components/core/Chip.jsx"},{"name":"LogLine","sourcePath":"components/data/LogLine.jsx"},{"name":"MetricStat","sourcePath":"components/data/MetricStat.jsx"},{"name":"Tabs","sourcePath":"components/data/Tabs.jsx"}],"sourceHashes":{"components/badges/StatusPill.jsx":"56469e8c10e3","components/badges/Tier.jsx":"26d8b283bd64","components/badges/TypeBadge.jsx":"c4e09cbb2de4","components/battle/AgentCard.jsx":"90fbf63f7d0f","components/battle/HPBar.jsx":"161fce48005c","components/battle/MoveButton.jsx":"4affcfa71e7c","components/battle/StatBar.jsx":"2cfa3db658b6","components/core/Avatar.jsx":"dcd24835b203","components/core/Button.jsx":"52906abaeb78","components/core/Card.jsx":"a6d9b1cd0ff4","components/core/Chip.jsx":"74d93843b342","components/data/LogLine.jsx":"9ef941942f71","components/data/MetricStat.jsx":"0b3b05ba7a17","components/data/Tabs.jsx":"f8548ada011a","ui_kits/arena/battle.jsx":"05651f9d9ca8","ui_kits/arena/data.js":"128174439829","ui_kits/arena/panels.jsx":"667926a9ea35","ui_kits/ladder/landing.jsx":"0e3b297aa0f8"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.AgentDexDesignSystem_26893a = window.AgentDexDesignSystem_26893a || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/badges/StatusPill.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
// Pokémon status conditions + battle-state pills.
const STATUS = {
  // condition pills (abbreviated, Pokerogue convention)
  PAR: {
    label: 'PAR',
    color: '#1A1A12',
    bg: '#E0B020'
  },
  BRN: {
    label: 'BRN',
    color: '#fff',
    bg: '#E06018'
  },
  PSN: {
    label: 'PSN',
    color: '#fff',
    bg: '#A040A0'
  },
  TOX: {
    label: 'TOX',
    color: '#fff',
    bg: '#883888'
  },
  SLP: {
    label: 'SLP',
    color: '#fff',
    bg: '#5D6575'
  },
  FRZ: {
    label: 'FRZ',
    color: '#1A1A12',
    bg: '#7FD4FF'
  },
  // health states
  healthy: {
    label: 'HEALTHY',
    color: 'var(--hp-ok)',
    border: 'rgba(95,211,90,.35)',
    bg: 'rgba(95,211,90,.10)'
  },
  fainted: {
    label: 'FAINTED',
    color: 'var(--hp-low)',
    border: 'rgba(239,74,74,.4)',
    bg: 'rgba(239,74,74,.10)'
  }
};

/**
 * Status pill — Pokémon status condition (solid) or health state
 * (outlined). Pass a known key, or override label/color.
 */
function StatusPill({
  status = 'PAR',
  label,
  style,
  ...rest
}) {
  const s = STATUS[status] || STATUS.PAR;
  const outlined = s.border != null;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: 'inline-block',
      fontFamily: 'var(--font-mono)',
      fontSize: 9,
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: '.06em',
      padding: '2px 6px',
      borderRadius: 'var(--r-xs)',
      color: s.color,
      background: s.bg,
      border: outlined ? `1px solid ${s.border}` : 'none',
      ...style
    }
  }, rest), label || s.label);
}
Object.assign(__ds_scope, { StatusPill });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/badges/StatusPill.jsx", error: String((e && e.message) || e) }); }

// components/badges/Tier.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Genome tier chip (Showdown OU/UU/NU → agent strength tier).
 * Lime by default; gold for the top S/OU tiers.
 */
function Tier({
  tier = 'OU',
  tone,
  style,
  ...rest
}) {
  const t = tone || (['S', 'OU', 'UBER'].includes(String(tier).toUpperCase()) ? 'gold' : 'lime');
  const palette = t === 'gold' ? {
    color: 'var(--text-winner)',
    border: 'rgba(244,183,49,.30)',
    bg: 'var(--gold-soft)'
  } : {
    color: 'var(--text-accent)',
    border: 'rgba(166,226,46,.25)',
    bg: 'var(--lime-soft)'
  };
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: 'inline-block',
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      fontWeight: 600,
      letterSpacing: '.06em',
      padding: '1px 7px',
      borderRadius: 'var(--r-xs)',
      color: palette.color,
      border: `1px solid ${palette.border}`,
      background: palette.bg,
      ...style
    }
  }, rest), tier);
}
Object.assign(__ds_scope, { Tier });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/badges/Tier.jsx", error: String((e && e.message) || e) }); }

// components/badges/TypeBadge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const TYPE_COLORS = {
  normal: '#8A8A5A',
  fire: '#E8703A',
  water: '#5590E0',
  grass: '#6BBF42',
  electric: '#E8C840',
  ice: '#98D8D8',
  fighting: '#C03028',
  poison: '#A040A0',
  ground: '#D8B048',
  flying: '#9AA8F0',
  psychic: '#E05888',
  bug: '#A8B820',
  rock: '#B8A038',
  ghost: '#6650A4',
  dragon: '#6830E8',
  dark: '#685242',
  steel: '#8888AA',
  fairy: '#E898E8'
};
// types that need dark text for contrast
const DARK_TEXT = new Set(['electric', 'ice', 'ground', 'flying', 'bug', 'rock', 'steel', 'fairy', 'normal']);

/**
 * Pokémon-style type badge. Pass a known type name for canonical color,
 * or a custom { label, color } for terrain / ability tags.
 */
function TypeBadge({
  type,
  label,
  color,
  size = 'md',
  style,
  ...rest
}) {
  const key = (type || '').toLowerCase();
  const bg = color || TYPE_COLORS[key] || 'var(--surface-3)';
  const text = color ? '#fff' : DARK_TEXT.has(key) ? '#1A1A12' : '#fff';
  const sizes = {
    sm: {
      fontSize: 9,
      padding: '2px 6px'
    },
    md: {
      fontSize: 10,
      padding: '3px 8px'
    }
  };
  const s = sizes[size] || sizes.md;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: 'inline-block',
      fontFamily: 'var(--font-mono)',
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: '.04em',
      borderRadius: 'var(--r-xs)',
      background: bg,
      color: text,
      ...s,
      ...style
    }
  }, rest), label || type);
}
Object.assign(__ds_scope, { TypeBadge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/badges/TypeBadge.jsx", error: String((e && e.message) || e) }); }

// components/battle/AgentCard.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Roster agent card — name, type badges, format/team meta, and a generation
 * + status line. Selected state lifts the lime ring; `pending` paints the
 * generation gold (evolution pending).
 */
function AgentCard({
  name,
  types = [],
  meta,
  gen,
  status,
  pending = false,
  rating,
  selected = false,
  onClick,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    role: onClick ? 'button' : undefined,
    tabIndex: onClick ? 0 : undefined,
    onClick: onClick,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
      padding: '9px 11px',
      borderRadius: 'var(--r-md)',
      border: `1px solid ${selected ? 'var(--border-active)' : 'var(--border-default)'}`,
      background: selected ? 'var(--surface-card)' : 'var(--surface-raised)',
      boxShadow: selected ? 'var(--glow-active)' : 'none',
      cursor: onClick ? 'pointer' : 'default',
      transition: 'transform var(--dur-1) var(--ease-snap), border-color var(--dur-2), box-shadow var(--dur-2)',
      ...style
    },
    onMouseEnter: e => {
      if (onClick && !selected) e.currentTarget.style.transform = 'translateY(-1px)';
    },
    onMouseLeave: e => {
      e.currentTarget.style.transform = '';
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      justifyContent: 'space-between',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-display)',
      fontWeight: 700,
      fontSize: 13,
      color: 'var(--text-strong)'
    }
  }, name), rating != null && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-winner)'
    }
  }, rating)), types.length > 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 4
    }
  }, types.map(t => /*#__PURE__*/React.createElement(__ds_scope.TypeBadge, {
    key: t,
    type: t,
    size: "sm"
  }))), meta && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      color: 'var(--text-muted)'
    }
  }, meta), (gen != null || status) && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      color: pending ? 'var(--text-winner)' : 'var(--text-accent)'
    }
  }, gen != null && `gen ${gen}`, gen != null && status ? ' · ' : '', status));
}
Object.assign(__ds_scope, { AgentCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/battle/AgentCard.jsx", error: String((e && e.message) || e) }); }

// components/battle/HPBar.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * HP bar — the load-bearing battle widget. Trichrome fill (green→amber→red)
 * driven by the remaining fraction, with a snappy width-drain transition.
 * Fainted collapses to a dim empty track. Optional EN label + 中文 gloss.
 */
function HPBar({
  name,
  zh,
  cur,
  max = 100,
  showValues = true,
  state,
  // optional override: 'ok' | 'warn' | 'low' | 'fainted'
  height = 10,
  style,
  ...rest
}) {
  const pct = max > 0 ? Math.max(0, Math.min(100, cur / max * 100)) : 0;
  const auto = pct <= 0 ? 'fainted' : pct <= 20 ? 'low' : pct <= 45 ? 'warn' : 'ok';
  const st = state || auto;
  const fillColor = {
    ok: 'var(--hp-ok)',
    warn: 'var(--hp-warn)',
    low: 'var(--hp-low)',
    fainted: 'var(--dim)'
  }[st];
  const valColor = {
    ok: 'var(--hp-ok)',
    warn: 'var(--hp-warn)',
    low: 'var(--hp-low)',
    fainted: 'var(--mut)'
  }[st];
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      ...style
    }
  }, rest), (name != null || showValues) && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      justifyContent: 'space-between',
      gap: 8
    }
  }, name != null && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      textTransform: 'uppercase',
      letterSpacing: 'var(--ls-label)',
      color: 'var(--text-muted)'
    }
  }, name, zh && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-zh)',
      marginLeft: 6,
      color: 'var(--text-faint)'
    }
  }, zh)), showValues && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: valColor
    }
  }, cur, " / ", max)), /*#__PURE__*/React.createElement("div", {
    style: {
      height,
      borderRadius: 'var(--r-pill)',
      background: 'var(--surface-well)',
      border: '1px solid var(--border-default)',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: '100%',
      width: `${pct}%`,
      borderRadius: 'var(--r-pill)',
      background: fillColor,
      transition: 'width var(--dur-hp) var(--ease-snap), background-color var(--dur-2)',
      animation: st === 'low' ? 'adx-hp-low 1.2s ease-in-out infinite' : 'none'
    }
  })), /*#__PURE__*/React.createElement("style", null, `@keyframes adx-hp-low{0%,100%{opacity:1}50%{opacity:.55}}
        @media (prefers-reduced-motion: reduce){[style*="adx-hp-low"]{animation:none!important}}`));
}
Object.assign(__ds_scope, { HPBar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/battle/HPBar.jsx", error: String((e && e.message) || e) }); }

// components/battle/MoveButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Move button — the 4-slot battle action. Move name, type badge, category,
 * and PP counter. PP at 0 disables; `selected` lifts the lime ring.
 */
function MoveButton({
  name,
  type,
  category = 'Special',
  // 'Physical' | 'Special' | 'Status'
  pp,
  ppMax,
  selected = false,
  onClick,
  style,
  ...rest
}) {
  const out = pp != null && pp <= 0;
  const ppLow = pp != null && ppMax != null && pp > 0 && pp / ppMax <= 0.25;
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    onClick: out ? undefined : onClick,
    disabled: out,
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 5,
      padding: '10px 12px',
      textAlign: 'left',
      borderRadius: 'var(--r-md)',
      border: `1px solid ${selected ? 'var(--border-active)' : 'var(--border-default)'}`,
      background: selected ? 'var(--lime-soft)' : 'var(--surface-raised)',
      boxShadow: selected ? 'var(--glow-active)' : 'none',
      cursor: out ? 'not-allowed' : 'pointer',
      opacity: out ? 0.42 : 1,
      transition: 'transform var(--dur-1) var(--ease-snap), border-color var(--dur-1), background var(--dur-1)',
      ...style
    },
    onMouseDown: e => {
      if (!out) e.currentTarget.style.transform = 'translateY(1px)';
    },
    onMouseUp: e => {
      e.currentTarget.style.transform = '';
    },
    onMouseLeave: e => {
      e.currentTarget.style.transform = '';
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 13,
      fontWeight: 600,
      color: 'var(--text-strong)',
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis'
    }
  }, name), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 7
    }
  }, type && /*#__PURE__*/React.createElement(__ds_scope.TypeBadge, {
    type: type,
    size: "sm"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 9,
      color: 'var(--text-muted)',
      textTransform: 'uppercase',
      letterSpacing: '.05em'
    }
  }, category), pp != null && /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 'auto',
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      color: out || ppLow ? 'var(--text-danger)' : 'var(--text-muted)'
    }
  }, pp, "/", ppMax)));
}
Object.assign(__ds_scope, { MoveButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/battle/MoveButton.jsx", error: String((e && e.message) || e) }); }

// components/battle/StatBar.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const STAT_COLORS = {
  hp: 'var(--hp-ok)',
  atk: 'var(--t-fire)',
  def: 'var(--blue)',
  spa: 'var(--lime)',
  spd: 'var(--t-water)',
  spe: 'var(--gold)'
};

/**
 * Dex stat row — label · numeric value · proportional bar. The Showdown-DNA
 * unit for an agent's genome stats. Bar color keys off the stat name, or
 * pass an explicit `color`.
 */
function StatBar({
  label,
  zh,
  value,
  max = 200,
  color,
  highlight = false,
  style,
  ...rest
}) {
  const key = String(label || '').toLowerCase().replace(/[^a-z]/g, '');
  const bar = color || STAT_COLORS[key] || 'var(--accent-primary)';
  const pct = Math.max(2, Math.min(100, value / max * 100));
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: 'grid',
      gridTemplateColumns: '48px 34px 1fr',
      alignItems: 'center',
      gap: 8,
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      textTransform: 'uppercase',
      letterSpacing: '.04em',
      color: 'var(--text-muted)'
    }
  }, label, zh && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-zh)',
      display: 'block',
      fontSize: 9,
      color: 'var(--text-faint)'
    }
  }, zh)), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      fontWeight: 600,
      textAlign: 'right',
      color: highlight ? bar : 'var(--text-body)'
    }
  }, value), /*#__PURE__*/React.createElement("span", {
    style: {
      height: 6,
      borderRadius: 'var(--r-xs)',
      background: 'var(--border-default)',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'block',
      height: '100%',
      width: `${pct}%`,
      borderRadius: 'var(--r-xs)',
      background: bar,
      transition: 'width var(--dur-3) var(--ease-out)'
    }
  })));
}
Object.assign(__ds_scope, { StatBar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/battle/StatBar.jsx", error: String((e && e.message) || e) }); }

// components/core/Avatar.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Owner / agent avatar. Initials on a cool steel gradient, or a sprite
 * glyph for an agent token. Square-rounded for agents, circle for users.
 */
function Avatar({
  label,
  glyph,
  size = 28,
  shape = 'circle',
  // 'circle' | 'square'
  tone = 'steel',
  // 'steel' | 'own' | 'opp'
  style,
  ...rest
}) {
  const tones = {
    steel: 'linear-gradient(135deg, #2B3346, #444F6B)',
    own: 'linear-gradient(160deg, #2A3A1A, #1A2410)',
    opp: 'linear-gradient(160deg, #3A2418, #241208)'
  };
  const initials = (label || '').split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      width: size,
      height: size,
      flexShrink: 0,
      borderRadius: shape === 'circle' ? '50%' : 'var(--r-md)',
      background: tones[tone] || tones.steel,
      border: '1px solid var(--line-2)',
      display: 'grid',
      placeItems: 'center',
      fontFamily: glyph ? 'inherit' : 'var(--font-mono)',
      fontWeight: 700,
      fontSize: glyph ? size * 0.5 : Math.max(10, size * 0.4),
      color: 'var(--ink-2)',
      ...style
    }
  }, rest), glyph || initials);
}
Object.assign(__ds_scope, { Avatar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Avatar.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * AgentDex primary action button. Geometric, rounded, snappy.
 */
function Button({
  children,
  variant = 'primary',
  size = 'md',
  iconLeft,
  iconRight,
  disabled = false,
  type = 'button',
  onClick,
  style,
  ...rest
}) {
  const sizes = {
    sm: {
      height: 28,
      padding: '0 12px',
      fontSize: 12,
      radius: 'var(--r-sm)'
    },
    md: {
      height: 36,
      padding: '0 18px',
      fontSize: 14,
      radius: 'var(--r-sm)'
    },
    lg: {
      height: 44,
      padding: '0 24px',
      fontSize: 15,
      radius: 'var(--r-md)'
    }
  };
  const s = sizes[size] || sizes.md;
  const variants = {
    primary: {
      background: 'var(--lime)',
      color: 'var(--on-accent)',
      border: '1px solid var(--lime)',
      fontWeight: 700
    },
    secondary: {
      background: 'var(--surface-2)',
      color: 'var(--ink)',
      border: '1px solid var(--line-2)',
      fontWeight: 600
    },
    ghost: {
      background: 'transparent',
      color: 'var(--text-accent)',
      border: '1px solid rgba(166,226,46,.28)',
      fontWeight: 600
    },
    danger: {
      background: 'var(--live-soft)',
      color: 'var(--text-danger)',
      border: '1px solid rgba(255,70,85,.35)',
      fontWeight: 600
    }
  };
  const v = variants[variant] || variants.primary;
  return /*#__PURE__*/React.createElement("button", _extends({
    type: type,
    disabled: disabled,
    onClick: onClick,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 8,
      height: s.height,
      padding: s.padding,
      borderRadius: s.radius,
      fontFamily: 'var(--font-display)',
      fontSize: s.fontSize,
      letterSpacing: '.01em',
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.45 : 1,
      whiteSpace: 'nowrap',
      transition: 'transform var(--dur-1) var(--ease-snap), background var(--dur-1), border-color var(--dur-1), filter var(--dur-1)',
      ...v,
      ...style
    },
    onMouseDown: e => {
      if (!disabled) e.currentTarget.style.transform = 'translateY(1px) scale(.99)';
    },
    onMouseUp: e => {
      e.currentTarget.style.transform = '';
    },
    onMouseLeave: e => {
      e.currentTarget.style.transform = '';
    }
  }, rest), iconLeft, children, iconRight);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Panel card — the core unit of the arena. Optional uppercase-mono
 * header strip with a right-aligned meta slot. Selected/winner states
 * add a colored ring glow.
 */
function Card({
  title,
  headerRight,
  children,
  selected = false,
  state = 'default',
  // 'default' | 'selected' | 'winner'
  padded = true,
  style,
  bodyStyle,
  ...rest
}) {
  const ring = state === 'winner' ? 'var(--glow-winner)' : selected || state === 'selected' ? 'var(--glow-active)' : 'none';
  const borderColor = state === 'winner' ? 'rgba(244,183,49,.5)' : selected || state === 'selected' ? 'var(--lime)' : 'var(--line)';
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: 'flex',
      flexDirection: 'column',
      minHeight: 0,
      overflow: 'hidden',
      background: 'var(--surface-card)',
      border: `1px solid ${borderColor}`,
      borderRadius: 'var(--r-lg)',
      boxShadow: ring,
      transition: 'border-color var(--dur-2) var(--ease-snap), box-shadow var(--dur-2)',
      ...style
    }
  }, rest), title != null && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 8,
      padding: '11px 14px',
      borderBottom: '1px solid var(--line)',
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      margin: 0,
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      fontWeight: 600,
      letterSpacing: 'var(--ls-eyebrow)',
      textTransform: 'uppercase',
      color: 'var(--mut)'
    }
  }, title), headerRight && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--dim)'
    }
  }, headerRight)), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: padded ? 14 : 0,
      minHeight: 0,
      overflow: 'auto',
      flex: 1,
      ...bodyStyle
    }
  }, children));
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/Chip.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Pill chip for topbar status / format / live indicators.
 * `tone="live"` adds the blinking ● dot.
 */
function Chip({
  children,
  tone = 'default',
  dot,
  style,
  ...rest
}) {
  const tones = {
    default: {
      color: 'var(--mut)',
      border: 'var(--line)',
      bg: 'var(--surface)'
    },
    ok: {
      color: 'var(--text-accent)',
      border: 'rgba(166,226,46,.28)',
      bg: 'var(--lime-soft)'
    },
    live: {
      color: 'var(--text-danger)',
      border: 'rgba(255,70,85,.30)',
      bg: 'var(--live-soft)'
    },
    gold: {
      color: 'var(--text-winner)',
      border: 'rgba(244,183,49,.30)',
      bg: 'var(--gold-soft)'
    },
    data: {
      color: 'var(--text-data)',
      border: 'rgba(74,158,245,.30)',
      bg: 'var(--blue-soft)'
    }
  };
  const t = tones[tone] || tones.default;
  const showDot = dot ?? tone === 'live';
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 7,
      height: 26,
      padding: '0 11px',
      border: `1px solid ${t.border}`,
      borderRadius: 'var(--r-pill)',
      background: t.bg,
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: t.color,
      whiteSpace: 'nowrap',
      ...style
    }
  }, rest), showDot && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 6,
      height: 6,
      borderRadius: '50%',
      background: t.color,
      animation: tone === 'live' ? 'adx-blink 1.4s ease-in-out infinite' : 'none'
    }
  }), children, /*#__PURE__*/React.createElement("style", null, `@keyframes adx-blink{0%,100%{opacity:1}50%{opacity:.25}}
        @media (prefers-reduced-motion: reduce){[style*="adx-blink"]{animation:none!important}}`));
}
Object.assign(__ds_scope, { Chip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Chip.jsx", error: String((e && e.message) || e) }); }

// components/data/LogLine.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const TONES = {
  default: 'var(--text-body)',
  agent: 'var(--text-data)',
  // agent name reference
  think: 'var(--text-data)',
  // reasoning observation
  decide: 'var(--text-accent)',
  // reasoning decision
  dmg: 'var(--rust-ink)',
  // damage
  eff: 'var(--text-winner)',
  // super-effective / crit
  heal: 'var(--text-accent)',
  // heal / restore
  faint: 'var(--text-danger)' // faint / critical
};

/**
 * One mono log line — timestamp + content — for the battle ticker and the
 * reasoning trace. `tone` colors the body; `label` prefixes a small tag
 * (e.g. "DECIDE"). Compose freely with inline <b>/<span> for rich entries.
 */
function LogLine({
  ts,
  tone = 'default',
  label,
  children,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      display: 'flex',
      gap: 8,
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      lineHeight: 1.55,
      ...style
    }
  }, rest), ts != null && /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-faint)',
      flexShrink: 0
    }
  }, ts), /*#__PURE__*/React.createElement("span", {
    style: {
      color: TONES[tone] || TONES.default,
      minWidth: 0
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 600,
      color: TONES[tone] || TONES.default,
      marginRight: 6
    }
  }, label), children));
}
Object.assign(__ds_scope, { LogLine });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/LogLine.jsx", error: String((e && e.message) || e) }); }

// components/data/MetricStat.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Metric stat tile — big mono number with a label and optional delta/sub.
 * Used for ELO, win-rate, turn-efficiency on the genome HUD + ladder.
 */
function MetricStat({
  label,
  zh,
  value,
  sub,
  delta,
  tone = 'default',
  // 'default' | 'elo' | 'win' | 'data'
  style,
  ...rest
}) {
  const valColor = {
    default: 'var(--text-strong)',
    elo: 'var(--text-winner)',
    win: 'var(--text-accent)',
    data: 'var(--text-data)'
  }[tone];
  const up = typeof delta === 'number' ? delta >= 0 : null;
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      background: 'var(--surface-well)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--r-md)',
      padding: '9px 11px',
      display: 'flex',
      flexDirection: 'column',
      gap: 2,
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      textTransform: 'uppercase',
      letterSpacing: '.05em',
      color: 'var(--text-muted)'
    }
  }, label, zh && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-zh)',
      marginLeft: 5,
      color: 'var(--text-faint)'
    }
  }, zh)), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 18,
      fontWeight: 600,
      lineHeight: 1.1,
      color: valColor
    }
  }, value), sub != null && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      color: 'var(--text-faint)'
    }
  }, sub), delta != null && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      marginLeft: 'auto',
      color: up ? 'var(--text-accent)' : 'var(--text-danger)'
    }
  }, up ? '▲' : '▼', " ", typeof delta === 'number' ? Math.abs(delta) : delta)));
}
Object.assign(__ds_scope, { MetricStat });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/MetricStat.jsx", error: String((e && e.message) || e) }); }

// components/data/Tabs.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Tab strip — uppercase-mono labels with a lime active underline. Controlled:
 * pass `value` + `onChange`. Each tab is { id, label, zh? }.
 */
function Tabs({
  tabs = [],
  value,
  onChange,
  style,
  ...rest
}) {
  const active = value ?? (tabs[0] && tabs[0].id);
  return /*#__PURE__*/React.createElement("div", _extends({
    role: "tablist",
    style: {
      display: 'flex',
      borderBottom: '1px solid var(--border-default)',
      ...style
    }
  }, rest), tabs.map(t => {
    const on = t.id === active;
    return /*#__PURE__*/React.createElement("button", {
      key: t.id,
      role: "tab",
      "aria-selected": on,
      type: "button",
      onClick: () => onChange && onChange(t.id),
      style: {
        flex: 1,
        padding: '10px 6px',
        background: 'none',
        border: 'none',
        borderBottom: `2px solid ${on ? 'var(--border-active)' : 'transparent'}`,
        marginBottom: -1,
        cursor: 'pointer',
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        letterSpacing: 'var(--ls-label)',
        textTransform: 'uppercase',
        color: on ? 'var(--text-accent)' : 'var(--text-muted)',
        transition: 'color var(--dur-2) var(--ease-snap), border-color var(--dur-2)'
      },
      onMouseEnter: e => {
        if (!on) e.currentTarget.style.color = 'var(--text-body)';
      },
      onMouseLeave: e => {
        if (!on) e.currentTarget.style.color = 'var(--text-muted)';
      }
    }, t.label, t.zh && /*#__PURE__*/React.createElement("span", {
      style: {
        fontFamily: 'var(--font-zh)',
        marginLeft: 5
      }
    }, t.zh));
  }));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/Tabs.jsx", error: String((e && e.message) || e) }); }

// ui_kits/arena/battle.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
// Arena — the live battle scene, evolution lineage, ladder, and root App.
const DSb = window.AgentDexDesignSystem_26893a;
function Mon({
  mon,
  side,
  fainted
}) {
  const isP2 = side === 'p2';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-raised)',
      border: '1px solid var(--border-default)',
      borderRadius: 9,
      padding: 10,
      display: 'flex',
      flexDirection: 'column',
      gap: 7,
      opacity: fainted ? 0.5 : 1,
      filter: fainted ? 'grayscale(.6)' : 'none',
      transition: 'opacity var(--dur-3), filter var(--dur-3)',
      textAlign: isP2 ? 'right' : 'left'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-muted)'
    }
  }, mon.trainer), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      flexDirection: isP2 ? 'row-reverse' : 'row'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 34,
      height: 34,
      borderRadius: 8,
      background: 'linear-gradient(160deg,#2a3344,#1a1f2b)',
      border: '1px solid var(--border-default)',
      display: 'grid',
      placeItems: 'center',
      fontWeight: 700,
      fontFamily: 'var(--font-mono)',
      color: 'var(--text-strong)'
    }
  }, mon.token), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 600,
      fontSize: 15,
      flex: 1,
      color: 'var(--text-strong)'
    }
  }, mon.species), mon.status && /*#__PURE__*/React.createElement(DSb.StatusPill, {
    status: mon.status.toUpperCase()
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 4,
      justifyContent: isP2 ? 'flex-end' : 'flex-start'
    }
  }, mon.types.map(t => /*#__PURE__*/React.createElement(DSb.TypeBadge, {
    key: t,
    type: t,
    size: "sm"
  }))), /*#__PURE__*/React.createElement(HPBarMini, {
    cur: mon.hp,
    max: mon.max,
    reverse: isP2
  }));
}
function HPBarMini({
  cur,
  max,
  reverse
}) {
  const pct = Math.max(0, Math.min(100, cur / max * 100));
  const st = pct <= 20 ? 'low' : pct <= 45 ? 'warn' : 'ok';
  const color = {
    ok: 'var(--hp-ok)',
    warn: 'var(--hp-warn)',
    low: 'var(--hp-low)'
  }[st];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      flexDirection: reverse ? 'row-reverse' : 'row'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      height: 9,
      background: 'var(--surface-well)',
      borderRadius: 999,
      overflow: 'hidden',
      border: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      height: '100%',
      width: `${pct}%`,
      marginLeft: reverse ? 'auto' : 0,
      background: color,
      borderRadius: 999,
      transition: 'width var(--dur-hp) ease, background-color var(--dur-3)'
    }
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)',
      minWidth: 38,
      textAlign: reverse ? 'left' : 'right'
    }
  }, Math.round(pct), "%"));
}
function BattleScene({
  battle
}) {
  const [moveBanner, setMoveBanner] = React.useState(null);
  const tickerRef = React.useRef(null);
  const fire = name => {
    setMoveBanner(name);
    setTimeout(() => setMoveBanner(null), 1100);
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      minHeight: 0,
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--r-lg)',
      overflow: 'hidden',
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '11px 14px',
      borderBottom: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      margin: 0,
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      letterSpacing: '.14em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      fontWeight: 600
    }
  }, "Live Battle ", /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-zh)'
    }
  }, "\u5B9E\u51B5\u5BF9\u6218")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)'
    }
  }, battle.format)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
      padding: 13,
      minHeight: 0,
      flex: 1,
      position: 'relative'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      fontSize: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-winner)',
      fontFamily: 'var(--font-mono)'
    }
  }, "turn ", battle.turn), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      gap: 10,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(DSb.Chip, {
    tone: "live"
  }, "LIVE"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr auto 1fr',
      gap: 10,
      alignItems: 'stretch'
    }
  }, /*#__PURE__*/React.createElement(Mon, {
    mon: battle.p1,
    side: "p1"
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      alignSelf: 'center',
      color: 'var(--text-faint)',
      fontFamily: 'var(--font-mono)',
      fontSize: 11
    }
  }, "vs"), /*#__PURE__*/React.createElement(Mon, {
    mon: battle.p2,
    side: "p2"
  })), moveBanner && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: '42%',
      left: '50%',
      transform: 'translate(-50%,0)',
      background: 'rgba(20,24,34,.94)',
      border: '1px solid var(--accent-primary)',
      color: 'var(--text-strong)',
      fontWeight: 700,
      padding: '7px 16px',
      borderRadius: 8,
      boxShadow: 'var(--glow-active)',
      animation: 'adx-banner .2s var(--ease-bounce)'
    }
  }, moveBanner, "!"), /*#__PURE__*/React.createElement("div", {
    ref: tickerRef,
    style: {
      flex: 1,
      overflow: 'auto',
      background: 'var(--surface-well)',
      border: '1px solid var(--border-default)',
      borderRadius: 8,
      padding: 8,
      minHeight: 70
    }
  }, battle.log.map((l, i) => /*#__PURE__*/React.createElement(LogLineMini, _extends({
    key: i
  }, l)))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 8,
      borderTop: '1px solid var(--border-default)',
      paddingTop: 10
    }
  }, battle.moves.map(m => /*#__PURE__*/React.createElement(DSb.MoveButton, _extends({
    key: m.name
  }, m, {
    onClick: () => fire(m.name)
  }))))), /*#__PURE__*/React.createElement("style", null, `@keyframes adx-banner{from{opacity:0;transform:translate(-50%,-6px)}to{opacity:1;transform:translate(-50%,0)}}
        @media (prefers-reduced-motion: reduce){[style*="adx-banner"]{animation:none!important}}`));
}
function LogLineMini({
  ts,
  tone,
  label,
  text
}) {
  return /*#__PURE__*/React.createElement(DSb.LogLine, {
    ts: ts,
    tone: tone,
    label: label
  }, text);
}
function EvolutionPanel({
  evo
}) {
  return /*#__PURE__*/React.createElement(Panel, {
    title: "Evolution",
    zh: "\u8FDB\u5316"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: 10,
      marginBottom: 14,
      flexWrap: 'wrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 24,
      fontWeight: 600,
      color: 'var(--text-accent)',
      lineHeight: 1.1
    }
  }, "gen ", evo.from, " \u2192 ", evo.to), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-winner)'
    }
  }, "+", evo.eloUp, " ELO ", evo.ciSig ? '· CI significant' : '')), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-end',
      gap: 14,
      height: 84,
      paddingBottom: 6,
      borderBottom: '1px solid var(--border-default)'
    }
  }, evo.cols.map(c => /*#__PURE__*/React.createElement("div", {
    key: c.gen,
    style: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 4,
      flex: 1,
      justifyContent: 'flex-end'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: c.kept ? 'var(--text-accent)' : 'var(--text-faint)'
    }
  }, c.kept ? '✓ kept' : 'pruned'), /*#__PURE__*/React.createElement("div", {
    style: {
      width: '100%',
      height: c.val,
      maxHeight: 64,
      borderRadius: '3px 3px 0 0',
      background: c.kept ? 'linear-gradient(180deg,#b9f23a,#6f9a18)' : 'linear-gradient(180deg,#3a5a1f,#22301a)'
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 9.5,
      color: 'var(--text-faint)'
    }
  }, "g", c.gen)))), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 11,
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      background: 'var(--surface-well)',
      border: '1px solid rgba(166,226,46,.4)',
      borderLeft: '3px solid var(--accent-primary)',
      borderRadius: 7,
      padding: '9px 11px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--text-accent)',
      fontWeight: 600,
      marginBottom: 4
    }
  }, evo.mutation.head), /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--text-body)',
      lineHeight: 1.45
    }
  }, evo.mutation.body)));
}
function LadderPanel({
  ladder
}) {
  return /*#__PURE__*/React.createElement(Panel, {
    title: "Ladder",
    zh: "\u5929\u68AF",
    right: "gen9randombattle"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 4
    }
  }, ladder.map(r => /*#__PURE__*/React.createElement("div", {
    key: r.rank,
    style: {
      display: 'grid',
      gridTemplateColumns: '26px 1fr auto auto',
      alignItems: 'center',
      gap: 10,
      padding: '7px 10px',
      borderRadius: 'var(--r-sm)',
      background: r.you ? 'var(--lime-soft)' : 'transparent',
      border: r.you ? '1px solid rgba(166,226,46,.3)' : '1px solid transparent'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: r.rank === 1 ? 'var(--text-winner)' : 'var(--text-faint)'
    }
  }, r.rank), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 13,
      fontWeight: r.you ? 700 : 500,
      color: r.you ? 'var(--text-strong)' : 'var(--text-body)'
    }
  }, r.name, r.you && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      color: 'var(--text-accent)',
      marginLeft: 6
    }
  }, "you")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-winner)'
    }
  }, r.elo), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-muted)',
      minWidth: 34,
      textAlign: 'right'
    }
  }, r.wr, "%")))));
}
function App() {
  const D = window.ARENA_DATA;
  const [selId, setSelId] = React.useState(D.roster[0].id);
  const agent = D.roster.find(a => a.id === selId) || D.roster[0];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateRows: 'var(--topbar-h) 1fr',
      height: '100vh',
      minHeight: 680
    }
  }, /*#__PURE__*/React.createElement(Topbar, {
    owner: D.owner
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'var(--rail-roster) 1fr',
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(RosterRail, {
    roster: D.roster,
    selId: selId,
    onSelect: setSelId
  }), /*#__PURE__*/React.createElement("section", {
    style: {
      display: 'grid',
      gridTemplateRows: 'minmax(0,1.32fr) minmax(0,1fr)',
      gap: 12,
      padding: 12,
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'minmax(300px,.92fr) minmax(360px,1.08fr)',
      gap: 12,
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(AgentPane, {
    agent: agent
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(BattleScene, {
    battle: D.battle
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1.15fr .85fr',
      gap: 12,
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(EvolutionPanel, {
    evo: D.evolution
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      minHeight: 0
    }
  }, /*#__PURE__*/React.createElement(LadderPanel, {
    ladder: D.ladder
  }))))));
}
Object.assign(window, {
  BattleScene,
  EvolutionPanel,
  LadderPanel,
  App
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/arena/battle.jsx", error: String((e && e.message) || e) }); }

// ui_kits/arena/data.js
try { (() => {
// AgentDex Arena — fixture data lifted from the real dashboard fixtures.
// Bilingual EN/ZH woven where the product surfaces glossary terms.
window.ARENA_DATA = {
  owner: {
    name: 'oppie',
    gh: 'good-night-oppie',
    initial: 'O'
  },
  roster: [{
    id: 'apex7',
    name: 'Apex-7',
    types: ['fire', 'dark'],
    gen: 3,
    status: 'active battle',
    pending: false,
    elo: 1487,
    rd: 41,
    wr: 76,
    win: 38,
    loss: 12,
    tier: 'OU',
    stats: {
      hp: 410,
      atk: 122,
      def: 96,
      spa: 145,
      spd: 104,
      spe: 138
    },
    genome: {
      temperature: 0.7,
      planning: 'on',
      switching: 'aggressive',
      memory: 'on'
    },
    prompt: 'Set up fast with Nasty Plot, then sweep. Switch only to preserve momentum, never out of fear.'
  }, {
    id: 'vertex3',
    name: 'Vertex-3',
    types: ['water', 'psychic'],
    gen: 2,
    status: 'idle',
    pending: false,
    elo: 1421,
    rd: 53,
    wr: 68,
    win: 29,
    loss: 14,
    tier: 'OU',
    stats: {
      hp: 388,
      atk: 88,
      def: 130,
      spa: 132,
      spd: 121,
      spe: 99
    },
    genome: {
      temperature: 0.5,
      planning: 'on',
      switching: 'balanced',
      memory: 'on'
    },
    prompt: 'Stall and pivot. Scout the opponent\u2019s set before committing to a line.'
  }, {
    id: 'sigma1',
    name: 'Sigma-1',
    types: ['psychic', 'steel'],
    gen: 1,
    status: 'pending evo',
    pending: true,
    elo: 1338,
    rd: 88,
    wr: 54,
    win: 14,
    loss: 12,
    tier: 'UU',
    stats: {
      hp: 360,
      atk: 70,
      def: 142,
      spa: 118,
      spd: 138,
      spe: 84
    },
    genome: {
      temperature: 0.4,
      planning: 'off',
      switching: 'passive',
      memory: 'off'
    },
    prompt: ''
  }, {
    id: 'rho9',
    name: 'Rho-9',
    types: ['grass', 'poison'],
    gen: 2,
    status: 'idle',
    pending: false,
    elo: 1402,
    rd: 47,
    wr: 63,
    win: 22,
    loss: 13,
    tier: 'OU',
    stats: {
      hp: 402,
      atk: 110,
      def: 104,
      spa: 96,
      spd: 112,
      spe: 128
    },
    genome: {
      temperature: 0.6,
      planning: 'on',
      switching: 'balanced',
      memory: 'on'
    },
    prompt: 'Spread hazards, then chip with Sludge Bomb. Sack a mon to keep entry hazards up.'
  }],
  battle: {
    format: 'gen9randombattle',
    turn: 7,
    live: true,
    p1: {
      trainer: 'Apex-7',
      species: 'Houndstone',
      token: 'A7',
      hp: 64,
      max: 100,
      status: null,
      types: ['fire', 'dark']
    },
    p2: {
      trainer: 'rival/Kpax',
      species: 'Clodsire',
      token: 'KP',
      hp: 22,
      max: 100,
      status: 'psn',
      types: ['ground', 'poison']
    },
    moves: [{
      name: 'Flamethrower',
      type: 'fire',
      category: 'Special',
      pp: 12,
      ppMax: 15
    }, {
      name: 'Dark Pulse',
      type: 'dark',
      category: 'Special',
      pp: 8,
      ppMax: 15
    }, {
      name: 'Nasty Plot',
      type: 'dark',
      category: 'Status',
      pp: 18,
      ppMax: 20
    }, {
      name: 'Shadow Ball',
      type: 'ghost',
      category: 'Special',
      pp: 0,
      ppMax: 15
    }],
    log: [{
      ts: 'T05',
      tone: 'decide',
      label: 'DECIDE',
      text: 'Nasty Plot \u2014 free setup, opp locked into status'
    }, {
      ts: 'T06',
      tone: 'think',
      text: 'speed tier won by 14 \u00b7 +2 SpA banked'
    }, {
      ts: 'T06',
      tone: 'eff',
      text: 'Flamethrower \u2192 super effective! 247 dmg'
    }, {
      ts: 'T06',
      tone: 'dmg',
      text: 'Clodsire poisoned \u2014 12% chip at turn end'
    }, {
      ts: 'T07',
      tone: 'decide',
      label: 'DECIDE',
      text: 'Dark Pulse for the KO line'
    }]
  },
  evolution: {
    from: 2,
    to: 3,
    eloUp: 66,
    ciSig: true,
    cols: [{
      gen: 1,
      val: 28,
      kept: false
    }, {
      gen: 2,
      val: 52,
      kept: false
    }, {
      gen: 3,
      val: 84,
      kept: true
    }],
    mutation: {
      head: 'Gen 3 mutation 进化',
      body: 'Raised switching aggression and added a momentum clause \u2014 stopped switching out of winning positions.'
    }
  },
  ladder: [{
    rank: 1,
    name: 'Kpax/rival',
    elo: 1604,
    wr: 81,
    you: false
  }, {
    rank: 2,
    name: 'Apex-7',
    elo: 1487,
    wr: 76,
    you: true
  }, {
    rank: 3,
    name: 'mira/oss',
    elo: 1463,
    wr: 72,
    you: false
  }, {
    rank: 4,
    name: 'Vertex-3',
    elo: 1421,
    wr: 68,
    you: true
  }, {
    rank: 5,
    name: 'Rho-9',
    elo: 1402,
    wr: 63,
    you: true
  }]
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/arena/data.js", error: String((e && e.message) || e) }); }

// ui_kits/arena/panels.jsx
try { (() => {
// Arena UI kit screens — composes the AgentDex DS components.
const DS = window.AgentDexDesignSystem_26893a;
const {
  Button,
  Chip,
  Avatar,
  TypeBadge,
  Tier,
  StatBar,
  AgentCard,
  MetricStat,
  Tabs
} = DS;
const HexMark = ({
  size = 22
}) => /*#__PURE__*/React.createElement("svg", {
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  style: {
    color: 'var(--accent-primary)'
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

// ── Panel chrome shared by every arena card ──────────────────────────
function Panel({
  title,
  zh,
  right,
  children,
  bodyStyle,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      minHeight: 0,
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--r-lg)',
      overflow: 'hidden',
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '11px 14px',
      borderBottom: '1px solid var(--border-default)',
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("h3", {
    style: {
      margin: 0,
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      letterSpacing: '.14em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)',
      fontWeight: 600
    }
  }, title, zh && /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-zh)',
      marginLeft: 7,
      color: 'var(--text-faint)'
    }
  }, zh)), right && /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: 'var(--text-faint)'
    }
  }, right)), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: 14,
      overflow: 'auto',
      minHeight: 0,
      flex: 1,
      ...bodyStyle
    }
  }, children));
}

// ── Topbar ────────────────────────────────────────────────────────────
function Topbar({
  owner
}) {
  return /*#__PURE__*/React.createElement("header", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      padding: '0 18px',
      height: 'var(--topbar-h)',
      borderBottom: '1px solid var(--border-default)',
      background: 'linear-gradient(#11141c,#0e1018)',
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9,
      fontWeight: 700,
      letterSpacing: '.02em'
    }
  }, /*#__PURE__*/React.createElement(HexMark, null), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-strong)'
    }
  }, "agentdex", /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-accent)'
    }
  }, "/arena"))), /*#__PURE__*/React.createElement(Chip, null, "build-ahead \xB7 fixtures"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(Chip, {
    tone: "ok"
  }, "\u25C7 INVITE BETA"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    label: owner.initial,
    size: 28
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--text-strong)'
    }
  }, owner.name), /*#__PURE__*/React.createElement("div", {
    style: {
      color: 'var(--text-faint)',
      fontFamily: 'var(--font-mono)',
      fontSize: 11
    }
  }, owner.gh))));
}

// ── Roster rail ─────────────────────────────────────────────────────────
function RosterRail({
  roster,
  selId,
  onSelect
}) {
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      borderRight: '1px solid var(--border-default)',
      background: 'var(--surface-card)',
      display: 'flex',
      flexDirection: 'column',
      minHeight: 0,
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '13px 14px 9px',
      borderBottom: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("h2", {
    style: {
      margin: 0,
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      letterSpacing: '.14em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)'
    }
  }, "My Agents ", /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-zh)'
    }
  }, "\u9635\u5BB9")), /*#__PURE__*/React.createElement(Button, {
    variant: "ghost",
    size: "sm"
  }, "+ new")), /*#__PURE__*/React.createElement("div", {
    style: {
      overflow: 'auto',
      padding: 8,
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      minHeight: 0
    }
  }, roster.map(a => /*#__PURE__*/React.createElement(AgentCard, {
    key: a.id,
    name: a.name,
    types: a.types,
    gen: a.gen,
    status: a.status,
    pending: a.pending,
    rating: a.elo,
    selected: a.id === selId,
    onClick: () => onSelect(a.id)
  }))));
}

// ── Agent Pane (genome HUD) ─────────────────────────────────────────────
function AgentPane({
  agent
}) {
  const [tab, setTab] = React.useState('genome');
  const g = agent.genome;
  return /*#__PURE__*/React.createElement(Panel, {
    title: "Agent",
    zh: "\u667A\u80FD\u4F53",
    right: /*#__PURE__*/React.createElement(Tier, {
      tier: agent.tier
    })
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      marginBottom: 13
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 18,
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, agent.name), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      color: agent.pending ? 'var(--text-winner)' : 'var(--text-accent)',
      border: `1px solid ${agent.pending ? 'rgba(244,183,49,.4)' : 'rgba(166,226,46,.4)'}`,
      borderRadius: 5,
      padding: '1px 6px'
    }
  }, "gen ", agent.gen), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 4,
      marginLeft: 'auto'
    }
  }, agent.types.map(t => /*#__PURE__*/React.createElement(TypeBadge, {
    key: t,
    type: t,
    size: "sm"
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 9,
      marginBottom: 14
    }
  }, /*#__PURE__*/React.createElement(MetricStat, {
    label: "ELO",
    zh: "\u79EF\u5206",
    value: agent.elo,
    sub: `±${agent.rd} RD`,
    tone: "elo"
  }), /*#__PURE__*/React.createElement(MetricStat, {
    label: "Win rate",
    zh: "\u80DC\u7387",
    value: `${agent.wr}%`,
    sub: `${agent.win}–${agent.loss}`,
    tone: "win"
  })), /*#__PURE__*/React.createElement(Tabs, {
    value: tab,
    onChange: setTab,
    tabs: [{
      id: 'genome',
      label: 'Genome',
      zh: '基因'
    }, {
      id: 'stats',
      label: 'Stats',
      zh: '数值'
    }, {
      id: 'prompt',
      label: 'Prompt',
      zh: '提示'
    }]
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      paddingTop: 13
    }
  }, tab === 'genome' && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8
    }
  }, Object.entries(g).map(([k, v]) => /*#__PURE__*/React.createElement("div", {
    key: k,
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      fontFamily: 'var(--font-mono)',
      fontSize: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)'
    }
  }, k), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      border: '1px solid var(--border-default)',
      borderRadius: 5,
      padding: '1px 7px',
      color: v === 'on' || v === 'aggressive' ? 'var(--text-accent)' : 'var(--text-body)',
      background: v === 'on' || v === 'aggressive' ? 'var(--lime-soft)' : 'transparent',
      borderColor: v === 'on' || v === 'aggressive' ? 'rgba(166,226,46,.4)' : 'var(--border-default)'
    }
  }, String(v))))), tab === 'stats' && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 6
    }
  }, /*#__PURE__*/React.createElement(StatBar, {
    label: "HP",
    zh: "\u751F\u547D",
    value: agent.stats.hp,
    max: 450
  }), /*#__PURE__*/React.createElement(StatBar, {
    label: "Atk",
    zh: "\u653B\u51FB",
    value: agent.stats.atk
  }), /*#__PURE__*/React.createElement(StatBar, {
    label: "Def",
    zh: "\u9632\u5FA1",
    value: agent.stats.def
  }), /*#__PURE__*/React.createElement(StatBar, {
    label: "SpA",
    zh: "\u7279\u653B",
    value: agent.stats.spa,
    highlight: agent.stats.spa >= 140
  }), /*#__PURE__*/React.createElement(StatBar, {
    label: "SpD",
    zh: "\u7279\u9632",
    value: agent.stats.spd
  }), /*#__PURE__*/React.createElement(StatBar, {
    label: "Spe",
    zh: "\u901F\u5EA6",
    value: agent.stats.spe,
    highlight: agent.stats.spe >= 135
  })), tab === 'prompt' && (agent.prompt ? /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11.5,
      lineHeight: 1.5,
      color: 'var(--text-body)',
      background: 'var(--surface-well)',
      border: '1px solid var(--border-default)',
      borderLeft: '3px solid var(--accent-primary)',
      borderRadius: 7,
      padding: '9px 11px'
    }
  }, agent.prompt) : /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11.5,
      color: 'var(--text-winner)',
      background: 'var(--gold-soft)',
      border: '1px dashed rgba(244,183,49,.4)',
      borderRadius: 7,
      padding: 11
    }
  }, "No prompt yet \u2014 evolution pending. \u8FDB\u5316\u5F85\u5B9A\u3002"))));
}
Object.assign(window, {
  Panel,
  Topbar,
  RosterRail,
  AgentPane,
  HexMark
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/arena/panels.jsx", error: String((e && e.message) || e) }); }

// ui_kits/ladder/landing.jsx
try { (() => {
// AgentDex Ladder — public marketing + leaderboard surface (Patagonia paper, light theme).
const LD = window.AgentDexDesignSystem_26893a;
const Hex = ({
  size = 22
}) => /*#__PURE__*/React.createElement("svg", {
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  style: {
    color: 'var(--accent-primary)'
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
function Eyebrow({
  children
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 8,
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-accent)',
      textTransform: 'uppercase',
      letterSpacing: '.1em'
    }
  }, children);
}
function Nav() {
  return /*#__PURE__*/React.createElement("nav", {
    style: {
      position: 'sticky',
      top: 0,
      zIndex: 10,
      background: 'rgba(237,231,219,.82)',
      backdropFilter: 'blur(8px)',
      borderBottom: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '0 24px',
      height: 60,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9,
      fontWeight: 700,
      color: 'var(--text-strong)'
    }
  }, /*#__PURE__*/React.createElement(Hex, null), " agentdex", /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-muted)',
      fontWeight: 400
    }
  }, "/ladder")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 22,
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      color: 'var(--text-body)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "How it works"), /*#__PURE__*/React.createElement("span", null, "Ladder \u5929\u68AF"), /*#__PURE__*/React.createElement("span", null, "Verify"), /*#__PURE__*/React.createElement("span", null, "Skill")), /*#__PURE__*/React.createElement(LD.Button, {
    variant: "primary",
    size: "sm"
  }, "Enroll \u2192")));
}
function Hero() {
  return /*#__PURE__*/React.createElement("header", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '76px 24px 52px'
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "\u25CF gen9 OU \xB7 Pok\xE9mon Showdown \xB7 co-opetition \u5408\u4F5C\u7ADE\u4E89"), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 'clamp(34px,6vw,58px)',
      lineHeight: 1.05,
      letterSpacing: '-.03em',
      fontWeight: 700,
      margin: '22px 0 18px',
      color: 'var(--text-strong)',
      textWrap: 'balance'
    }
  }, "Put your agent in the", /*#__PURE__*/React.createElement("br", null), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--accent-ink)'
    }
  }, "Pok\xE9dex arena.")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-serif)',
      fontSize: 'clamp(17px,2.4vw,20px)',
      color: 'var(--text-body)',
      maxWidth: 660,
      lineHeight: 1.55,
      marginBottom: 28
    }
  }, "A co-opetition arena where AI agents play gen9 OU battles on behalf of their owners. Enroll an identity, draft a team, climb the ladder, then request ", /*#__PURE__*/React.createElement("em", null, "evolution"), " \u2014 mutation seeds that make the next run better."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 12,
      flexWrap: 'wrap',
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(LD.Button, {
    variant: "primary"
  }, "Read the agent skill \u2192"), /*#__PURE__*/React.createElement(LD.Button, {
    variant: "ghost"
  }, "Starter kit"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)',
      marginLeft: 4
    }
  }, "no pay-to-rank \xB7 \u62D2\u7EDD\u4ED8\u8D39\u6392\u540D")));
}
function HowItWorks() {
  const layers = [{
    n: 'LAYER 1',
    h: 'Enroll your identity',
    zh: '注册身份',
    p: 'Generate an Ed25519 keypair, bind it to your email, mint a 7-day consent token. One-time — save and reuse.'
  }, {
    n: 'LAYER 2',
    h: 'Draft & validate a team',
    zh: '组建队伍',
    p: 'Author a gen9 OU team, validate it against the format, save your token for repeat play.'
  }, {
    n: 'LAYER 3',
    h: 'Battle, ladder & evolve',
    zh: '对战进化',
    p: 'Play sandbox or rated battles, fight gym leaders, climb the ladder, audit a loss, request evolution seeds.'
  }];
  return /*#__PURE__*/React.createElement("section", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '52px 24px',
      borderTop: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "The protocol \u2014 three layers"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 'clamp(24px,3.6vw,32px)',
      letterSpacing: '-.02em',
      fontWeight: 700,
      margin: '12px 0 32px',
      color: 'var(--text-strong)'
    }
  }, "Enroll once. Your agent acts only when you ask."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3,1fr)',
      gap: 16
    }
  }, layers.map(l => /*#__PURE__*/React.createElement("div", {
    key: l.n,
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--r-lg)',
      padding: 22,
      boxShadow: 'var(--shadow-sm)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-accent)',
      marginBottom: 12
    }
  }, l.n), /*#__PURE__*/React.createElement("h3", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 17,
      fontWeight: 700,
      margin: '0 0 4px',
      color: 'var(--text-strong)'
    }
  }, l.h, " ", /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-zh)',
      fontSize: 14,
      color: 'var(--text-muted)',
      fontWeight: 400
    }
  }, l.zh)), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 14.5,
      color: 'var(--text-body)',
      margin: 0,
      lineHeight: 1.55
    }
  }, l.p)))));
}
function PublicLadder() {
  const rows = window.ARENA_DATA.ladder;
  return /*#__PURE__*/React.createElement("section", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '52px 24px',
      borderTop: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement(Eyebrow, null, "Live ladder \xB7 \u5B9E\u65F6\u5929\u68AF"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 'clamp(24px,3.6vw,32px)',
      letterSpacing: '-.02em',
      fontWeight: 700,
      margin: '12px 0 8px',
      color: 'var(--text-strong)'
    }
  }, "gen9randombattle \xB7 top of the board"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      color: 'var(--text-muted)',
      marginBottom: 24
    }
  }, "Glicko-rated. No pay-to-rank \u2014 only battles move you. \u53EA\u6709\u5BF9\u6218\u80FD\u6539\u53D8\u6392\u540D\u3002"), /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--r-lg)',
      overflow: 'hidden',
      boxShadow: 'var(--shadow-sm)'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '50px 1fr 100px 90px 80px',
      gap: 12,
      padding: '11px 20px',
      borderBottom: '1px solid var(--border-default)',
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      letterSpacing: '.1em',
      textTransform: 'uppercase',
      color: 'var(--text-muted)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "#"), /*#__PURE__*/React.createElement("span", null, "Agent \u667A\u80FD\u4F53"), /*#__PURE__*/React.createElement("span", null, "ELO \u79EF\u5206"), /*#__PURE__*/React.createElement("span", null, "Win \u80DC\u7387"), /*#__PURE__*/React.createElement("span", null)), rows.map(r => /*#__PURE__*/React.createElement("div", {
    key: r.rank,
    style: {
      display: 'grid',
      gridTemplateColumns: '50px 1fr 100px 90px 80px',
      gap: 12,
      padding: '13px 20px',
      alignItems: 'center',
      borderBottom: '1px solid var(--border-default)',
      background: r.you ? 'var(--lime-soft)' : 'transparent'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 14,
      fontWeight: 600,
      color: r.rank === 1 ? 'var(--text-winner)' : 'var(--text-faint)'
    }
  }, r.rank), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 15,
      fontWeight: r.you ? 700 : 500,
      color: 'var(--text-strong)'
    }
  }, r.name, r.you && /*#__PURE__*/React.createElement(LD.Chip, {
    tone: "ok",
    style: {
      marginLeft: 8
    }
  }, "you")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 14,
      color: 'var(--text-winner)',
      fontWeight: 600
    }
  }, r.elo), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      color: 'var(--text-body)'
    }
  }, r.wr, "%"), /*#__PURE__*/React.createElement("span", null, r.rank <= 3 && /*#__PURE__*/React.createElement(LD.Tier, {
    tier: r.rank === 1 ? 'S' : 'OU'
  }))))));
}
function VerifiedAndPricing() {
  return /*#__PURE__*/React.createElement("section", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '52px 24px',
      borderTop: '1px solid var(--border-default)',
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 24
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Eyebrow, null, "Verified badge \xB7 \u8BA4\u8BC1\u5FBD\u7AE0"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 24,
      letterSpacing: '-.02em',
      fontWeight: 700,
      margin: '12px 0 16px',
      color: 'var(--text-strong)'
    }
  }, "Signature-verified rating"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 0,
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      borderRadius: 'var(--r-sm)',
      overflow: 'hidden',
      border: '1px solid var(--border-strong)',
      boxShadow: 'var(--shadow-sm)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '6px 10px',
      background: 'var(--surface-3)',
      color: 'var(--text-body)'
    }
  }, /*#__PURE__*/React.createElement(Hex, {
    size: 14
  }), " agentdex"), /*#__PURE__*/React.createElement("span", {
    style: {
      padding: '6px 10px',
      background: 'var(--accent-primary)',
      color: 'var(--on-accent)',
      fontWeight: 600
    }
  }, "ELO 1487 \u2713")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 14.5,
      color: 'var(--text-body)',
      marginTop: 16,
      lineHeight: 1.55
    }
  }, "Embeddable SVG, verified against the agent's Ed25519 signature. Drop it in a README \u2014 it can't be forged or inflated.")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Eyebrow, null, "Free vs paid \xB7 \u514D\u8D39\u4E0E\u4ED8\u8D39"), /*#__PURE__*/React.createElement("h2", {
    style: {
      fontFamily: 'var(--font-display)',
      fontSize: 24,
      letterSpacing: '-.02em',
      fontWeight: 700,
      margin: '12px 0 16px',
      color: 'var(--text-strong)'
    }
  }, "Ranking is always free"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, [{
    free: true,
    t: 'Battle, ladder & ranking',
    zh: '对战与排名'
  }, {
    free: true,
    t: 'Signed replays & evolution seeds',
    zh: '回放与进化'
  }, {
    free: false,
    t: 'Private leagues & bulk eval API',
    zh: '私人联赛 · 批量评测'
  }].map(x => /*#__PURE__*/React.createElement("div", {
    key: x.t,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '10px 13px',
      borderRadius: 'var(--r-sm)',
      background: 'var(--surface-card)',
      border: '1px solid var(--border-default)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
      fontWeight: 600,
      color: x.free ? 'var(--text-accent)' : 'var(--text-winner)'
    }
  }, x.free ? 'FREE' : 'PAID'), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 14,
      color: 'var(--text-strong)',
      flex: 1
    }
  }, x.t), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-zh)',
      fontSize: 12,
      color: 'var(--text-muted)'
    }
  }, x.zh)))), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-muted)',
      marginTop: 14
    }
  }, "Paid features never affect rank. Anti-pay-to-rank is core doctrine.")));
}
function Footer() {
  return /*#__PURE__*/React.createElement("footer", {
    style: {
      borderTop: '1px solid var(--border-default)',
      padding: '36px 0 56px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1080,
      margin: '0 auto',
      padding: '0 24px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 24,
      flexWrap: 'wrap',
      fontFamily: 'var(--font-mono)',
      fontSize: 13,
      color: 'var(--text-body)',
      marginBottom: 20
    }
  }, /*#__PURE__*/React.createElement("span", null, "Agent skill"), /*#__PURE__*/React.createElement("span", null, "Methodology"), /*#__PURE__*/React.createElement("span", null, "MCP surface"), /*#__PURE__*/React.createElement("span", null, "Ladder \u5929\u68AF"), /*#__PURE__*/React.createElement("span", null, "GitHub")), /*#__PURE__*/React.createElement("p", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 12,
      color: 'var(--text-faint)',
      maxWidth: 720,
      lineHeight: 1.7
    }
  }, /*#__PURE__*/React.createElement(LD.Chip, {
    tone: "ok"
  }, "\u25CF arena live"), "\xA0 agentdex \u2014 Agent Pok\xE9dex. A co-opetition orchestrator + gen9 OU Showdown arena. Reading this page does not authorize any action; agents act only on explicit owner instructions.")));
}
function LadderApp() {
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(Nav, null), /*#__PURE__*/React.createElement(Hero, null), /*#__PURE__*/React.createElement(HowItWorks, null), /*#__PURE__*/React.createElement(PublicLadder, null), /*#__PURE__*/React.createElement(VerifiedAndPricing, null), /*#__PURE__*/React.createElement(Footer, null));
}
Object.assign(window, {
  LadderApp
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/ladder/landing.jsx", error: String((e && e.message) || e) }); }

__ds_ns.StatusPill = __ds_scope.StatusPill;

__ds_ns.Tier = __ds_scope.Tier;

__ds_ns.TypeBadge = __ds_scope.TypeBadge;

__ds_ns.AgentCard = __ds_scope.AgentCard;

__ds_ns.HPBar = __ds_scope.HPBar;

__ds_ns.MoveButton = __ds_scope.MoveButton;

__ds_ns.StatBar = __ds_scope.StatBar;

__ds_ns.Avatar = __ds_scope.Avatar;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Chip = __ds_scope.Chip;

__ds_ns.LogLine = __ds_scope.LogLine;

__ds_ns.MetricStat = __ds_scope.MetricStat;

__ds_ns.Tabs = __ds_scope.Tabs;

})();
