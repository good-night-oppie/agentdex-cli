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

const { BattleStream, Teams, TeamValidator } = ps;

const MAX_BATTLES = Number(process.env.ADX_SIDECAR_MAX_BATTLES || 4);
const battles = new Map(); // battleId -> entry

const out = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
const drain = () => new Promise((resolve) => setImmediate(resolve));

function newEntry() {
  return {
    stream: new BattleStream(),
    inputLog: [],
    pending: { p1: null, p2: null },
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
            if (line.startsWith('|turn|')) {
              entry.turns = Number(line.split('|')[2]);
            } else if (line.startsWith('|win|')) {
              entry.winner = line.split('|')[2];
            } else if (line === '|tie' || line.startsWith('|tie|')) {
              // NOT startsWith('|tie') — that also matches '|tier|' (measured:
              // every randombattle "tied" at turn 1 via the tier announcement).
              entry.winner = '';
            }
          }
        } else if (type === 'sideupdate') {
          const snl = rest.indexOf('\n');
          const side = rest.slice(0, snl);
          const line = rest.slice(snl + 1);
          if (line.startsWith('|request|')) {
            const reqJson = line.slice('|request|'.length);
            if (reqJson) entry.pending[side] = JSON.parse(reqJson);
          } else if (line.startsWith('|error|')) {
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
  const state = {
    pending: {
      p1: entry.winner === null ? entry.pending.p1 : null,
      p2: entry.winner === null ? entry.pending.p2 : null,
    },
    errors,
    turns: entry.turns,
    end:
      entry.winner === null
        ? null
        : {
            winner: entry.winner,
            turns: entry.turns,
            inputLog: entry.inputLog,
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
          entry.pending[side] = null; // consumed; re-filled by the next |request|
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
    if (op === 'rss') {
      return out({ id, ok: true, rss: process.memoryUsage().rss, active: battles.size });
    }
    if (op === 'stop') {
      const entry = battles.get(msg.battle);
      if (entry) {
        await writeBattle(entry, `>forcetie`);
        battles.delete(msg.battle);
      }
      return out({ id, ok: true });
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
