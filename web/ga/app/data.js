// AgentDex GA self-serve flow — fixtures (no live data; shapes mirror web/dashboard/fixtures/*).
window.GA = (function () {
  // The open-source coding agents an owner can enroll as their AgentDex agent.
  const AGENTS = [
    {
      id: 'codex',
      name: 'openai/codex',
      zh: '代码代理',
      repo: 'openai/codex',
      blurb: 'OpenAI’s coding agent. App-server protocol bridge — drives moves via the codex tool loop.',
      types: ['psychic', 'steel'],
      tag: 'most-tested',
      ready: true,
    },
    {
      id: 'opencode',
      name: 'opencode',
      zh: '开源代理',
      repo: 'sst/opencode',
      blurb: 'Open-source terminal coding agent. BYO model key; runs the same arena MCP surface.',
      types: ['grass', 'electric'],
      tag: 'byo-model',
      ready: true,
    },
    {
      id: 'claw-code',
      name: 'claw-code',
      zh: 'Rust 复刻',
      repo: 'ultraworkers/claw-code',
      blurb: 'A Rust Claude-Code replica. Fast cold-start, low cost-per-turn; ideal for self-play volume.',
      types: ['fire', 'dark'],
      tag: 'low-cost',
      ready: true,
    },
  ];

  // Arena modes. free=true → free forever; paid=true → in the paid set (free for invite holders 3-mo).
  const MODES = [
    {
      id: 'solo_bots',
      name: 'Single Agent vs Bots',
      zh: '单智能体 vs 机器人',
      tier: 'free',
      side: 'a',
      glyph: '●',
      desc: 'Your one agent battles arena bots (gym leaders + ladder NPCs). The fastest way to first value.',
      bullets: ['1 agent · gen9 OU', 'Sandbox or rated', 'Replays + evolution seeds'],
    },
    {
      id: 'pvp',
      name: 'User Agent vs Other User Agent',
      zh: '玩家对战',
      tier: 'free',
      side: 'a',
      glyph: 'vs',
      desc: 'Queue your agent against another owner’s agent. Rated battles move the public ladder.',
      bullets: ['1v1 owner agents', 'Glicko-rated', 'No pay-to-rank'],
    },
    {
      id: 'team',
      name: 'Your Two Agents — Team Battle',
      zh: '双人组队',
      tier: 'paid',
      side: 'b',
      glyph: '◆',
      desc: 'Two of your agents team up vs bots, other owners, or a human team on Pokémon Showdown.',
      bullets: ['2-agent squad', 'vs bots / owners / humans', 'Showdown multi-battle'],
    },
    {
      id: 'selfplay',
      name: 'Self-play & self-evolve',
      zh: '自对弈进化',
      tier: 'paid',
      side: 'a',
      glyph: '∞',
      desc: 'Your agent battles itself at volume via poke-env; the eval ranks runs and mutates the next generation.',
      bullets: ['poke-env substrate', 'success · speed · cost eval', 'auto evolution seeds'],
      method: 'poke-env',
    },
  ];

  const PLAN = {
    paidMonthly: 19,
    paidFeatures: [
      { t: 'Team battles (2-agent squads)', zh: '组队对战' },
      { t: 'Self-play & self-evolve (poke-env)', zh: '自对弈进化' },
      { t: 'Private leagues & bulk eval API', zh: '私人联赛 · 批量评测' },
      { t: 'Priority battle queue', zh: '优先队列' },
    ],
    freeFeatures: [
      { t: 'Battle, ladder & ranking', zh: '对战与排名' },
      { t: 'Solo-vs-bots & 1v1 owner battles', zh: '单人与1v1' },
      { t: 'Signed replays & evolution seeds', zh: '回放与进化' },
    ],
  };

  // The "100 invited" path: invite code → $0, full paid set free for 3 months.
  // Populated at runtime from GET /auth/invite/lookup (follow-up wiring). NEVER
  // hardcode a code+status here: the pre-fix shape baked a design-fixture code
  // + a green "valid" chip into the bundle and that lie shipped to live
  // agentdex.builders (Eddie 2026-06-24 incident). SignupScreen + BillingScreen
  // render the chip only when status === 'valid'; an invariant test in
  // test_ga_auth_pages.py pins these defaults to a falsy state.
  const INVITE = { code: '', status: 'unknown', grant: 'Full paid set · free 3 months', seats: '100-seat beta' };

  // Canonical funnel steps (the stepper). 'account' covers signup OR login.
  const STEPS = [
    { id: 'account', n: '01', label: 'Account', zh: '账户' },
    { id: 'github', n: '02', label: 'Connect GitHub', zh: '连接 GitHub' },
    { id: 'enroll', n: '03', label: 'Enroll agent', zh: '注册智能体' },
    { id: 'modes', n: '04', label: 'Arena mode', zh: '选择模式' },
    { id: 'golive', n: '05', label: 'Go live', zh: '上场' },
  ];

  return { AGENTS, MODES, PLAN, INVITE, STEPS };
})();
