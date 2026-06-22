import * as React from 'react';

export interface ChipProps {
  children?: React.ReactNode;
  /** @default "default" */
  tone?: 'default' | 'ok' | 'live' | 'gold' | 'data';
  /** Force the leading dot on/off. Defaults on for tone="live". */
  dot?: boolean;
  style?: React.CSSProperties;
}

/**
 * Mono pill for topbar metadata: format, lane, LIVE indicator, SSE
 * status. tone="live" blinks a ● dot (respects reduced-motion).
 */
export function Chip(props: ChipProps): React.ReactElement;
