import React from 'react';

/**
 * Tab strip — uppercase-mono labels with a lime active underline. Controlled:
 * pass `value` + `onChange`. Each tab is { id, label, zh? }.
 */
export function Tabs({ tabs = [], value, onChange, style, ...rest }) {
  const active = value ?? (tabs[0] && tabs[0].id);
  return (
    <div
      role="tablist"
      style={{ display: 'flex', borderBottom: '1px solid var(--border-default)', ...style }}
      {...rest}
    >
      {tabs.map((t) => {
        const on = t.id === active;
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={on}
            type="button"
            onClick={() => onChange && onChange(t.id)}
            style={{
              flex: 1,
              padding: '10px 6px',
              background: 'none',
              border: 'none',
              borderBottom: `2px solid ${on ? 'var(--border-active)' : 'transparent'}`,
              marginBottom: -1,
              cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: 'var(--ls-label)',
              textTransform: 'uppercase',
              color: on ? 'var(--text-accent)' : 'var(--text-muted)',
              transition: 'color var(--dur-2) var(--ease-snap), border-color var(--dur-2)',
            }}
            onMouseEnter={(e) => { if (!on) e.currentTarget.style.color = 'var(--text-body)'; }}
            onMouseLeave={(e) => { if (!on) e.currentTarget.style.color = 'var(--text-muted)'; }}
          >
            {t.label}
            {t.zh && <span style={{ fontFamily: 'var(--font-zh)', marginLeft: 5 }}>{t.zh}</span>}
          </button>
        );
      })}
    </div>
  );
}
