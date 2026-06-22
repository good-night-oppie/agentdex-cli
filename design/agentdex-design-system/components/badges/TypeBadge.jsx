import React from 'react';

const TYPE_COLORS = {
  normal: '#8A8A5A', fire: '#E8703A', water: '#5590E0', grass: '#6BBF42',
  electric: '#E8C840', ice: '#98D8D8', fighting: '#C03028', poison: '#A040A0',
  ground: '#D8B048', flying: '#9AA8F0', psychic: '#E05888', bug: '#A8B820',
  rock: '#B8A038', ghost: '#6650A4', dragon: '#6830E8', dark: '#685242',
  steel: '#8888AA', fairy: '#E898E8',
};
// types that need dark text for contrast
const DARK_TEXT = new Set(['electric', 'ice', 'ground', 'flying', 'bug', 'rock', 'steel', 'fairy', 'normal']);

/**
 * Pokémon-style type badge. Pass a known type name for canonical color,
 * or a custom { label, color } for terrain / ability tags.
 */
export function TypeBadge({ type, label, color, size = 'md', style, ...rest }) {
  const key = (type || '').toLowerCase();
  const bg = color || TYPE_COLORS[key] || 'var(--surface-3)';
  const text = color ? '#fff' : DARK_TEXT.has(key) ? '#1A1A12' : '#fff';
  const sizes = {
    sm: { fontSize: 9, padding: '2px 6px' },
    md: { fontSize: 10, padding: '3px 8px' },
  };
  const s = sizes[size] || sizes.md;
  return (
    <span
      style={{
        display: 'inline-block',
        fontFamily: 'var(--font-mono)',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '.04em',
        borderRadius: 'var(--r-xs)',
        background: bg,
        color: text,
        ...s,
        ...style,
      }}
      {...rest}
    >
      {label || type}
    </span>
  );
}
