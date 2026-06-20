/*
 * live-source.js — the pluggable live frame source for the GA-BENE-2 viewer.
 *
 * The renderer never talks to a transport directly; it consumes frames from a
 * source object that mimics the SSE EventSource surface (onmessage + an "end"
 * listener). This gives us ONE wiring seam (LVC-01/02/03/19):
 *
 *   - MockLiveSource — replays projector frames on a timer (no backend); proves
 *     incremental per-seq rendering + the event:end -> replay swap entirely
 *     offline. This is what the fixture-driven reference demo uses.
 *   - SseLiveSource — the real GA-CORE-3 client. Picks the endpoint BY INTENT:
 *     a logged-in own-agent view opens the AUTHENTICATED owner stream
 *     (/me/battle/{id}/live, own-side fog-of-war); a third-party / shared link
 *     opens the PUBLIC spectator stream (/battle/{id}/live). It NEVER uses the
 *     public stream for the own-agent view (LVC-02/16). It is stubbed until
 *     GA-CORE-3 emits frames — wiring it is the one-line swap MockLiveSource
 *     stands in for.
 *
 * Both speak the same frame shape (LIVE_VIEWER_CONTRACT.md): each "message"
 * carries one frame {battle_id, turn, seq, side, lines, scene, ts_ms}; a final
 * "end" event carries {replay_url}.
 */
