/* battle.js — helpers + data exposure for the arena2d 2D viewer.
 * The battle LOG (raw Showdown protocol) and RATIONALES (the agent's REAL per-decision
 * words from codex_decide, in order) come from data.js, generated from a live-codex
 * capture. This file is pure logic — no embedded data, no narration authored by us. */
(function () {
  "use strict";
  const D = window.__ARENA2D_DATA || { LOG: [], RATIONALES: [] };

  const F = (s) => s.split("|");
  const slug = (name) => String(name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  // spriteId: Showdown sprite filenames KEEP form hyphens (zamazenta-crowned.gif,
  // mimikyu-busted.gif) — only spaces/punctuation are stripped. slug() collapses
  // hyphens (good for rationale matching) but 404s every FORM sprite, so the CDN
  // URL must keep them.
  const spriteId = (name) => String(name || "").toLowerCase().replace(/[^a-z0-9-]/g, "");
  // animated in-battle sprites cover ALL gens (incl. gen9 forms); 404s fall back faded.
  const sprite = (name, back) =>
    "https://play.pokemonshowdown.com/sprites/" + (back ? "ani-back" : "ani") + "/" + spriteId(name) + ".gif";
  // HP as a percentage. YOUR side (p1) logs exact totals (e.g. 225/288); the foe
  // logs %-of-100. Convert any cur/max -> %, so the agent's own HP tracks the real
  // battle instead of staying at 100% until it faints. "fnt" == 0.
  function pubHp(v) {
    if (!v) return null;
    if (/fnt/.test(v)) return 0;
    const m = String(v).match(/^(\d+)\/(\d+)/);
    if (!m || +m[2] === 0) return null;
    return Math.max(0, Math.min(100, Math.round((+m[1] / +m[2]) * 100)));
  }
  const sideOf = (ref) => String(ref || "").slice(0, 2); // "p1a: Azumarill" -> "p1"
  const monOf = (ref) => (String(ref || "").split(": ")[1] || "").trim();
  const SIDE_LABEL = { p1: "Your agent", p2: "Rival" };

  window.__ARENA2D = {
    LOG: D.LOG || [],
    RATIONALES: D.RATIONALES || [],
    SIDE_LABEL,
    F,
    slug,
    sprite,
    pubHp,
    sideOf,
    monOf,
  };
})();
