// adx_showdown sidecar — persistent Node process multiplexing pokemon-showdown
// BattleStream objects, speaking NDJSON over stdio. ADR-0010 §Measured-constraints
// F1: the stock multi-process Showdown server (599 MB RSS idle) is replaced by
// this single process (~165 MB at 3 concurrent battles, measured 2026-06-11).
//
// DETERMINISM (IDEAL §Arena A2): battles advance via a SYNCHRONOUS STEP
// protocol, not free-running events. Showdown commits a turn synchronously
// inside stream.write() once the final needed choice lands; `step` awaits the
// writes (fixed p1-then-p2 order), lets the reader drain on setImmediate, and
// returns the next pending request per side. Outcomes are a pure function of
// (battle seed, submitted choice sequence) — no arrival races by construction
// (measured 2026-06-11: event-driven lockstep still diverged run-to-run).
//
// Protocol (one JSON object per line):
//   requests  (stdin):  {id, op, ...}
//   responses (stdout): {id, ok: true|false, ...}
//
// Ops:
//   start  {battle, format, seed?, p1:{name,team?}, p2:{name,team?}}
//          -> {ok, state: {pending, errors, end, turns}}
//   step   {battle, choices: {p1?: str, p2?: str}}
//          -> {ok, state: {...}}
//   replay {battle, lines: [...]}            — verbatim inputLog re-simulation
//          -> {ok, state: {...end...}}
//   validate-team {format, team}             — packed team string
//   pack-team     {export}                   — export text -> packed
//   rss / stop {battle} / shutdown
//
// `state.pending.p1` is the latest |request| JSON for p1 (null if none);
// `state.errors` are |error| lines since the previous step (cleared on read);
// `state.end` is {winner, turns, inputLog} once the battle finished.

import { createInterface } from 'node:readline';
import ps from 'pokemon-showdown';

const { BattleStream, Teams, TeamValidator, Dex } = ps;

const MAX_BATTLES = Number(process.env.ADX_SIDECAR_MAX_BATTLES || 4);
const battles = new Map(); // battleId -> entry

const out = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
const KEY_LINE_RE = /^\|(move|faint|switch|drag|turn|-supereffective|-resisted|-immune|-crit)\|/;
const OBSERVABILITY_LINE_RE = /^\|(move|faint|switch|drag|turn|-supereffective|-resisted|-immune|-crit|-damage|-heal|-status|-unboost|-boost|-weather|-fieldstart|-fieldend|-activate|cant|detailschange|-start|-end)\|/;

function parseHp(hpStr) {
  if (!hpStr) return 100;
  const hpPart = hpStr.split(' ')[0];
  if (hpPart === '0' || hpPart === '0/100') return 0;
  if (!hpPart.includes('/')) {
    const val = Number(hpPart);
    return Number.isNaN(val) ? 100 : val;
  }
  const [cur, max] = hpPart.split('/').map(Number);
  if (!max) return 0;
  return Math.ceil((cur / max) * 100);
}
const drain = () => new Promise((resolve) => setImmediate(resolve));

function newEntry() {
  return {
    stream: new BattleStream(),
    inputLog: [],
    pending: { p1: null, p2: null },
    submitted: { p1: false, p2: false }, // choice in flight, not yet rejected
    active: { p1: null, p2: null }, // active species per side (from |switch|/|drag|)
    active_hp: { p1: 100, p2: 100 },
    turnLines: [],
    keyLines: [], // signature-relevant battle lines (phase-5 signatures.py)
    errors: [],
    winner: null, // null = in progress; '' = tie
    turns: 0,
    readerDone: null,
  };
}

