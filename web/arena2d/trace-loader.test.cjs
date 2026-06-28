/* Unit tests for trace-loader.js pure helpers — run with `node --test web/arena2d/`.
 *
 * Guards the PR #614 review fix: a live ?trace= doc must NEVER fall back to the baked
 * demo battle, so an empty live log resolves to a "waiting" action (not a demo render),
 * while a non-empty log boots the engine on the real battle data. arena2d JS is not part
 * of the CI invariant gates today; this file is runnable standalone via `node --test`.
 */
const test = require("node:test");
const assert = require("node:assert");
const { toArenaData, decideLiveRender } = require("./trace-loader.js");

test("toArenaData splits the protocol log and maps decisions", () => {
  const data = toArenaData({
    log: "|turn|1\n|move|p1a: Pikachu|Thunderbolt\n",
    decisions: [{ move: "Thunderbolt", rationale: "stab", considered: [{ move: "Quick Attack", why_not: "weak" }] }],
  });
  assert.deepEqual(data.LOG, ["|turn|1", "|move|p1a: Pikachu|Thunderbolt"]); // blank lines dropped
  assert.equal(data.RATIONALES.length, 1);
  assert.equal(data.RATIONALES[0].move, "Thunderbolt");
  assert.deepEqual(data.RATIONALES[0].considered, [{ move: "Quick Attack", why_not: "weak" }]);
});

test("decideLiveRender boots on a non-empty live log", () => {
  const r = decideLiveRender({ log: "|turn|1\n|move|p1a: Pikachu|Thunderbolt", decisions: [] });
  assert.equal(r.action, "boot");
  assert.deepEqual(r.data.LOG, ["|turn|1", "|move|p1a: Pikachu|Thunderbolt"]);
});

test("decideLiveRender waits (never the demo) on an empty live log", () => {
  // This is the PR #614 review case: /live.json returns {log:"", decisions:[]} before the
  // first SSE frame or after a failed stream — must NOT render the baked demo battle.
  const r = decideLiveRender({ log: "", decisions: [] });
  assert.equal(r.action, "waiting");
  assert.deepEqual(r.data.LOG, []);
});

test("decideLiveRender treats a whitespace-only log as empty (waiting)", () => {
  const r = decideLiveRender({ log: "\n\n", decisions: [] });
  assert.equal(r.action, "waiting");
  assert.deepEqual(r.data.LOG, []);
});
