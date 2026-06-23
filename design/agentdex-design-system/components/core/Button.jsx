import React from 'react';

/**
 * AgentDex primary action button. Geometric, rounded, snappy.
 */
export function Button({
  children,
  variant = 'primary',
  size = 'md',
  iconLeft,
  iconRight,
  disabled = false,
  type = 'button',
  onClick,
  style,
  ...rest
}) {
  const sizes = {
    sm: { height: 28, padding: '0 12px', fontSize: 12, radius: 'var(--r-sm)' },
    md: { height: 36, padding: '0 18px', fontSize: 14, radius: 'var(--r-sm)' },
    lg: { height: 44, padding: '0 24px', fontSize: 15, radius: 'var(--r-md)' },
  };
  const s = sizes[size] || sizes.md;

  const variants = {
    primary: {
      background: 'var(--lime)',
      color: 'var(--on-accent)',
      border: '1px solid var(--lime)',
      fontWeight: 700,
    },
    secondary: {
      background: 'var(--surface-2)',
      color: 'var(--ink)',
      border: '1px solid var(--line-2)',
      fontWeight: 600,
    },
    ghost: {
      background: 'transparent',
      color: 'var(--text-accent)',
      border: '1px solid rgba(166,226,46,.28)',
      fontWeight: 600,
    },
    danger: {
      background: 'var(--live-soft)',
      color: 'var(--text-danger)',
      border: '1px solid rgba(255,70,85,.35)',
      fontWeight: 600,
    },
  };
  const v = variants[variant] || variants.primary;

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        height: s.height,
        padding: s.padding,
        borderRadius: s.radius,
        fontFamily: 'var(--font-display)',
        fontSize: s.fontSize,
        letterSpacing: '.01em',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        whiteSpace: 'nowrap',
        transition: 'transform var(--dur-1) var(--ease-snap), background var(--dur-1), border-color var(--dur-1), filter var(--dur-1)',
        ...v,
        ...style,
      }}
      onMouseDown={(e) => { if (!disabled) e.currentTarget.style.transform = 'translateY(1px) scale(.99)'; }}
      onMouseUp={(e) => { e.currentTarget.style.transform = ''; }}
      onMouseLeave={(e) => { e.currentTarget.style.transform = ''; }}
      {...rest}
    >
      {iconLeft}
      {children}
      {iconRight}
    </button>
  );
}
