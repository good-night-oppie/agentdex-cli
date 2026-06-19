---
title: "Genome-HUD Re-homing Implementation Plan"
status: active
owner: "@EdwardTang"
created: 2026-06-19
updated: 2026-06-19
type: reference
scope: docs/superpowers
layer: cross-cutting
cross_cutting: true
---

# GA-CORE-5 Genome-HUD Re-homing Implementation Plan


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FastAPI routes for agent team/genome detail queries and add comprehensive unit tests validating roster projection, quarantine exclusion, and fail-safe out-of-band capture.

**Architecture:** Mount GET `/me/agents/{agent_name}/team` and `/me/agents/{agent_name}/genome` to retrieve team hashes and out-of-band payloads. Expand the Pytest suite to verify sequential log traversal, quarantine, and capture failure handling.

**Tech Stack:** Python, FastAPI, Pytest, JSON/blake2b/sha256.

---

### Task 1: Mount API Endpoints in `gateway.py`

**Goal:** Register `/me/agents/{agent_name}/team` and `/me/agents/{agent_name}/genome` route handlers in FastAPI.

**Files:**
- Modify: `packages/agentdex_arena/src/agentdex_arena/gateway.py`

**Acceptance Criteria:**
- GET `/me/agents/{agent_name}/team` returns the correct team/build identity payload.
- GET `/me/agents/{agent_name}/genome` acts as an alias to `/me/agents/{agent_name}/team` and returns compatible alias keys (`genome_hash`, `genome_packed`).

**Verify:** `pytest packages/agentdex_arena/tests/test_me_dashboard.py`

**Steps:**

- [ ] **Step 1: Mount the `/me/agents/{agent_name}/team` and `/me/agents/{agent_name}/genome` routes in `create_app`**
  Add the following route handlers inside `create_app()` in `gateway.py` (after the `me_agents` route handler):
  ```python
    @app.get("/me/agents/{agent_name}/team")
    async def me_agent_team(
        agent_name: str,
        authorization: str | None = Header(default=None),
    ) -> dict:
        """GA-CORE-5: session-authed detail view for the agent's team/build identity (US-2.1)."""
        return gateway.me_agent_team(agent_name, _require_session(authorization))

    @app.get("/me/agents/{agent_name}/genome")
    async def me_agent_genome(
        agent_name: str,
        authorization: str | None = Header(default=None),
    ) -> dict:
        """Alias to /me/agents/{agent_name}/team for backward compatibility (US-2.1)."""
        res = gateway.me_agent_team(agent_name, _require_session(authorization))
        res["genome_hash"] = res["team_hash"]
        res["genome_packed"] = res["team_packed"]
        return res
```

- [ ] **Step 2: Update the `me_agent_team` method return signature to include genome keys**
  Add `genome_hash` and `genome_packed` to the returned dictionary in the `me_agent_team` method:
  ```python
        return {
            "agent_name": agent_name,
            "team_hash": latest_team_hash,
            "team_packed": team_packed,
            "genome_hash": latest_team_hash,
            "genome_packed": team_packed,
            "rating_context": {
                "rating": round(r.rating, 1),
                "rd": round(r.rd, 1),
                "games": r.games,
                "mixed_window": len(agent_rated_teams) > 1 or agent_has_uncaptured,
            },
            "recent_non_rated_note": recent_non_rated_note,
        }
```

- [ ] **Step 3: Run existing tests to verify compiling and syntax correctness**
  Run: `pytest packages/agentdex_arena/tests/test_me_dashboard.py`
  Expected: PASS

---

### Task 2: Implement Unit Tests in `test_me_dashboard.py`

**Goal:** Add test cases checking basic endpoints, mixed window flagging, quarantine retro-eligibility, and best-effort capture on error.

**Files:**
- Modify: `packages/agentdex_arena/tests/test_me_dashboard.py`

**Acceptance Criteria:**
- Test details endpoint works for both `/team` and `/genome` and returns correct rating/mixed_window status.
- Test `mixed_window` flags true when multiple team hashes or uncaptured battles are registered.
- Test quarantine exclusion properly disregards quarantined battles and rolls back to older eligible team hashes.
- Test that if out-of-band capture raises an exception, the battle still successfully starts and records a `team_hash` of `None`.

**Verify:** `pytest packages/agentdex_arena/tests/test_me_dashboard.py`

**Steps:**

