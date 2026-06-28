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
 *   - No ?trace=<url>  -> use the baked data.js demo data, just boot the engine.
 *   - ?trace=<url>     -> fetch a Pokemon-Showdown-replay-shaped JSON doc and install it
 *                         as __ARENA2D_DATA, then boot. A live ?trace= URL ALWAYS wins
 *                         over the baked demo — even an EMPTY log — so opening the printed
 *                         --ui URL before the first turn (or after a stream failure that
 *                         leaves the buffer empty) NEVER silently renders the unrelated
 *                         baked demo battle. An empty live log shows a "waiting" state and
 *                         a fetch/parse failure shows an error; reloading re-fetches the
 *                         /live.json snapshot (PR #614 review).
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

  // Decide how a live ?trace= doc should render. A non-empty log boots the engine to
  // animate the real battle; an EMPTY log resolves to "waiting" (the live battle has no
  // frames yet, or the stream failed leaving the buffer empty) — which the caller renders
  // as a waiting state instead of falling back to the unrelated baked demo. Pure, so the
  // empty-vs-demo decision is unit-testable without a DOM (PR #614 review).
  function decideLiveRender(doc) {
    var data = toArenaData(doc);
    return { data: data, action: data.LOG.length ? "boot" : "waiting" };
  }

  // Node/test entry point: export the pure helpers and skip the browser boot below
  // (which touches window/document/fetch). In the browser `module` is undefined, so this
  // is a no-op and execution continues into the loader proper.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { toArenaData: toArenaData, decideLiveRender: decideLiveRender };
    return;
  }

  // Show a one-line status message in the arena banner (the live battle isn't animating).
  function showMessage(text) {
    var banner = document.getElementById("banner");
    if (banner) banner.textContent = text;
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

  // Endpoint requested — a live ?trace= doc ALWAYS replaces the baked demo so the viewer
  // can never silently render an unrelated battle. A non-empty log boots the engine; an
  // empty log or a fetch/parse failure shows an explicit status instead of the demo.
  fetch(traceUrl)
    .then(function (r) {
      if (!r.ok) throw new Error("trace fetch failed: " + r.status);
      return r.json();
    })
    .then(function (doc) {
      var decided = decideLiveRender(doc);
      window.__ARENA2D_DATA = decided.data; // live trace wins over the baked demo, always
      if (decided.action === "waiting") {
        // No frames yet (or the stream failed leaving the buffer empty): show a waiting
        // state rather than booting on an empty/demo log. Reloading re-fetches /live.json.
        showMessage("Waiting for the first turn… reload to refresh.");
        return;
      }
      bootEngine();
    })
    .catch(function () {
      // Live endpoint unreachable or malformed: surface an error, never the demo battle.
      showMessage("Live battle data unavailable — reload to retry.");
    });
})();
