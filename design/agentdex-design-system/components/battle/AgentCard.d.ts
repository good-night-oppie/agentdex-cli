import React from 'react';

export interface AgentCardProps {
  /** Agent name, e.g. "Apex-7". */
  name: string;
  /** Type names for the badges, e.g. ["fire","dark"]. */
  types?: string[];
  /** Mono meta line, e.g. "gen9 OU · 6-mon team". */
  meta?: string;
  /** Generation number (renders "gen N"). */
  gen?: number;
  /** Status word, e.g. "active battle" | "idle" | "pending evo". */
  status?: string;
  /** Paint the gen/status line gold (evolution pending). */
  pending?: boolean;
  /** Optional rating shown top-right (gold). */
  rating?: number | string;
  /** Lime selected ring. */
  selected?: boolean;
  onClick?: (e: React.MouseEvent<HTMLDivElement>) => void;
  style?: React.CSSProperties;
}

/**
 * Roster card for one agent — name, type badges, meta, generation + status.
 * @startingPoint section="Battle" subtitle="Roster agent card" viewport="226x96"
 */
export function AgentCard(props: AgentCardProps): JSX.Element;
