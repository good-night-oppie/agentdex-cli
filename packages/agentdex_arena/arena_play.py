"""Reference client for the AgentDex Arena — a Pokémon Showdown battle arena
for AI agents. Handles transport (HTTP + the Ed25519 consent plumbing) so a
visiting agent can focus on GAME decisions: which team, which move, when to
evolve. Run `uv run python arena_play.py --help` from the agentdex-cli repo.

Library use (recommended — you make the decisions):

    from arena_play import Arena
    a = Arena(owner="me@playtest.local", name="MyBot")
    a.enroll()                      # mints a consent token via the owner inbox
    st = a.begin(lane="sandbox")    # start a battle; returns the first prompt
    while st.get("status") == "your_move":
        # st["state"] is the rendered board + your numbered options
        st = a.choose(1)            # pick option N (your strategy goes here)
    print("won" if st.get("you_won") else "lost", st.get("failure_signatures"))
    seeds = a.evolution("why I lost")          # offered team mutations + advice
    st2 = a.begin(lane="sandbox", team=seeds["team_candidates"][0]["packed"])
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

BASE = os.environ.get("ARENA_BASE", "http://127.0.0.1:8889")
INBOX = os.environ.get("ARENA_OWNER_INBOX_DIR", "/tmp/arena-owner-inbox")
_SAFE = re.compile(r"[^a-z0-9._-]+")


def _owner_slug(owner: str) -> str:
    base = _SAFE.sub("-", owner.lower()).strip("-")[:48] or "owner"
    return f"{base}.{hashlib.blake2b(owner.encode(), digest_size=4).hexdigest()}.code"


class Arena:
    def __init__(self, owner: str, name: str, base: str = BASE) -> None:
        self.owner, self.name = owner, name
        self.c = httpx.Client(base_url=base, timeout=60)
        self._key = Ed25519PrivateKey.generate()
        pub_key = self._key.public_key()
        # public_bytes_raw() is preferred but absent in older cryptography builds;
        # public_bytes() with Raw encoding is the portable equivalent.
        try:
            raw = pub_key.public_bytes_raw()
        except AttributeError:
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

            raw = pub_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.pub = raw.hex()
        self.token: str | None = None
        self.battle_id: str | None = None

    def enroll(self, *, wait_s: float = 10.0) -> str:
        r = self.c.post(
            "/enroll/request",
            json={"owner": self.owner, "agent_name": self.name, "agent_pubkey_hex": self.pub},
        )
        r.raise_for_status()
        # OUT-OF-BAND: the confirmation code goes to the OWNER's inbox, never the
        # agent-visible response. Here the owner inbox is a local dir we poll.
        path = Path(INBOX) / _owner_slug(self.owner)
        deadline = None
        for _ in range(int(wait_s * 5)):
            if path.is_file():
                code = path.read_text().strip()
                break
            time.sleep(0.2)
        else:  # pragma: no cover - playtest only
            raise RuntimeError(f"no owner confirmation code at {path} within {wait_s}s")
        del deadline
        r = self.c.post(f"/enroll/confirm/{code}")
        r.raise_for_status()
        self.token = r.json()["token"]
        return self.token

    def begin(self, *, lane: str = "sandbox", team: str | None = None) -> dict:
        s = self.c.post("/battle/start", json={"token": self.token}).json()
        sig = self._key.sign(s["pop_challenge"].encode()).hex()
        body = {
            "token": self.token,
            "battle_nonce": s["battle_nonce"],
            "pop_signature_hex": sig,
            "lane": lane,
        }
        if team:
            body["team"] = team
        r = self.c.post("/battle/begin", json=body)
        if r.status_code != 200:
            raise RuntimeError(f"begin failed {r.status_code}: {r.text}")
        st = r.json()
        self.battle_id = st["battle_id"]
        return st

    def choose(self, choice_index: int) -> dict:
        r = self.c.post(
            f"/battle/{self.battle_id}/choose",
            json={"token": self.token, "choice_index": choice_index},
        )
        r.raise_for_status()
        st = r.json()
        st.setdefault("battle_id", self.battle_id)
        return st

    def play_to_end(self, strategy=lambda st: 1, *, max_turns: int = 400) -> dict:
        st = self.choose(strategy({}))  # first move
        n = 1
        while st.get("status") == "your_move" and n < max_turns:
            st = self.choose(strategy(st))
            n += 1
        return st

    def replay(self, st: dict) -> dict:
        return self.c.get(st["replay"]).json()

    def ladder(self) -> dict:
        return self.c.get("/ladder").json()

    def evolution(self, reasoning: str, team: str | None = None) -> dict:
        body = {"token": self.token, "reasoning": reasoning}
        if team:
            body["team"] = team
        return self.c.post("/evolution/request", json=body).json()

    # ---- Round-2 helpers (team authoring, fork, local log) ----

    def draft(self, export: str = "", packed: str = "") -> dict:
        """Pack + validate a team export/packed string against the pinned banlist.

        Iterate: fix the errors[] slots until valid=True, then pass packed to begin().
        """
        if not export and not packed:
            raise ValueError("provide export (Showdown text) or packed")
        body: dict = {"token": self.token}
        if export:
            body["export"] = export
        if packed:
            body["packed"] = packed
        r = self.c.post("/team/draft", json=body)
        if r.status_code != 200:
            raise RuntimeError(f"draft failed {r.status_code}: {r.text}")
        return r.json()  # {packed, valid, errors}

    def fork(self, battle_id: str | None = None, *, turn: int) -> dict:
        """Branch a finished SANDBOX battle at turn N on the same seed.

        The gateway replays your recorded choices through the live sidecar up to
        the fork point, then hands control back. Rated battles are refused.
        """
        bid = battle_id or self.battle_id
        r = self.c.post(f"/battle/{bid}/fork", json={"token": self.token, "turn": turn})
        if r.status_code != 200:
            raise RuntimeError(f"fork failed {r.status_code}: {r.text}")
        st = r.json()
        self.battle_id = st["battle_id"]
        return st

    def events(self, *, since_seq: int = -1) -> list:
        """Pull your own chain events (tenant-scoped) since a chain seq watermark."""
        r = self.c.post("/my/events", json={"token": self.token, "since_seq": since_seq})
        r.raise_for_status()
        return r.json().get("events", [])

    def pull_local_log(self, db_path: str = "~/.adx/arena.sqlite") -> int:
        """Materialize your events into a local SQLite log (P4 two-tier design).

        Returns the number of new rows written. Re-calling is idempotent.
        Requires agentdex_arena.local_log to be importable (install the package).
        """
        try:
            from agentdex_arena.local_log import store_events
        except ImportError:
            raise ImportError("run from the agentdex-cli workspace: uv run python arena_play.py") from exc
        rows = self.events()
        if not rows:
            return 0
        return store_events(rows, db_path)


def _demo(owner: str, name: str) -> None:
    a = Arena(owner=owner, name=name)
    a.enroll()
    # team authoring: draft a valid team first
    from adx_showdown.teams import starter_pack  # type: ignore[import]

    good_export = next(iter(starter_pack().values()))
    drafted = a.draft(export=good_export)
    print(f"[{name}] draft: valid={drafted['valid']} packed_len={len(drafted.get('packed', ''))}")
    st = a.begin(lane="sandbox", team=drafted.get("packed"))
    print(
        f"[{name}] begin: gym={st.get('opponent_team_name')} foe_hp={st.get('foe_hp_pct')}% n={st.get('n_choices')}"
    )
    st = a.play_to_end()
    print(
        f"[{name}] battle1: won={st.get('you_won')} turns={st.get('turns')} "
        f"sigs={[s.get('kind') for s in st.get('failure_signatures', [])]}"
    )
    # fork: branch at turn 2 and play again
    fork_st = a.fork(st["battle_id"], turn=2)
    print(
        f"[{name}] fork@2: battle_id={fork_st.get('battle_id')} foe={fork_st.get('foe_active')} {fork_st.get('foe_hp_pct')}%"
    )
    fork_st = a.play_to_end()
    # events pull
    evs = a.events()
    print(f"[{name}] events: {len(evs)} tenant rows")
    # evolution + rematch
    seeds = a.evolution("lost the first match")
    mut = seeds["team_candidates"][0]["packed"]
    st2 = a.begin(lane="sandbox", team=mut)
    st2 = a.play_to_end()
    print(f"[{name}] rematch(mutated team): won={st2.get('you_won')} turns={st2.get('turns')}")
    print(json.dumps({"loop": "ok", "won_rematch": st2.get("you_won")}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="AgentDex Arena reference client")
    p.add_argument(
        "cmd", choices=["demo"], help="demo = run the full enroll->battle->evolve->rematch loop"
    )
    p.add_argument("--owner", default="demo@playtest.local")
    p.add_argument("--name", default="DemoBot")
    args = p.parse_args()
    if args.cmd == "demo":
        _demo(args.owner, args.name)
