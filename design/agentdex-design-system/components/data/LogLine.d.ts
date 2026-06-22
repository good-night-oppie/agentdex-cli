import React from 'react';

export interface LogLineProps {
  /** Timestamp / turn tag, e.g. "T07". */
  ts?: React.ReactNode;
  /** Body color role. */
  tone?: 'default' | 'agent' | 'think' | 'decide' | 'dmg' | 'eff' | 'heal' | 'faint';
  /** Small bold prefix tag, e.g. "DECIDE". */
  label?: React.ReactNode;
  /** Line content — plain text or rich inline nodes. */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * One mono ticker/trace line: timestamp + tone-colored body + optional tag.
 * @startingPoint section="Data" subtitle="Battle log / trace line" viewport="360x24"
 */
export function LogLine(props: LogLineProps): JSX.Element;
