import * as React from 'react';

export interface AvatarProps {
  /** Name to derive initials from (used when no glyph). */
  label?: string;
  /** Emoji / sprite glyph for an agent token (overrides initials). */
  glyph?: React.ReactNode;
  /** Pixel size. @default 28 */
  size?: number;
  /** @default "circle" — use "square" for agent tokens */
  shape?: 'circle' | 'square';
  /** Gradient tone. @default "steel" */
  tone?: 'steel' | 'own' | 'opp';
  style?: React.CSSProperties;
}

/**
 * Owner avatar (circle, initials on steel) or agent token (square,
 * sprite glyph). own/opp tones tint the two battle sides.
 */
export function Avatar(props: AvatarProps): React.ReactElement;
