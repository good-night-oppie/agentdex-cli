import React from 'react';

export interface StatBarProps {
  /** Stat name — "HP" | "Atk" | "Def" | "SpA" | "SpD" | "Spe" auto-colors the bar. */
  label: string;
  /** Optional 中文 gloss under the label. */
  zh?: string;
  /** Numeric stat value. */
  value: number;
  /** Scale max for the bar fill. Default 200. */
  max?: number;
  /** Override bar color (any CSS color / token). */
  color?: string;
  /** Tint the value text with the bar color (use to flag the win-con stat). */
  highlight?: boolean;
  style?: React.CSSProperties;
}

/**
 * Showdown-style genome stat row: label, value, proportional bar.
 * @startingPoint section="Battle" subtitle="Dex genome stat row" viewport="280x28"
 */
export function StatBar(props: StatBarProps): JSX.Element;