function attachReader(battleId, entry) {
  entry.readerDone = (async () => {
    try {
      for await (const chunk of entry.stream) {
        const nl = chunk.indexOf('\n');
        const type = nl === -1 ? chunk : chunk.slice(0, nl);
        const rest = nl === -1 ? '' : chunk.slice(nl + 1);
        if (type === 'update') {
          for (const line of rest.split('\n')) {
            if (KEY_LINE_RE.test(line) && entry.keyLines.length < 3000) {
              entry.keyLines.push(line);
            }
            if (OBSERVABILITY_LINE_RE.test(line)) {
              entry.turnLines.push(line);
            }
            if (line.startsWith('|turn|')) {
              entry.turns = Number(line.split('|')[2]);
            } else if (line.startsWith('|win|')) {
              entry.winner = line.split('|')[2];
            } else if (line.startsWith('|switch|') || line.startsWith('|drag|')) {
              const parts = line.split('|');
              const side = parts[2].slice(0, 2); // 'p1a: Nick' -> 'p1'
              entry.active[side] = (parts[3] || '').split(',')[0];
              if (parts[4]) {
                entry.active_hp[side] = parseHp(parts[4]);
              }
            } else if (line === '|tie' || line.startsWith('|tie|')) {
              // NOT startsWith('|tie') — that also matches '|tier|' (measured:
              // every randombattle "tied" at turn 1 via the tier announcement).
              entry.winner = '';
            } else if (line.startsWith('|-damage|') || line.startsWith('|-heal|') || line.startsWith('|-sethp|')) {
              const parts = line.split('|');
              if (parts.length >= 4) {
                const side = parts[2].slice(0, 2);
                if (side === 'p1' || side === 'p2') {
                  entry.active_hp[side] = parseHp(parts[3]);
                }
              }
            } else if (line.startsWith('|faint|')) {
              const parts = line.split('|');
              if (parts.length >= 3) {
                const side = parts[2].slice(0, 2);
                if (side === 'p1' || side === 'p2') {
                  entry.active_hp[side] = 0;
                }
              }
            } else if (line.startsWith('|detailschange|') || line.startsWith('|-formechange|')) {
              const parts = line.split('|');
              if (parts.length >= 4) {
                const side = parts[2].slice(0, 2);
                if (side === 'p1' || side === 'p2') {
                  entry.active[side] = (parts[3] || '').split(',')[0];
                }
              }
            }
          }
        } else if (type === 'sideupdate') {
          const snl = rest.indexOf('\n');
          const side = rest.slice(0, snl);
          const line = rest.slice(snl + 1);
          if (line.startsWith('|request|')) {
            const reqJson = line.slice('|request|'.length);
            if (reqJson) {
              entry.pending[side] = JSON.parse(reqJson);
              entry.submitted[side] = false;
            }
          } else if (line.startsWith('|error|')) {
            // rejected choice: re-expose the stored request so the driver's
            // fallback rail can answer it (measured stall: destructive nulling
            // left both sides pending-less with the battle waiting).
            entry.submitted[side] = false;
            entry.errors.push({ side, error: line.slice('|error|'.length) });
          }
        }
        if (entry.winner !== null) break;
      }
    } catch (err) {
      entry.errors.push({ side: '', error: `stream-exception: ${String(err && err.message)}` });
      entry.winner = entry.winner ?? '';
      entry.streamError = String(err && err.message);
    }
  })();
}

function writeBattle(entry, line) {
  entry.inputLog.push(line);
  return entry.stream.write(line);
}

async function settledState(entry) {
  // two drain rounds: stream pushes resolve on microtasks; the for-await
  // reader consumes on macrotask boundaries.
  await drain();
  await drain();
  const errors = entry.errors.splice(0);
  const turnLines = entry.turnLines.splice(0);
  const state = {
    pending: {
      p1: entry.winner === null && !entry.submitted.p1 ? entry.pending.p1 : null,
      p2: entry.winner === null && !entry.submitted.p2 ? entry.pending.p2 : null,
    },
    active: entry.active,
    active_hp: entry.active_hp,
    log_events: turnLines,
    errors,
    turns: entry.turns,
    end:
      entry.winner === null
        ? null
        : {
            winner: entry.winner,
            turns: entry.turns,
            inputLog: entry.inputLog,
            keyLines: entry.keyLines,
            streamError: entry.streamError || null,
          },
  };
  return state;
}

