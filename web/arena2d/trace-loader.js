/* trace-loader.js — PS-style, endpoint-aware loader for the arena2d viewer.
 *
 * WHY THIS EXISTS:
 *   data.js ships a BAKED, file://-safe projection of one real ReasoningTrace and
 *   sets window.__ARENA2D_DATA as the fallback. This loader lets the SAME page run
 *   against a live arena endpoint without giving up that offline-first guarantee.
 *
 * CONTRACT:
 *   - The four engine scripts (dex.js, battle.js, mind.js, anim.js) MUST run only
 *     AFTER window.__ARENA2D_DATA is finalized — anim.js reads it at load time.
 *   - So index.html loads:  data.js  (baked fallback, sets __ARENA2D_DATA)
 *                           trace-loader.js  (this file — maybe overrides, then boots)
 *     and this file is the SOLE injector of the engine scripts.
 *
 * MODES:
 *   - No ?trace=<url>  -> use the baked data.js data, just boot the engine.
 *   - ?trace=<url>     -> fetch a Pokemon-Showdown-replay-shaped JSON doc, convert it
 *                         into __ARENA2D_DATA, then boot. ANY failure is swallowed and
 *                         the baked data.js data is kept (graceful degradation).
 *
 * file://-safe: the fetch() path runs ONLY when ?trace= is present, so opening the
 * page off the filesystem (no query) never triggers a network request.
 */
(function () {
  "use strict";

  // The engine scripts, in their REQUIRED load order. dex.js (type chart) before
  // battle.js (helpers) before mind.js (panel) before anim.js (driver, reads data).
  var ENGINE = ["dex.js", "battle.js", "mind.js", "anim.js"];

  // Sequentially inject <script> tags, each chaining the next on load, so order is
  // deterministic (defer/async would not guarantee it).
  function bootEngine() {
    var i = 0;
    (function next() {
      if (i >= ENGINE.length) return;
      var s = document.createElement("script");
      s.src = ENGINE[i++];
      s.onload = next;
      s.onerror = next; // keep going; a missing optional script shouldn't wedge boot
      document.body.appendChild(s);
    })();
  }

  // Convert a PS-replay-shaped doc into the __ARENA2D_DATA the engine expects.
  //   { log: "<newline-joined protocol>", decisions:[{move,rationale,considered:[{move,why_not}]}] }
  // ->{ LOG: [...protocol lines...], RATIONALES: [{move,rationale,considered:[{move,why_not}]}] }
  function toArenaData(doc) {
    var log = typeof doc.log === "string" ? doc.log : "";
    var decisions = Array.isArray(doc.decisions) ? doc.decisions : [];
    return {
      LOG: log.split("\n").filter(Boolean),
      RATIONALES: decisions.map(function (d) {
        return {
          move: d.move,
          rationale: d.rationale,
          considered: (d.considered || []).map(function (c) {
            return { move: c.move, why_not: c.why_not };
          }),
        };
      }),
    };
  }

  // Read ?trace=<url> from the page URL.
  var traceUrl = null;
  try {
    traceUrl = new URLSearchParams(window.location.search).get("trace");
  } catch (e) {
    traceUrl = null;
  }

  if (!traceUrl) {
    // No endpoint requested — keep the baked data.js data and boot immediately.
    bootEngine();
    return;
  }

  // Endpoint requested — try to override __ARENA2D_DATA, but NEVER let a failure
  // block the viewer: on any error we fall through to the baked data and boot anyway.
  fetch(traceUrl)
    .then(function (r) {
      if (!r.ok) throw new Error("trace fetch failed: " + r.status);
      return r.json();
    })
    .then(function (doc) {
      var data = toArenaData(doc);
      if (data.LOG.length) {
        window.__ARENA2D_DATA = data; // override the baked fallback
      }
    })
    .catch(function () {
      // Swallow: keep the baked data.js data exactly as-is.
    })
    .finally(function () {
      bootEngine(); // FINALLY boot the engine, with whichever data won.
    });
})();
