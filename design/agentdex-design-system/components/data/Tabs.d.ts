import React from 'react';

export interface TabItem {
  /** Stable id passed to onChange. */
  id: string;
  /** EN label. */
  label: string;
  /** Optional 中文 gloss. */
  zh?: string;
}

export interface TabsProps {
  /** The tab definitions. */
  tabs: TabItem[];
  /** Active tab id (controlled). Defaults to the first tab. */
  value?: string;
  /** Called with the new tab id. */
  onChange?: (id: string) => void;
  style?: React.CSSProperties;
}

/**
 * Uppercase-mono tab strip with a lime active underline (Genome / Trace / Ladder).
 * @startingPoint section="Data" subtitle="Tab strip" viewport="280x40"
 */
export function Tabs(props: TabsProps): JSX.Element;