async function handle(msg) {
  const { id, op } = msg;
  try {
    if (op === 'start') {
      if (battles.size >= MAX_BATTLES) {
        return out({ id, ok: false, error: `capacity: ${battles.size}/${MAX_BATTLES} battles active` });
      }
      if (battles.has(msg.battle)) {
        return out({ id, ok: false, error: `battle ${msg.battle} already active` });
      }
      const entry = newEntry();
      battles.set(msg.battle, entry);
      attachReader(msg.battle, entry);
      const startOpts = { formatid: msg.format };
      if (msg.seed) startOpts.seed = msg.seed;
      await writeBattle(entry, `>start ${JSON.stringify(startOpts)}`);
      for (const side of ['p1', 'p2']) {
        const cfg = { name: msg[side].name };
        if (msg[side].team) cfg.team = msg[side].team;
        // Random formats generate the TEAM from the PLAYER options' seed —
        // not the battle seed (battle.js getTeam). Without this, every run
        // gets fresh random teams and determinism is impossible (measured).
        if (msg[side].seed) cfg.seed = msg[side].seed;
        await writeBattle(entry, `>player ${side} ${JSON.stringify(cfg)}`);
      }
      const state = await settledState(entry);
      if (state.end) battles.delete(msg.battle);
      return out({ id, ok: true, battle: msg.battle, active: battles.size, state });
    }
    if (op === 'step') {
      const entry = battles.get(msg.battle);
      if (!entry) return out({ id, ok: false, error: `no battle ${msg.battle}` });
      // fixed submission order: p1 always before p2 — determinism by construction
      for (const side of ['p1', 'p2']) {
        const choice = (msg.choices || {})[side];
        if (choice != null) {
          entry.submitted[side] = true; // re-exposed by |error| or next |request|
          await writeBattle(entry, `>${side} ${choice}`);
        }
      }
      const state = await settledState(entry);
      if (state.end) battles.delete(msg.battle);
      return out({ id, ok: true, state });
    }
    if (op === 'replay') {
      if (battles.size >= MAX_BATTLES) {
        return out({ id, ok: false, error: `capacity: ${battles.size}/${MAX_BATTLES} battles active` });
      }
      const entry = newEntry();
      battles.set(msg.battle, entry);
      attachReader(msg.battle, entry);
      for (const line of msg.lines) await writeBattle(entry, line);
      const state = await settledState(entry);
      battles.delete(msg.battle);
      return out({ id, ok: true, state });
    }
    if (op === 'validate-team') {
      const validator = TeamValidator.get(msg.format);
      const team = Teams.unpack(msg.team);
      if (!team) return out({ id, ok: false, error: 'team failed to unpack' });
      const errors = validator.validateTeam(team);
      return out({ id, ok: true, valid: !errors, errors: errors || [] });
    }
    if (op === 'pack-team') {
      const team = Teams.import(msg.export);
      if (!team) return out({ id, ok: false, error: 'team failed to import' });
      return out({ id, ok: true, packed: Teams.pack(team) });
    }
    if (op === 'dex-rate') {
      // effective power of each move id vs a defender species: basePower x
      // 2^getEffectiveness x (getImmunity ? 1 : 0). Status moves rate 0.
      const defender = Dex.species.get(msg.defender || '');
      const types = defender.exists ? defender.types : [];
      const attacker = Dex.species.get(msg.attacker || '');
      const stabTypes = attacker.exists ? attacker.types : [];
      const ratings = {};
      for (const id of msg.moves || []) {
        const mv = Dex.moves.get(id);
        if (!mv.exists || !mv.basePower) {
          ratings[id] = 0;
          continue;
        }
        let mult = 1;
        if (types.length) {
          mult = Dex.getImmunity(mv.type, types) ? Math.pow(2, Dex.getEffectiveness(mv.type, types)) : 0;
        }
        if (stabTypes.includes(mv.type)) mult *= 1.5; // STAB
        ratings[id] = mv.basePower * mult;
      }
      return out({ id, ok: true, ratings });
    }
    if (op === 'rss') {
      if (global.gc) {
        global.gc();
      }
      return out({ id, ok: true, rss: process.memoryUsage().rss, active: battles.size });
    }
    if (op === 'stop') {
      const entry = battles.get(msg.battle);
      let inputLog = [];
      if (entry) {
        inputLog = entry.inputLog;
        await writeBattle(entry, `>forcetie`);
        battles.delete(msg.battle);
      }
      return out({ id, ok: true, inputLog });
    }
    if (op === 'shutdown') {
      out({ id, ok: true });
      process.exit(0);
    }
    return out({ id, ok: false, error: `unknown op ${op}` });
  } catch (err) {
    return out({ id, ok: false, error: String(err && err.stack ? err.message : err) });
  }
}

// serialize op handling per battle id so concurrent battles can't interleave
// a single battle's writes (global FIFO is fine at this scale).
let chain = Promise.resolve();
const rl = createInterface({ input: process.stdin, terminal: false });
rl.on('line', (line) => {
  if (!line.trim()) return;
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return out({ id: null, ok: false, error: 'bad json' });
  }
  chain = chain.then(() => handle(msg)).catch((e) => out({ id: msg.id, ok: false, error: String(e) }));
});
rl.on('close', () => process.exit(0));
out({ event: 'ready', maxBattles: MAX_BATTLES, pid: process.pid });
