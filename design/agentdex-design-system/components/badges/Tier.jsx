import React from 'react';

/**
 * Genome tier chip (Showdown OU/UU/NU → agent strength tier).
 * Lime by default; gold for the top S/OU tiers.
 */
export function Tier({ tier = 'OU', tone, style, ...rest }) {
  const t = tone || (['S', 'OU', 'UBER'].includes(String(tier).toUpperCase()) ? 'gold' : 'lime');
  const palette =
    t === 'gold'
      ? { color: 'var(--text-winner)', border: 'rgba(244,183,49,.30)', bg: 'var(--gold-soft)' }
      : { color: 'var(--text-accent)', border: 'rgba(166,226,46,.25)', bg: 'var(--lime-soft)' };
  return (
    <span
      style={{
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
        ...style,
      }}
      {...rest}
    >
      {tier}
    </span>
  );
}
