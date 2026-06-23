import React from 'react';

const STAT_COLORS = {
  hp: 'var(--hp-ok)',
  atk: 'var(--t-fire)',
  def: 'var(--blue)',
  spa: 'var(--lime)',
  spd: 'var(--t-water)',
  spe: 'var(--gold)',
};

/**
 * Dex stat row — label · numeric value · proportional bar. The Showdown-DNA
 * unit for an agent's genome stats. Bar color keys off the stat name, or
 * pass an explicit `color`.
 */
export function StatBar({
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
  const pct = Math.max(2, Math.min(100, (value / max) * 100));
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '48px 34px 1fr',
        alignItems: 'center',
        gap: 8,
        ...style,
      }}
      {...rest}
    >
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          textTransform: 'uppercase',
          letterSpacing: '.04em',
          color: 'var(--text-muted)',
        }}
      >
        {label}
        {zh && <span style={{ fontFamily: 'var(--font-zh)', display: 'block', fontSize: 9, color: 'var(--text-faint)' }}>{zh}</span>}
      </span>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          fontWeight: 600,
          textAlign: 'right',
          color: highlight ? bar : 'var(--text-body)',
        }}
      >
        {value}
      </span>
      <span
        style={{
          height: 6,
          borderRadius: 'var(--r-xs)',
          background: 'var(--border-default)',
          overflow: 'hidden',
        }}
      >
        <span
          style={{
            display: 'block',
            height: '100%',
            width: `${pct}%`,
            borderRadius: 'var(--r-xs)',
            background: bar,
            transition: 'width var(--dur-3) var(--ease-out)',
          }}
        />
      </span>
    </div>
  );
}
