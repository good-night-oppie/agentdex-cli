#!/usr/bin/env node
/* build_arena2d_dex.cjs — regenerate web/arena2d/dex.js (the DERIVED type layer) for
 * whatever battle is currently in data.js, sourced from pokemon-showdown's OWN dex data
 * (the same engine the arena runs). Emits the universal Gen-9 type CHART + only the
 * species/move typings the current battle's LOG references, so the matchup widget +
 * candidate-fan badges ground the agent's claims in the real chart.
 *
 *   node tools/build_arena2d_dex.cjs web/arena2d/data.js web/arena2d/dex.js
 *
 * Reads the cast from data.js: |switch|...|<Species>, ...  +  |move|...|<Move Name>|...
 * and RATIONALES[].move / considered[].move (move ids). Form-exact species names are
 * kept as the log writes them (e.g. "Zamazenta-Crowned"), matched to PS via toID. */
"use strict";
const fs = require("fs");

const PS = "/home/admin/gh/agentdex-cli/packages/adx_showdown/node_modules/pokemon-showdown";
const pokedex = (() => { const m = require(PS + "/dist/data/pokedex.js"); return m.Pokedex || m.BattlePokedex || m; })();
const movedex = (() => { const m = require(PS + "/dist/data/moves.js"); return m.Moves || m.BattleMovedex || m; })();
const toID = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

const [, , dataPath, outPath] = process.argv;
if (!dataPath || !outPath) { console.error("usage: build_arena2d_dex.cjs <data.js> <dex.js>"); process.exit(2); }
const src = fs.readFileSync(dataPath, "utf8");
const LOG = JSON.parse(src.match(/LOG:\s*(\[[\s\S]*?\]),\s*\n/)[1]);
const RATIONALES = JSON.parse(src.match(/RATIONALES:\s*(\[[\s\S]*\])\s*\n\};/)[1]);

// ---- collect the cast from the log ----
const speciesNames = new Set();   // form-exact display names, as the log writes them
const moveNames = new Set();      // display move names from |move| lines
for (const line of LOG) {
  const p = line.split("|");
  if ((p[1] === "switch" || p[1] === "drag") && p[3]) speciesNames.add(p[3].split(",")[0].trim());
  if (p[1] === "detailschange" && p[3]) speciesNames.add(p[3].split(",")[0].trim());
  if (p[1] === "move" && p[3]) moveNames.add(p[3]);
}
// move IDs the agent's rationale/fan reference (so every fan badge resolves)
const moveIds = new Set();
for (const r of RATIONALES) {
  if (r.move) moveIds.add(toID(r.move));
  for (const c of r.considered || []) if (c.move) moveIds.add(toID(c.move));
}

// ---- resolve types from PS data ----
const missing = [];
const SPECIES = {};
for (const name of [...speciesNames].sort()) {
  const e = pokedex[toID(name)];
  if (e && e.types) SPECIES[name] = e.types;
  else missing.push("species:" + name);
}
const MOVES = {};
const addMove = (key, id) => {
  const m = movedex[id];
  if (m && m.type && m.category !== "Status") MOVES[key] = m.type;   // status moves have no offensive type lens
  else if (m && m.type) MOVES[key] = m.type;                          // keep type for display anyway
  else missing.push("move:" + key);
};
for (const nm of [...moveNames].sort()) addMove(nm, toID(nm)); // display-name key (battle.js uses the |move| name)
for (const id of [...moveIds].sort()) if (!(id in MOVES)) addMove(id, id); // id key (mind.js fan + moveType use ids)

