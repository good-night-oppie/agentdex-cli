import * as React from 'react';

export type PokemonType =
  | 'normal' | 'fire' | 'water' | 'grass' | 'electric' | 'ice'
  | 'fighting' | 'poison' | 'ground' | 'flying' | 'psychic' | 'bug'
  | 'rock' | 'ghost' | 'dragon' | 'dark' | 'steel' | 'fairy';

export interface TypeBadgeProps {
  /** Canonical Pokémon type — sets the badge color automatically. */
  type?: PokemonType;
  /** Override label text (defaults to the type name). */
  label?: string;
  /** Custom color for non-type tags (Electric Terrain, ability). */
  color?: string;
  /** @default "md" */
  size?: 'sm' | 'md';
  style?: React.CSSProperties;
}

/**
 * Pokémon-convention type badge — agents and moves are type-coded.
 * Text color auto-flips for light type backgrounds.
 *
 * @startingPoint section="Badges" subtitle="Type-coded agent/move badges" viewport="700x140"
 */
export function TypeBadge(props: TypeBadgeProps): React.ReactElement;
