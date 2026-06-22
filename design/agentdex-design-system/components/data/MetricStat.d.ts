import React from 'react';

export interface MetricStatProps {
  /** EN label, e.g. "ELO" | "Win rate". */
  label: string;
  /** Optional 中文 gloss after the label. */
  zh?: string;
  /** The headline value (string or number). */
  value: React.ReactNode;
  /** Small trailing context, e.g. "±41 RD" or "38–12". */
  sub?: React.ReactNode;
  /** Numeric delta → ▲/▼ with accent/danger color, or a preformatted node. */
  delta?: number | string;
  /** Color of the headline value. */
  tone?: 'default' | 'elo' | 'win' | 'data';
  style?: React.CSSProperties;
}

/**
 * Metric tile (label + big mono number + delta) for genome HUD / ladder stats.
 * @startingPoint section="Data" subtitle="Metric stat tile" viewport="160x64"
 */
export function MetricStat(props: MetricStatProps): JSX.Element;