// ---- emit dex.js (universal CHART + this battle's SPECIES/MOVES) ----
const CHART = {
  Normal: { sup: [], res: ["Rock", "Steel"], imm: ["Ghost"] },
  Fire: { sup: ["Grass", "Ice", "Bug", "Steel"], res: ["Fire", "Water", "Rock", "Dragon"], imm: [] },
  Water: { sup: ["Fire", "Ground", "Rock"], res: ["Water", "Grass", "Dragon"], imm: [] },
  Electric: { sup: ["Water", "Flying"], res: ["Electric", "Grass", "Dragon"], imm: ["Ground"] },
  Grass: { sup: ["Water", "Ground", "Rock"], res: ["Fire", "Grass", "Poison", "Flying", "Bug", "Dragon", "Steel"], imm: [] },
  Ice: { sup: ["Grass", "Ground", "Flying", "Dragon"], res: ["Fire", "Water", "Ice", "Steel"], imm: [] },
  Fighting: { sup: ["Normal", "Ice", "Rock", "Dark", "Steel"], res: ["Poison", "Flying", "Psychic", "Bug", "Fairy"], imm: ["Ghost"] },
  Poison: { sup: ["Grass", "Fairy"], res: ["Poison", "Ground", "Rock", "Ghost"], imm: ["Steel"] },
  Ground: { sup: ["Fire", "Electric", "Poison", "Rock", "Steel"], res: ["Grass", "Bug"], imm: ["Flying"] },
  Flying: { sup: ["Grass", "Fighting", "Bug"], res: ["Electric", "Rock", "Steel"], imm: [] },
  Psychic: { sup: ["Fighting", "Poison"], res: ["Psychic", "Steel"], imm: ["Dark"] },
  Bug: { sup: ["Grass", "Psychic", "Dark"], res: ["Fire", "Fighting", "Poison", "Flying", "Ghost", "Steel", "Fairy"], imm: [] },
  Rock: { sup: ["Fire", "Ice", "Flying", "Bug"], res: ["Fighting", "Ground", "Steel"], imm: [] },
  Ghost: { sup: ["Psychic", "Ghost"], res: ["Dark"], imm: ["Normal"] },
  Dragon: { sup: ["Dragon"], res: ["Steel"], imm: ["Fairy"] },
  Dark: { sup: ["Psychic", "Ghost"], res: ["Fighting", "Dark", "Fairy"], imm: [] },
  Steel: { sup: ["Ice", "Rock", "Fairy"], res: ["Fire", "Water", "Electric", "Steel"], imm: [] },
  Fairy: { sup: ["Fighting", "Dragon", "Dark"], res: ["Fire", "Poison", "Steel"], imm: [] },
};

const header = `/* dex.js — DERIVED reference data (NOT the agent's words, NOT the battle log).
 * The universal Gen-9 type CHART + the species/move typings for the Pokémon in THIS
 * battle, so the mind readout can ground the agent's claims ("resists Grass", "super-
 * effective") in the real chart. SOURCED from pokemon-showdown's own dex data (the same
 * engine the arena runs) — regenerate via tools/build_arena2d_dex.cjs; do not hand-edit. */
`;
const body = `(function () {
  "use strict";
  const CHART = ${JSON.stringify(CHART, null, 2).replace(/\n/g, "\n  ")};
  const SPECIES = ${JSON.stringify(SPECIES, null, 2).replace(/\n/g, "\n  ")};
  const MOVES = ${JSON.stringify(MOVES, null, 2).replace(/\n/g, "\n  ")};
  const norm = (s) => String(s || "").trim();
  const id = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  function speciesTypes(name) { return SPECIES[norm(name)] || null; }
  function moveType(mv) { return MOVES[norm(mv)] || MOVES[id(mv)] || null; }
  function effectiveness(att, defTypes) {
    const c = CHART[att]; if (!c || !defTypes) return 1;
    let m = 1;
    for (const d of defTypes) { if (c.imm.includes(d)) return 0; if (c.sup.includes(d)) m *= 2; else if (c.res.includes(d)) m *= 0.5; }
    return m;
  }
  function verdict(m) {
    if (m === 0) return { k: "imm", x: "\\u00d70", t: "IMMUNE" };
    if (m >= 4) return { k: "sup", x: "\\u00d74", t: "4\\u00d7 SUPER" };
    if (m >= 2) return { k: "sup", x: "\\u00d72", t: "SUPER-EFFECTIVE" };
    if (m <= 0.25) return { k: "res", x: "\\u00d7\\u00bc", t: "DOUBLY RESISTED" };
    if (m <= 0.5) return { k: "res", x: "\\u00d7\\u00bd", t: "RESISTED" };
    return { k: "neu", x: "\\u00d71", t: "NEUTRAL" };
  }
  window.__ARENA2D_DEX = { types: Object.keys(CHART), speciesTypes, moveType, effectiveness, verdict };
})();
`;
fs.writeFileSync(outPath, header + body);
console.log(`wrote ${outPath}: ${Object.keys(SPECIES).length} species, ${Object.keys(MOVES).length} move typings` + (missing.length ? `\n  UNRESOLVED (${missing.length}): ${missing.join(", ")}` : " (all resolved)"));
