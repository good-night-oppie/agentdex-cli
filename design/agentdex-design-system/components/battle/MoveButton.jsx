import React from 'react';
import { TypeBadge } from '../badges/TypeBadge.jsx';

/**
 * Move button — the 4-slot battle action. Move name, type badge, category,
 * and PP counter. PP at 0 disables; `selected` lifts the lime ring.
 */
export function MoveButton({
  name,
  type,
  category = 'Special', // 'Physical' | 'Special' | 'Status'
  pp,
  ppMax,
  selected = false,
  onClick,
  style,
  ...rest
}) {
  const out = pp != null && pp <= 0;
  const ppLow = pp != null && ppMax != null && pp > 0 && pp / ppMax <= 0.25;
  return (
    <button
      type="button"
      onClick={out ? undefined : onClick}
      disabled={out}
      style={{
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
        ...style,
      }}
      onMouseDown={(e) => { if (!out) e.currentTarget.style.transform = 'translateY(1px)'; }}
      onMouseUp={(e) => { e.currentTarget.style.transform = ''; }}
      onMouseLeave={(e) => { e.currentTarget.style.transform = ''; }}
      {...rest}
    >
      <span
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--text-strong)',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {name}
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        {type && <TypeBadge type={type} size="sm" />}
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>
          {category}
        </span>
        {pp != null && (
          <span
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: out || ppLow ? 'var(--text-danger)' : 'var(--text-muted)',
            }}
          >
            {pp}/{ppMax}
          </span>
        )}
      </span>
    </button>
  );
}
