import React from 'react';

/**
 * Panel card — the core unit of the arena. Optional uppercase-mono
 * header strip with a right-aligned meta slot. Selected/winner states
 * add a colored ring glow.
 */
export function Card({
  title,
  headerRight,
  children,
  selected = false,
  state = 'default', // 'default' | 'selected' | 'winner'
  padded = true,
  style,
  bodyStyle,
  ...rest
}) {
  const ring =
    state === 'winner'
      ? 'var(--glow-winner)'
      : selected || state === 'selected'
      ? 'var(--glow-active)'
      : 'none';
  const borderColor =
    state === 'winner'
      ? 'rgba(244,183,49,.5)'
      : selected || state === 'selected'
      ? 'var(--lime)'
      : 'var(--line)';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
        overflow: 'hidden',
        background: 'var(--surface-card)',
        border: `1px solid ${borderColor}`,
        borderRadius: 'var(--r-lg)',
        boxShadow: ring,
        transition: 'border-color var(--dur-2) var(--ease-snap), box-shadow var(--dur-2)',
        ...style,
      }}
      {...rest}
    >
      {title != null && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            padding: '11px 14px',
            borderBottom: '1px solid var(--line)',
            flexShrink: 0,
          }}
        >
          <h3
            style={{
              margin: 0,
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: 'var(--ls-eyebrow)',
              textTransform: 'uppercase',
              color: 'var(--mut)',
            }}
          >
            {title}
          </h3>
          {headerRight && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--dim)',
              }}
            >
              {headerRight}
            </div>
          )}
        </div>
      )}
      <div
        style={{
          padding: padded ? 14 : 0,
          minHeight: 0,
          overflow: 'auto',
          flex: 1,
          ...bodyStyle,
        }}
      >
        {children}
      </div>
    </div>
  );
}
