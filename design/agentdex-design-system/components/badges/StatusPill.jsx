import React from 'react';

// Pokémon status conditions + battle-state pills.
const STATUS = {
  // condition pills (abbreviated, Pokerogue convention)
  PAR: { label: 'PAR', color: '#1A1A12', bg: '#E0B020' },
  BRN: { label: 'BRN', color: '#fff', bg: '#E06018' },
  PSN: { label: 'PSN', color: '#fff', bg: '#A040A0' },
  TOX: { label: 'TOX', color: '#fff', bg: '#883888' },
  SLP: { label: 'SLP', color: '#fff', bg: '#5D6575' },
  FRZ: { label: 'FRZ', color: '#1A1A12', bg: '#7FD4FF' },
  // health states
  healthy: { label: 'HEALTHY', color: 'var(--hp-ok)', border: 'rgba(95,211,90,.35)', bg: 'rgba(95,211,90,.10)' },
  fainted: { label: 'FAINTED', color: 'var(--hp-low)', border: 'rgba(239,74,74,.4)', bg: 'rgba(239,74,74,.10)' },
};

/**
 * Status pill — Pokémon status condition (solid) or health state
 * (outlined). Pass a known key, or override label/color.
 */
export function StatusPill({ status = 'PAR', label, style, ...rest }) {
  const s = STATUS[status] || STATUS.PAR;
  const outlined = s.border != null;
  return (
    <span
      style={{
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
        ...style,
      }}
      {...rest}
    >
      {label || s.label}
    </span>
  );
}
