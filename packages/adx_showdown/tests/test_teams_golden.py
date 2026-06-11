"""Phase-A3 — starter pack validation (F3) + golden battle fixtures (A2).

Criteria:
- all committed starter teams pass validate-team against the PINNED
  pokemon-showdown version (ROADMAP criterion 4)
- recorded golden inputLogs re-simulate to identical outcomes, AND a fresh
  run from (seed, policy seeds) reproduces the inputLog byte-identically
  (ROADMAP criterion 2; no network)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from adx_showdown.sidecar import Sidecar, sidecar_available
from adx_showdown.sim import replay_input_log, run_battle, seeded_random_policy
from adx_showdown.teams import starter_pack, validate_starter_pack

pytestmark = pytest.mark.skipif(
    sidecar_available() is not None, reason=str(sidecar_available())
)

GOLDEN_DIR = Path(__file__).resolve().parents[3] / "tests" / "golden" / "arena"
GOLDEN_FILES = sorted(GOLDEN_DIR.glob("battle_*.json"))


def test_starter_pack_has_at_least_12_teams():
    assert len(starter_pack()) >= 12


def test_starter_pack_all_teams_validate_gen9ou():
    async def _run():
        async with Sidecar() as sc:
            return await validate_starter_pack(sc)

    results = asyncio.run(_run())
    failures = {r.name: r.errors for r in results if not r.valid}
    print(f"\nSTARTER_PACK_VALIDATION: {len(results) - len(failures)}/{len(results)} valid")
    assert not failures, f"invalid starter teams: {failures}"


def test_broken_team_yields_structured_errors():
    """The visitor repair loop depends on per-set error strings."""
    broken = (
        "Volcarona @ Heavy-Duty Boots\n"
        "Ability: Flame Body\n"
        "EVs: 252 SpA / 4 SpD / 252 Spe\n"
        "Timid Nature\n"
        "- Quiver Dance\n- Flamethrower\n- Bug Buzz\n- Gigaton Hammer\n"
    )

    async def _run():
        async with Sidecar() as sc:
            from adx_showdown.teams import pack_team, validate_team

            packed = await pack_team(sc, broken)
            return await validate_team(sc, packed)

    valid, errors = asyncio.run(_run())
    assert not valid
    assert errors and all(isinstance(e, str) and e for e in errors)


@pytest.mark.parametrize("fixture_path", GOLDEN_FILES, ids=lambda p: p.stem)
def test_golden_inputlog_resimulates_identically(fixture_path: Path):
    data = json.loads(fixture_path.read_text())
    digest = hashlib.blake2b("\n".join(data["input_log"]).encode(), digest_size=16).hexdigest()
    assert digest == data["input_log_blake2b16"], "fixture file corrupted"

    async def _run():
        async with Sidecar() as sc:
            return await replay_input_log(
                sc, battle_id=f"replay-{fixture_path.stem}", input_log=data["input_log"]
            )

    replayed = asyncio.run(_run())
    assert replayed.winner == data["winner"]
    assert replayed.turns == data["turns"]


@pytest.mark.parametrize("fixture_path", GOLDEN_FILES, ids=lambda p: p.stem)
def test_golden_fresh_run_reproduces_inputlog(fixture_path: Path):
    """Same seed + same policies ⇒ byte-identical inputLog (full determinism)."""
    data = json.loads(fixture_path.read_text())

    async def _run():
        async with Sidecar() as sc:
            return await run_battle(
                sc,
                battle_id=f"fresh-{fixture_path.stem}",
                format_id=data["format"],
                p1_name=data["p1_name"],
                p2_name=data["p2_name"],
                p1_policy=seeded_random_policy(data["policy_seeds"]["p1"]),
                p2_policy=seeded_random_policy(data["policy_seeds"]["p2"]),
                seed=data["seed"],
                p1_team=data["p1_team"],
                p2_team=data["p2_team"],
            )

    fresh = asyncio.run(_run())
    assert fresh.winner == data["winner"]
    assert fresh.turns == data["turns"]
    assert fresh.input_log == data["input_log"], "inputLog must reproduce byte-identically"
