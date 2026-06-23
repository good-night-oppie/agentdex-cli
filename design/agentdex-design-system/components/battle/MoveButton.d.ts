import React from 'react';

export interface MoveButtonProps {
  /** Move name, e.g. "Flamethrower". */
  name: string;
  /** Pokémon type for the badge, e.g. "fire". */
  type?: string;
  /** Move category. Default "Special". */
  category?: 'Physical' | 'Special' | 'Status';
  /** Remaining PP. 0 disables the button. */
  pp?: number;
  /** Max PP (denominator + low-PP threshold). */
  ppMax?: number;
  /** Lime selected ring. */
  selected?: boolean;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  style?: React.CSSProperties;
}

/**
 * One of the four battle move slots: name, type badge, category, PP counter.
 * @startingPoint section="Battle" subtitle="Battle move action button" viewport="200x70"
 */
export function MoveButton(props: MoveButtonProps): JSX.Element;
