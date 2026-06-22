import React from 'react';

/**
 * Pill chip for topbar status / format / live indicators.
 * `tone="live"` adds the blinking ● dot.
 */
export function Chip({ children, tone = 'default', dot, style, ...rest }) {
  const tones = {
    default: { color: 'var(--mut)', border: 'var(--line)', bg: 'var(--surface)' },
    ok:      { color: 'var(--text-accent)', border: 'rgba(166,226,46,.28)', bg: 'var(--lime-soft)' },
    live:    { color: 'var(--text-danger)', border: 'rgba(255,70,85,.30)', bg: 'var(--live-soft)' },
    gold:    { color: 'var(--text-winner)', border: 'rgba(244,183,49,.30)', bg: 'var(--gold-soft)' },
    data:    { color: 'var(--text-data)', border: 'rgba(74,158,245,.30)', bg: 'var(--blue-soft)' },
  };
  const t = tones[tone] || tones.default;
  const showDot = dot ?? tone === 'live';

  return (
    <span
      style={{
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
        ...style,
      }}
      {...rest}
    >
      {showDot && (
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: t.color,
            animation: tone === 'live' ? 'adx-blink 1.4s ease-in-out infinite' : 'none',
          }}
        />
      )}
      {children}
      <style>{`@keyframes adx-blink{0%,100%{opacity:1}50%{opacity:.25}}
        @media (prefers-reduced-motion: reduce){[style*="adx-blink"]{animation:none!important}}`}</style>
    </span>
  );
}
