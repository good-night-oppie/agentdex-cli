import React from 'react';

/**
 * Owner / agent avatar. Initials on a cool steel gradient, or a sprite
 * glyph for an agent token. Square-rounded for agents, circle for users.
 */
export function Avatar({
  label,
  glyph,
  size = 28,
  shape = 'circle', // 'circle' | 'square'
  tone = 'steel',   // 'steel' | 'own' | 'opp'
  style,
  ...rest
}) {
  const tones = {
    steel: 'linear-gradient(135deg, #2B3346, #444F6B)',
    own:   'linear-gradient(160deg, #2A3A1A, #1A2410)',
    opp:   'linear-gradient(160deg, #3A2418, #241208)',
  };
  const initials = (label || '')
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div
      style={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: shape === 'circle' ? '50%' : 'var(--r-md)',
        background: tones[tone] || tones.steel,
        border: '1px solid var(--line-2)',
        display: 'grid',
        placeItems: 'center',
        fontFamily: glyph ? 'inherit' : 'var(--font-mono)',
        fontWeight: 700,
        fontSize: glyph ? size * 0.5 : Math.max(10, size * 0.4),
        color: 'var(--ink-2)',
        ...style,
      }}
      {...rest}
    >
      {glyph || initials}
    </div>
  );
}
