import React from 'react';

export interface HPBarProps {
  /** EN stat label, e.g. "HP · Apex-7". Omit to hide the label row. */
  name?: string;
  /** Optional 中文 gloss shown faintly after the EN label. */
  zh?: string;
  /** Current HP. */
  cur: number;
  /** Max HP. Default 100. */
  max?: number;
  /** Show the "cur / max" numeric readout. Default true. */
  showValues?: boolean;
  /** Force a state instead of deriving it from the fraction. */
  state?: 'ok' | 'warn' | 'low' | 'fainted';
  /** Track height in px. Default 10. */
  height?: number;
  style?: React.CSSProperties;
}

/**
 * Trichrome HP bar (green ≤100→45, amber ≤45→20, red ≤20→0, dim when fainted)
 * with a snappy drain transition. The core battle health widget.
 * @startingPoint section="Battle" subtitle="Animated trichrome HP bar" viewport="320x60"
 */
export function HPBar(props: HPBarProps): JSX.Element;