- [ ] **Step 1: Write test cases at the end of `test_me_dashboard.py`**
  Append these test functions to `packages/agentdex_arena/tests/test_me_dashboard.py`:
  ```python
def test_me_agent_team_and_genome_details(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")
    # Simulate a battle begin with a captured team
    owner_norm = "eddie@oppie.xyz"
    import hashlib, json
    owner_dir = hashlib.blake2b(owner_norm.encode("utf-8"), digest_size=8).hexdigest()
    team_hash = hashlib.sha256(b"p1_team_blob").hexdigest()[:8]
    team_dir = gw.artifacts_dir / "teams" / owner_dir
    team_dir.mkdir(parents=True, exist_ok=True)
    (team_dir / f"{team_hash}.json").write_text(
        json.dumps({"owner": owner_norm, "team_hash": team_hash, "team_packed": "p1_team_blob"})
    )

    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b_detail",
            "lane": "rated",
            "visitor": "oppie",
            "opponent": "anchor",
            "team_hash": team_hash,
        },
    )
    gw.events.append(
        "battle_end",
        {
            "tenant_id": "tok",
            "battle_id": "b_detail",
            "lane": "rated",
            "winner": "oppie",
            "turns": 5,
            "input_log_blake2b16": "a" * 32,
        },
    )

    with _client(gw) as c:
        headers = _auth(gw)
        # Check team endpoint
        res_team = c.get("/me/agents/oppie/team", headers=headers)
        assert res_team.status_code == 200
        data_t = res_team.json()
        assert data_t["agent_name"] == "oppie"
        assert data_t["team_hash"] == team_hash
        assert data_t["team_packed"] == "p1_team_blob"
        assert data_t["rating_context"]["mixed_window"] is False

        # Check genome endpoint
        res_gen = c.get("/me/agents/oppie/genome", headers=headers)
        assert res_gen.status_code == 200
        data_g = res_gen.json()
        assert data_g["genome_hash"] == team_hash
        assert data_g["genome_packed"] == "p1_team_blob"


def test_me_agent_team_mixed_window(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")

    # 1. Multiple different teams -> mixed_window should be True
    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b1",
            "lane": "rated",
            "visitor": "oppie",
            "opponent": "anchor",
            "team_hash": "hash1111",
        },
    )
    gw.events.append("battle_end", {"tenant_id": "tok", "battle_id": "b1", "winner": "oppie", "turns": 2})

    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b2",
            "lane": "rated",
            "visitor": "oppie",
            "opponent": "anchor",
            "team_hash": "hash2222",
        },
    )
    gw.events.append("battle_end", {"tenant_id": "tok", "battle_id": "b2", "winner": "oppie", "turns": 2})

    with _client(gw) as c:
        headers = _auth(gw)
        res = c.get("/me/agents/oppie/team", headers=headers).json()
        assert res["rating_context"]["mixed_window"] is True


def test_me_agent_team_quarantine_exclusion(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")

    # Battle 1: clean rated battle
    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b1",
            "lane": "rated",
            "visitor": "oppie",
            "opponent": "anchor",
            "team_hash": "clean_hash",
        },
    )
    gw.events.append("battle_end", {"tenant_id": "tok", "battle_id": "b1", "winner": "oppie", "turns": 2})

    # Battle 2: dirty/quarantined rated battle
    gw.events.append(
        "battle_begin",
        {
            "tenant_id": "tok",
            "battle_id": "b2",
            "lane": "rated",
            "visitor": "oppie",
            "opponent": "anchor",
            "team_hash": "dirty_hash",
        },
    )
    gw.events.append("battle_end", {"tenant_id": "tok", "battle_id": "b2", "winner": "oppie", "turns": 2})
    gw.events.append("quarantine", {"battle_id": "b2", "reason": "collusion"})

    with _client(gw) as c:
        headers = _auth(gw)
        res = c.get("/me/agents/oppie/team", headers=headers).json()
        # The latest team hash should fall back to the clean one, ignoring dirty_hash
        assert res["team_hash"] == "clean_hash"


def test_me_agent_team_capture_failure_fail_safe(tmp_path):
    gw = _gateway(tmp_path)
    gw.accounts.add_agent(_OWNER, "oppie")

    # Mock artifacts_dir to raise error on write/mkdir to simulate write failure
    original_artifacts_dir = gw.artifacts_dir
    # We cause a write error by making the teams directory a file
    (gw.artifacts_dir).mkdir(parents=True, exist_ok=True)
    (gw.artifacts_dir / "teams").write_text("not_a_directory")

    # Starting a battle should NOT fail or raise 500
    # Simulate the request flow
    from types import SimpleNamespace
    req = SimpleNamespace(
        visitor_name="oppie",
        opponent="anchor",
        lane="rated",
        team="p1_team_blob_that_fails_capture",
    )
    import asyncio
    loop = asyncio.get_event_loop()
    
    # We call the internal _run_battle_begin to verify it handles the exception safely
    battle_id = "fail_safe_battle"
    owner_norm = "eddie@oppie.xyz"
    sidecar = SimpleNamespace(visitor_side="p1", start=lambda: None)

    async def run_test():
        await gw._run_battle_begin(
            req=req,
            battle_id=battle_id,
            owner_norm=owner_norm,
            visitor="oppie",
            opponent="anchor",
            team="p1_team_blob_that_fails_capture",
            sidecar=sidecar,
        )

    loop.run_until_complete(run_test())

    # Restore artifacts_dir state just in case
    (gw.artifacts_dir / "teams").unlink()

    # Now verify the event log contains the battle begin with team_hash=None/null
    events = list(gw.events.iter_events())
    begin_event = next(e for e in events if e.get("type") == "battle_begin")
    assert begin_event["payload"]["team_hash"] is None
```

- [ ] **Step 2: Run pytest to verify all tests pass**
  Run: `pytest packages/agentdex_arena/tests/test_me_dashboard.py`
  Expected: All tests pass.