;(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) module.exports = factory();
  else root.LiveSource = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  // Minimal EventSource-like emitter (onmessage / addEventListener('end') / close).
  function Emitter() {
    this._listeners = { message: [], end: [], error: [] };
    this.onmessage = null;
  }
  Emitter.prototype.addEventListener = function (type, fn) {
    (this._listeners[type] || (this._listeners[type] = [])).push(fn);
  };
  Emitter.prototype._emit = function (type, detail) {
    if (type === "message" && typeof this.onmessage === "function") this.onmessage({ data: detail });
    for (const fn of this._listeners[type] || []) fn({ data: detail, detail });
  };

  /*
   * MockLiveSource — replay `frames` on a timer. Each tick emits the next frame
   * as a "message"; after the last, emits "end" with the replay url. Supports
   * pause()/resume() and a mid-stream connect that first flushes the buffered
   * backlog then streams live (LVC-04 backpressure shape).
   */
  function MockLiveSource(frames, opts) {
    Emitter.call(this);
    opts = opts || {};
    this.frames = frames.slice();
    this.intervalMs = opts.intervalMs == null ? 900 : opts.intervalMs; // demo pace (<2s, AC3)
    this.replayUrl = opts.replayUrl || "/replay/b_demo";
    this.startAt = opts.startAt || 0; // mid-battle join => backlog flush then live
    this._i = 0;
    this._timer = null;
    this._paused = false;
  }
  MockLiveSource.prototype = Object.create(Emitter.prototype);

  MockLiveSource.prototype.start = function () {
    // Backpressure (LVC-04): a client joining mid-battle first receives the
    // buffered frames [0..startAt], applied immediately, then streams live.
    for (; this._i < this.startAt && this._i < this.frames.length; this._i++) {
      this._emit("message", this.frames[this._i]);
    }
    this._tick();
    return this;
  };
  MockLiveSource.prototype._tick = function () {
    if (this._paused) return;
    if (this._i >= this.frames.length) {
      this._emit("end", { replay_url: this.replayUrl });
      return;
    }
    this._emit("message", this.frames[this._i++]);
    this._timer = setTimeout(() => this._tick(), this.intervalMs);
  };
  MockLiveSource.prototype.pause = function () {
    this._paused = true;
    if (this._timer) clearTimeout(this._timer);
  };
  MockLiveSource.prototype.resume = function () {
    if (!this._paused) return;
    this._paused = false;
    this._tick();
  };
  MockLiveSource.prototype.close = function () {
    this._paused = true;
    if (this._timer) clearTimeout(this._timer);
  };

  /*
   * endpointFor — the LVC-01/02/03 routing rule, isolated + unit-testable.
   * intent: "own" (a logged-in user's own agent) -> authenticated owner stream;
   *         "spectate" (third-party / shared link) -> public spectator stream.
   * The own-agent view MUST NOT use the public endpoint (it lacks own-side
   * hidden info and would fail fog-of-war).
   */
  function endpointFor(intent, battleId) {
    if (intent === "own") return { url: `/me/battle/${battleId}/live`, auth: true, side: "owner" };
    return { url: `/battle/${battleId}/live`, auth: false, side: "spectator" };
  }

  /*
   * SseLiveSource — the real GA-CORE-3 consumer. Owner streams use the backend's
   * Bearer session-token contract, which requires fetch + ReadableStream because
   * native EventSource cannot set Authorization. Public spectator streams can keep
   * native EventSource.
   */
  function SseLiveSource(battleId, intent, opts) {
    Emitter.call(this);
    opts = opts || {};
    this.battleId = battleId;
    this.endpoint = endpointFor(intent, battleId);
    this.sessionToken = opts.sessionToken || "";
    this._fetch = opts.fetch || (typeof fetch !== "undefined" ? fetch.bind(globalThis) : null);
    this._AbortController =
      opts.AbortController || (typeof AbortController !== "undefined" ? AbortController : null);
    this._abort = null;
    this._es = null;
    this._EventSource = opts.EventSource || (typeof EventSource !== "undefined" ? EventSource : null);
  }
  SseLiveSource.prototype = Object.create(Emitter.prototype);
  SseLiveSource.prototype.start = function () {
    if (this.endpoint.auth) return this._startBearerFetch();
    if (!this._EventSource) throw new Error("SseLiveSource: no EventSource (wire GA-CORE-3 first)");
    this._es = new this._EventSource(this.endpoint.url);
    this._es.onmessage = (ev) => this._emit("message", JSON.parse(ev.data));
    this._es.addEventListener("end", (ev) => this._emit("end", JSON.parse(ev.data)));
    this._es.onerror = (ev) => this._emit("error", ev);
    return this;
  };

  SseLiveSource.prototype._startBearerFetch = function () {
    if (!this.sessionToken) throw new Error("SseLiveSource: Bearer session token required");
    if (!this._fetch || !this._AbortController) {
      throw new Error("SseLiveSource: fetch streaming unavailable");
    }
    this._abort = new this._AbortController();
    this._fetch(this.endpoint.url, {
      headers: {
        Accept: "text/event-stream",
        Authorization: `Bearer ${this.sessionToken}`,
      },
      signal: this._abort.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`${this.endpoint.url}: HTTP ${res.status}`);
        if (!res.body || !res.body.getReader) throw new Error("SseLiveSource: no response stream");
        return this._readStream(res.body.getReader());
      })
      .catch((err) => {
        if (!this._abort || !this._abort.signal.aborted) this._emit("error", err);
      });
    return this;
  };

  SseLiveSource.prototype._readStream = async function (reader) {
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buf += decoder.decode(chunk.value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        this._dispatchSseBlock(block);
      }
    }
    buf += decoder.decode();
    if (buf.trim()) this._dispatchSseBlock(buf);
  };

  SseLiveSource.prototype._dispatchSseBlock = function (block) {
    let event = "message";
    const data = [];
    for (const raw of block.split(/\r?\n/)) {
      if (raw.startsWith("event:")) event = raw.slice(6).trim() || "message";
      else if (raw.startsWith("data:")) data.push(raw.slice(5).trimStart());
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n"));
    this._emit(event, payload);
  };

  SseLiveSource.prototype.close = function () {
    if (this._es) this._es.close();
    if (this._abort) this._abort.abort();
  };

  return { MockLiveSource, SseLiveSource, endpointFor, Emitter };
});
