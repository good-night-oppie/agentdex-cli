import React from 'react';

const TONES = {
  default: 'var(--text-body)',
  agent: 'var(--text-data)',     // agent name reference
  think: 'var(--text-data)',     // reasoning observation
  decide: 'var(--text-accent)',  // reasoning decision
  dmg: 'var(--rust-ink)',        // damage
  eff: 'var(--text-winner)',     // super-effective / crit
  heal: 'var(--text-accent)',    // heal / restore
  faint: 'var(--text-danger)',   // faint / critical
};

/**
 * One mono log line — timestamp + content — for the battle ticker and the
 * reasoning trace. `tone` colors the body; `label` prefixes a small tag
 * (e.g. "DECIDE"). Compose freely with inline <b>/<span> for rich entries.
 */
export function LogLine({ ts, tone = 'default', label, children, style, ...rest }) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 8,
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        lineHeight: 1.55,
        ...style,
      }}
      {...rest}
    >
      {ts != null && <span style={{ color: 'var(--text-faint)', flexShrink: 0 }}>{ts}</span>}
      <span style={{ color: TONES[tone] || TONES.default, minWidth: 0 }}>
        {label && (
          <span style={{ fontWeight: 600, color: TONES[tone] || TONES.default, marginRight: 6 }}>
            {label}
          </span>
        )}
        {children}
      </span>
    </div>
  );
}
