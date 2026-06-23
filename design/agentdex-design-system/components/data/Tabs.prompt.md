Controlled tab strip — uppercase-mono labels, lime active underline. The Agent Pane's Genome / Trace / Ladder switcher.

```jsx
const [tab, setTab] = React.useState('genome');
<Tabs value={tab} onChange={setTab} tabs={[
  { id: 'genome', label: 'Genome', zh: '基因' },
  { id: 'trace',  label: 'Trace',  zh: '推理' },
  { id: 'ladder', label: 'Ladder', zh: '天梯' },
]} />
```

- Controlled — you own the active id; defaults to the first tab if `value` is unset.
- Each tab may carry a `zh` gloss rendered after the EN label.
