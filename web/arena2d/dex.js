/* dex.js — DERIVED reference data (NOT the agent's words, NOT the battle log).
 * A minimal type chart + the species/move typings for the Pokémon in THIS battle,
 * so the mind readout can ground the agent's claims ("resists Grass", "immune to
 * Close Combat") in the real Gen-9 type chart. This is OUR reconstruction layer —
 * the UI labels it as "derived", strictly separate from the agent's rationale. */
(function () {
  "use strict";

  // attacker -> { sup: 2x targets, res: 0.5x targets, imm: 0x targets }; default 1x.
  const CHART = {
    Normal:   { sup: [], res: ["Rock", "Steel"], imm: ["Ghost"] },
    Fire:     { sup: ["Grass", "Ice", "Bug", "Steel"], res: ["Fire", "Water", "Rock", "Dragon"], imm: [] },
    Water:    { sup: ["Fire", "Ground", "Rock"], res: ["Water", "Grass", "Dragon"], imm: [] },
    Electric: { sup: ["Water", "Flying"], res: ["Electric", "Grass", "Dragon"], imm: ["Ground"] },
    Grass:    { sup: ["Water", "Ground", "Rock"], res: ["Fire", "Grass", "Poison", "Flying", "Bug", "Dragon", "Steel"], imm: [] },
    Ice:      { sup: ["Grass", "Ground", "Flying", "Dragon"], res: ["Fire", "Water", "Ice", "Steel"], imm: [] },
    Fighting: { sup: ["Normal", "Ice", "Rock", "Dark", "Steel"], res: ["Poison", "Flying", "Psychic", "Bug", "Fairy"], imm: ["Ghost"] },
    Poison:   { sup: ["Grass", "Fairy"], res: ["Poison", "Ground", "Rock", "Ghost"], imm: ["Steel"] },
    Ground:   { sup: ["Fire", "Electric", "Poison", "Rock", "Steel"], res: ["Grass", "Bug"], imm: ["Flying"] },
    Flying:   { sup: ["Grass", "Fighting", "Bug"], res: ["Electric", "Rock", "Steel"], imm: [] },
    Psychic:  { sup: ["Fighting", "Poison"], res: ["Psychic", "Steel"], imm: ["Dark"] },
    Bug:      { sup: ["Grass", "Psychic", "Dark"], res: ["Fire", "Fighting", "Poison", "Flying", "Ghost", "Steel", "Fairy"], imm: [] },
    Rock:     { sup: ["Fire", "Ice", "Flying", "Bug"], res: ["Fighting", "Ground", "Steel"], imm: [] },
    Ghost:    { sup: ["Psychic", "Ghost"], res: ["Dark"], imm: ["Normal"] },
    Dragon:   { sup: ["Dragon"], res: ["Steel"], imm: ["Fairy"] },
    Dark:     { sup: ["Psychic", "Ghost"], res: ["Fighting", "Dark", "Fairy"], imm: [] },
    Steel:    { sup: ["Ice", "Rock", "Fairy"], res: ["Fire", "Water", "Electric", "Steel"], imm: [] },
    Fairy:    { sup: ["Fighting", "Dragon", "Dark"], res: ["Fire", "Poison", "Steel"], imm: [] },
  };

  // species (form-exact, as the log names them) -> types. Only this battle's cast.
  const SPECIES = {
    "Tyranitar": ["Rock", "Dark"],
    "Iron Moth": ["Fire", "Poison"],
    "Decidueye": ["Grass", "Ghost"],
    "Zamazenta-Crowned": ["Fighting", "Steel"],
    "Mew": ["Psychic"],
    "Dedenne": ["Electric", "Fairy"],
    "Lanturn": ["Water", "Electric"],
    "Quaquaval": ["Water", "Fighting"],
    "Mimikyu": ["Ghost", "Fairy"],
    "Mimikyu-Busted": ["Ghost", "Fairy"],
    "Leavanny": ["Bug", "Grass"],
    "Drifblim": ["Ghost", "Flying"],
  };

  // move (slug) -> type. Every move that appears in this battle's log.
  const MOVES = {
    fireblast: "Fire", stoneedge: "Rock", leafstorm: "Grass", heavyslam: "Steel",
    bugbuzz: "Bug", thunderbolt: "Electric", scald: "Water", closecombat: "Fighting",
    playrough: "Fairy", knockoff: "Dark", airslash: "Flying", thunderwave: "Electric",
  };

  function mult1(att, def) {
    const c = CHART[att];
    if (!c) return 1;
    if (c.imm.includes(def)) return 0;
    if (c.sup.includes(def)) return 2;
    if (c.res.includes(def)) return 0.5;
    return 1;
  }
  // effectiveness of an attacking type against a (1- or 2-type) defender.
  function effectiveness(att, defTypes) {
    return (defTypes || []).reduce((m, d) => m * mult1(att, d), 1);
  }
  const slug = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

  window.__ARENA2D_DEX = {
    types: Object.keys(CHART),
    speciesTypes: (name) => SPECIES[name] || SPECIES[(name || "").split("-")[0]] || null,
    moveType: (mv) => MOVES[slug(mv)] || null,
    effectiveness,
    verdict: (m) =>
      m === 0 ? { k: "imm", t: "IMMUNE", x: "×0" }
      : m >= 4 ? { k: "sup", t: "4× SUPER", x: "×4" }
      : m >= 2 ? { k: "sup", t: "SUPER-EFFECTIVE", x: "×2" }
      : m <= 0.25 ? { k: "res", t: "DOUBLE-RESIST", x: "×¼" }
      : m <= 0.5 ? { k: "res", t: "RESISTED", x: "×½" }
      : { k: "neu", t: "NEUTRAL", x: "×1" },
  };
})();
