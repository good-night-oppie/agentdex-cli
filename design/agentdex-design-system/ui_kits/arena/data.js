// AgentDex Arena — fixture data lifted from the real dashboard fixtures.
// Bilingual EN/ZH woven where the product surfaces glossary terms.
window.ARENA_DATA = {
  owner: { name: 'oppie', gh: 'good-night-oppie', initial: 'O' },
  roster: [
    { id: 'apex7',  name: 'Apex-7',  types: ['fire','dark'],      gen: 3, status: 'active battle', pending: false, elo: 1487, rd: 41, wr: 76, win: 38, loss: 12, tier: 'OU',
      stats: { hp: 410, atk: 122, def: 96, spa: 145, spd: 104, spe: 138 },
      genome: { temperature: 0.7, planning: 'on', switching: 'aggressive', memory: 'on' },
      prompt: 'Set up fast with Nasty Plot, then sweep. Switch only to preserve momentum, never out of fear.' },
    { id: 'vertex3',name: 'Vertex-3',types: ['water','psychic'],  gen: 2, status: 'idle', pending: false, elo: 1421, rd: 53, wr: 68, win: 29, loss: 14, tier: 'OU',
      stats: { hp: 388, atk: 88, def: 130, spa: 132, spd: 121, spe: 99 },
      genome: { temperature: 0.5, planning: 'on', switching: 'balanced', memory: 'on' },
      prompt: 'Stall and pivot. Scout the opponent\u2019s set before committing to a line.' },
    { id: 'sigma1', name: 'Sigma-1', types: ['psychic','steel'],  gen: 1, status: 'pending evo', pending: true, elo: 1338, rd: 88, wr: 54, win: 14, loss: 12, tier: 'UU',
      stats: { hp: 360, atk: 70, def: 142, spa: 118, spd: 138, spe: 84 },
      genome: { temperature: 0.4, planning: 'off', switching: 'passive', memory: 'off' },
      prompt: '' },
    { id: 'rho9',   name: 'Rho-9',   types: ['grass','poison'],    gen: 2, status: 'idle', pending: false, elo: 1402, rd: 47, wr: 63, win: 22, loss: 13, tier: 'OU',
      stats: { hp: 402, atk: 110, def: 104, spa: 96, spd: 112, spe: 128 },
      genome: { temperature: 0.6, planning: 'on', switching: 'balanced', memory: 'on' },
      prompt: 'Spread hazards, then chip with Sludge Bomb. Sack a mon to keep entry hazards up.' },
  ],
  battle: {
    format: 'gen9randombattle', turn: 7, live: true,
    p1: { trainer: 'Apex-7', species: 'Houndstone', token: 'A7', hp: 64, max: 100, status: null, types: ['fire','dark'] },
    p2: { trainer: 'rival/Kpax', species: 'Clodsire', token: 'KP', hp: 22, max: 100, status: 'psn', types: ['ground','poison'] },
    moves: [
      { name: 'Flamethrower', type: 'fire', category: 'Special', pp: 12, ppMax: 15 },
      { name: 'Dark Pulse',   type: 'dark', category: 'Special', pp: 8,  ppMax: 15 },
      { name: 'Nasty Plot',   type: 'dark', category: 'Status',  pp: 18, ppMax: 20 },
      { name: 'Shadow Ball',  type: 'ghost',category: 'Special', pp: 0,  ppMax: 15 },
    ],
    log: [
      { ts: 'T05', tone: 'decide', label: 'DECIDE', text: 'Nasty Plot \u2014 free setup, opp locked into status' },
      { ts: 'T06', tone: 'think',  text: 'speed tier won by 14 \u00b7 +2 SpA banked' },
      { ts: 'T06', tone: 'eff',    text: 'Flamethrower \u2192 super effective! 247 dmg' },
      { ts: 'T06', tone: 'dmg',    text: 'Clodsire poisoned \u2014 12% chip at turn end' },
      { ts: 'T07', tone: 'decide', label: 'DECIDE', text: 'Dark Pulse for the KO line' },
    ],
  },
  evolution: {
    from: 2, to: 3, eloUp: 66, ciSig: true,
    cols: [
      { gen: 1, val: 28, kept: false }, { gen: 2, val: 52, kept: false }, { gen: 3, val: 84, kept: true },
    ],
    mutation: { head: 'Gen 3 mutation 进化', body: 'Raised switching aggression and added a momentum clause \u2014 stopped switching out of winning positions.' },
  },
  ladder: [
    { rank: 1, name: 'Kpax/rival', elo: 1604, wr: 81, you: false },
    { rank: 2, name: 'Apex-7', elo: 1487, wr: 76, you: true },
    { rank: 3, name: 'mira/oss', elo: 1463, wr: 72, you: false },
    { rank: 4, name: 'Vertex-3', elo: 1421, wr: 68, you: true },
    { rank: 5, name: 'Rho-9', elo: 1402, wr: 63, you: true },
  ],
};
