import * as React from 'react';

export interface CardProps {
  /** Uppercase-mono header label. Omit for a headerless card. */
  title?: React.ReactNode;
  /** Right-aligned meta slot in the header (e.g. format, turn count). */
  headerRight?: React.ReactNode;
  children?: React.ReactNode;
  /** Lime ring + border (shorthand for state="selected"). */
  selected?: boolean;
  /** @default "default" */
  state?: 'default' | 'selected' | 'winner';
  /** Pad the body. Set false for full-bleed (battle scene, sprites). @default true */
  padded?: boolean;
  style?: React.CSSProperties;
  bodyStyle?: React.CSSProperties;
}

/**
 * The arena's core container. Every panel (Roster, Agent Pane, Live
 * Battle, Evolution, Ladder) is a Card with a mono header strip.
 * `state="winner"` casts a gold ring; `selected` casts a lime ring.
 *
 * @startingPoint section="Core" subtitle="Panel card with mono header" viewport="700x260"
 */
export function Card(props: CardProps): React.ReactElement;
