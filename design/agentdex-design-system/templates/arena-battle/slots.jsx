// Thin wrappers for the Arena template.
// `name` is a reserved attribute on <x-import> (the runtime never forwards it
// as a prop), so we remap non-reserved props onto the DS components' `name`.
const NS = () => (typeof window !== 'undefined' && window.AgentDexDesignSystem_26893a) || {};

function MoveSlot(props) {
  const { moveName, ...rest } = props;
  return React.createElement(NS().MoveButton, Object.assign({ name: moveName }, rest));
}

function AgentRow(props) {
  const { agentName, ...rest } = props;
  return React.createElement(NS().AgentCard, Object.assign({ name: agentName }, rest));
}

function HpRow(props) {
  const { hpName, ...rest } = props;
  return React.createElement(NS().HPBar, Object.assign({ name: hpName }, rest));
}

module.exports = { MoveSlot, AgentRow, HpRow };
