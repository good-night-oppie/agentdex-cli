import * as React from 'react';

export interface StatusPillProps {
  /** Status key. @default "PAR" */
  status?: 'PAR' | 'BRN' | 'PSN' | 'TOX' | 'SLP' | 'FRZ' | 'healthy' | 'fainted';
  /** Override label text. */
  label?: string;
  style?: React.CSSProperties;
}

/**
 * Battle status pill — Pokémon conditions (PAR/BRN/PSN…) render solid;
 * health states (healthy/fainted) render outlined. Green=healthy,
 * amber=status, red=fainted.
 */
export function StatusPill(props: StatusPillProps): React.ReactElement;
