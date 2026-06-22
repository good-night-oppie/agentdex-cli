import React from 'react';

/**
 * Metric stat tile — big mono number with a label and optional delta/sub.
 * Used for ELO, win-rate, turn-efficiency on the genome HUD + ladder.
 */
export function MetricStat({
  label,
  zh,
  value,
  sub,
  delta,
  tone = 'default', // 'default' | 'elo' | 'win' | 'data'
  style,
  ...rest
}) {
  const valColor = {
    default: 'var(--text-strong)',
    elo: 'var(--text-winner)',
    win: 'var(--text-accent)',
    data: 'var(--text-data)',
  }[tone];
  const up = typeof delta === 'number' ? delta >= 0 : null;
  return (
    <div
      style={{
        background: 'var(--surface-well)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--r-md)',
        padding: '9px 11px',
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
        ...style,
      }}
      {...rest}
    >
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text-muted)' }}>
        {label}
        {zh && <span style={{ fontFamily: 'var(--font-zh)', marginLeft: 5, color: 'var(--text-faint)' }}>{zh}</span>}
      </span>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 600, lineHeight: 1.1, color: valColor }}>
          {value}
        </span>
        {sub != null && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-faint)' }}>{sub}</span>
        )}
        {delta != null && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, marginLeft: 'auto', color: up ? 'var(--text-accent)' : 'var(--text-danger)' }}>
            {up ? '▲' : '▼'} {typeof delta === 'number' ? Math.abs(delta) : delta}
          </span>
        )}
      </span>
    </div>
  );
}
