import * as React from 'react';

export interface TierProps {
  /** Tier label — OU / UU / NU / S / Uber. @default "OU" */
  tier?: string;
  /** Force tone; defaults gold for S/OU/Uber, lime otherwise. */
  tone?: 'lime' | 'gold';
  style?: React.CSSProperties;
}

/**
 * Genome strength tier chip (Showdown tiers reused as agent ranks).
 */
export function Tier(props: TierProps): React.ReactElement;
