import React from 'react';
import { TypeBadge } from '../badges/TypeBadge.jsx';

/**
 * Roster agent card — name, type badges, format/team meta, and a generation
 * + status line. Selected state lifts the lime ring; `pending` paints the
 * generation gold (evolution pending).
 */
export function AgentCard({
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
  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      style={{
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
        ...style,
      }}
      onMouseEnter={(e) => { if (onClick && !selected) e.currentTarget.style.transform = 'translateY(-1px)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.transform = ''; }}
      {...rest}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 13, color: 'var(--text-strong)' }}>
          {name}
        </span>
        {rating != null && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-winner)' }}>{rating}</span>
        )}
      </div>
      {types.length > 0 && (
        <div style={{ display: 'flex', gap: 4 }}>
          {types.map((t) => <TypeBadge key={t} type={t} size="sm" />)}
        </div>
      )}
      {meta && (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>{meta}</span>
      )}
      {(gen != null || status) && (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: pending ? 'var(--text-winner)' : 'var(--text-accent)' }}>
          {gen != null && `gen ${gen}`}{gen != null && status ? ' · ' : ''}{status}
        </span>
      )}
    </div>
  );
}
