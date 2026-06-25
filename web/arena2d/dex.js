/* dex.js — DERIVED reference data (NOT the agent's words, NOT the battle log).
 * The universal Gen-9 type CHART + the species/move typings for the Pokémon in THIS
 * battle, so the mind readout can ground the agent's claims ("resists Grass", "super-
 * effective") in the real chart. SOURCED from pokemon-showdown's own dex data (the same
 * engine the arena runs) — regenerate via tools/build_arena2d_dex.cjs; do not hand-edit. */
(function () {
  "use strict";
  const CHART = {
    "Normal": {
      "sup": [],
      "res": [
        "Rock",
        "Steel"
      ],
      "imm": [
        "Ghost"
      ]
    },
    "Fire": {
      "sup": [
        "Grass",
        "Ice",
        "Bug",
        "Steel"
      ],
      "res": [
        "Fire",
        "Water",
        "Rock",
        "Dragon"
      ],
      "imm": []
    },
    "Water": {
      "sup": [
        "Fire",
        "Ground",
        "Rock"
      ],
      "res": [
        "Water",
        "Grass",
        "Dragon"
      ],
      "imm": []
    },
    "Electric": {
      "sup": [
        "Water",
        "Flying"
      ],
      "res": [
        "Electric",
        "Grass",
        "Dragon"
      ],
      "imm": [
        "Ground"
      ]
    },
    "Grass": {
      "sup": [
        "Water",
        "Ground",
        "Rock"
      ],
      "res": [
        "Fire",
        "Grass",
        "Poison",
        "Flying",
        "Bug",
        "Dragon",
        "Steel"
      ],
      "imm": []
    },
    "Ice": {
      "sup": [
        "Grass",
        "Ground",
        "Flying",
        "Dragon"
      ],
      "res": [
        "Fire",
        "Water",
        "Ice",
        "Steel"
      ],
      "imm": []
    },
    "Fighting": {
      "sup": [
        "Normal",
        "Ice",
        "Rock",
        "Dark",
        "Steel"
      ],
      "res": [
        "Poison",
        "Flying",
        "Psychic",
        "Bug",
        "Fairy"
      ],
      "imm": [
        "Ghost"
      ]
    },
    "Poison": {
      "sup": [
        "Grass",
        "Fairy"
      ],
      "res": [
        "Poison",
        "Ground",
        "Rock",
        "Ghost"
      ],
      "imm": [
        "Steel"
      ]
    },
    "Ground": {
      "sup": [
        "Fire",
        "Electric",
        "Poison",
        "Rock",
        "Steel"
      ],
      "res": [
        "Grass",
        "Bug"
      ],
      "imm": [
        "Flying"
      ]
    },
    "Flying": {
      "sup": [
        "Grass",
        "Fighting",
        "Bug"
      ],
      "res": [
        "Electric",
        "Rock",
        "Steel"
      ],
      "imm": []
    },
    "Psychic": {
      "sup": [
        "Fighting",
        "Poison"
      ],
      "res": [
        "Psychic",
        "Steel"
      ],
      "imm": [
        "Dark"
      ]
    },
    "Bug": {
      "sup": [
        "Grass",
        "Psychic",
        "Dark"
      ],
      "res": [
        "Fire",
        "Fighting",
        "Poison",
        "Flying",
        "Ghost",
        "Steel",
        "Fairy"
      ],
      "imm": []
    },
    "Rock": {
      "sup": [
        "Fire",
        "Ice",
        "Flying",
        "Bug"
      ],
      "res": [
        "Fighting",
        "Ground",
        "Steel"
      ],
      "imm": []
    },
    "Ghost": {
      "sup": [
        "Psychic",
        "Ghost"
      ],
      "res": [
        "Dark"
      ],
      "imm": [
        "Normal"
      ]
    },
    "Dragon": {
      "sup": [
        "Dragon"
      ],
      "res": [
        "Steel"
      ],
      "imm": [
        "Fairy"
      ]
    },
    "Dark": {
      "sup": [
        "Psychic",
        "Ghost"
      ],
      "res": [
        "Fighting",
        "Dark",
        "Fairy"
      ],
      "imm": []
    },
    "Steel": {
      "sup": [
        "Ice",
        "Rock",
        "Fairy"
      ],
      "res": [
        "Fire",
        "Water",
        "Electric",
        "Steel"
      ],
      "imm": []
    },
    "Fairy": {
      "sup": [
        "Fighting",
        "Dragon",
        "Dark"
      ],
      "res": [
        "Fire",
        "Poison",
        "Steel"
      ],
      "imm": []
    }
  };
  const SPECIES = {
    "Articuno": [
      "Ice",
      "Flying"
    ],
    "Blissey": [
      "Normal"
    ],
    "Bronzong": [
      "Steel",
      "Psychic"
    ],
    "Calyrex-Ice": [
      "Psychic",
      "Ice"
    ],
    "Eiscue": [
      "Ice"
    ],
    "Eiscue-Noice": [
      "Ice"
    ],
    "Empoleon": [
      "Water",
      "Steel"
    ],
    "Lilligant": [
      "Grass"
    ],
    "Quagsire": [
      "Water",
      "Ground"
    ],
    "Quaquaval": [
      "Water",
      "Fighting"
    ],
    "Shiftry": [
      "Grass",
      "Dark"
    ],
    "Talonflame": [
      "Fire",
      "Flying"
    ],
    "Wyrdeer": [
      "Normal",
      "Psychic"
    ]
  };
  const MOVES = {
    "Body Press": "Fighting",
    "Brave Bird": "Flying",
    "Close Combat": "Fighting",
    "Earthquake": "Ground",
    "Freeze-Dry": "Ice",
    "Glacial Lance": "Ice",
    "Ice Spinner": "Ice",
    "Iron Head": "Steel",
    "Knock Off": "Dark",
    "Leaf Storm": "Grass",
    "Megahorn": "Bug",
    "Petal Dance": "Grass",
    "Seismic Toss": "Fighting",
    "Sucker Punch": "Dark",
    "U-turn": "Bug",
    "aquastep": "Water",
    "bellydrum": "Normal",
    "bravebird": "Flying",
    "closecombat": "Fighting",
    "earthquake": "Ground",
    "freezedry": "Ice",
    "icespinner": "Ice",
    "ironhead": "Steel",
    "knockoff": "Dark",
    "leafstorm": "Grass",
    "liquidation": "Water",
    "megahorn": "Bug",
    "psychicnoise": "Psychic",
    "roost": "Flying",
    "suckerpunch": "Dark",
    "surf": "Water",
    "thunderwave": "Electric",
    "uturn": "Bug",
    "willowisp": "Fire",
    "yawn": "Normal"
  };
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
    if (m === 0) return { k: "imm", x: "\u00d70", t: "IMMUNE" };
    if (m >= 4) return { k: "sup", x: "\u00d74", t: "4\u00d7 SUPER" };
    if (m >= 2) return { k: "sup", x: "\u00d72", t: "SUPER-EFFECTIVE" };
    if (m <= 0.25) return { k: "res", x: "\u00d7\u00bc", t: "DOUBLY RESISTED" };
    if (m <= 0.5) return { k: "res", x: "\u00d7\u00bd", t: "RESISTED" };
    return { k: "neu", x: "\u00d71", t: "NEUTRAL" };
  }
  window.__ARENA2D_DEX = { types: Object.keys(CHART), speciesTypes, moveType, effectiveness, verdict };
})();
