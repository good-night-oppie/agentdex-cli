import * as React from 'react';

export interface ButtonProps {
  children?: React.ReactNode;
  /** Visual weight. @default "primary" */
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  /** @default "md" */
  size?: 'sm' | 'md' | 'lg';
  iconLeft?: React.ReactNode;
  iconRight?: React.ReactNode;
  disabled?: boolean;
  type?: 'button' | 'submit' | 'reset';
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  style?: React.CSSProperties;
}

/**
 * Primary action control. Lime-fill primary for the one true CTA
 * (Enroll, Queue battle); ghost for secondary lime actions; danger
 * for forfeit/destructive.
 *
 * @startingPoint section="Core" subtitle="Action buttons — primary / ghost / danger" viewport="700x180"
 */
export function Button(props: ButtonProps): React.ReactElement;
