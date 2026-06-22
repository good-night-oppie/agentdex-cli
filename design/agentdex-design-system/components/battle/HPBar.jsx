import React from 'react';

/**
 * HP bar — the load-bearing battle widget. Trichrome fill (green→amber→red)
 * driven by the remaining fraction, with a snappy width-drain transition.
 * Fainted collapses to a dim empty track. Optional EN label + 中文 gloss.
 */
export function HPBar({
  name,
  zh,
  cur,
  max = 100,
  showValues = true,
  state, // optional override: 'ok' | 'warn' | 'low' | 'fainted'
  height = 10,
  style,
  ...rest
}) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (cur / max) * 100)) : 0;
  const auto =
    pct <= 0 ? 'fainted' : pct <= 20 ? 'low' : pct <= 45 ? 'warn' : 'ok';
  const st = state || auto;
  const fillColor = {
    ok: 'var(--hp-ok)',
    warn: 'var(--hp-warn)',
    low: 'var(--hp-low)',
    fainted: 'var(--dim)',
  }[st];
  const valColor = {
    ok: 'var(--hp-ok)',
    warn: 'var(--hp-warn)',
    low: 'var(--hp-low)',
    fainted: 'var(--mut)',
  }[st];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, ...style }} {...rest}>
      {(name != null || showValues) && (
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
          {name != null && (
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                textTransform: 'uppercase',
                letterSpacing: 'var(--ls-label)',
                color: 'var(--text-muted)',
              }}
            >
              {name}
              {zh && <span style={{ fontFamily: 'var(--font-zh)', marginLeft: 6, color: 'var(--text-faint)' }}>{zh}</span>}
            </span>
          )}
          {showValues && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: valColor }}>
              {cur} / {max}
            </span>
          )}
        </div>
      )}
      <div
        style={{
          height,
          borderRadius: 'var(--r-pill)',
          background: 'var(--surface-well)',
          border: '1px solid var(--border-default)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${pct}%`,
            borderRadius: 'var(--r-pill)',
            background: fillColor,
            transition: 'width var(--dur-hp) var(--ease-snap), background-color var(--dur-2)',
            animation: st === 'low' ? 'adx-hp-low 1.2s ease-in-out infinite' : 'none',
          }}
        />
      </div>
      <style>{`@keyframes adx-hp-low{0%,100%{opacity:1}50%{opacity:.55}}
        @media (prefers-reduced-motion: reduce){[style*="adx-hp-low"]{animation:none!important}}`}</style>
    </div>
  );
}
