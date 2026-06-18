"""Unit + replay tests for the AccountStore (ADR-0013 D3/D6 substrate).

Two layers:
  - the store in isolation (link / owner_for / add_agent / agents_for, owner
    normalization, verbatim email storage);
  - the gateway boot replay folding durable account_link / account_enroll events
    back into ``gateway.accounts`` (the write-ahead-then-replay durability the
    membership + quota counters already have), including malformed-event
    resilience (a bad row must not crash boot).

Writers (device-flow login, /enroll/account) land in later PRs; this PR proves
the store + its durable read-side."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentdex_arena.account import AccountStore
from agentdex_arena.consent import ConsentAuthority
from agentdex_arena.gateway import ArenaGateway
from agentdex_engine.modules.arena import EventLog
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_OWNER = "yongbing.e.tang@gmail.com"
_GH = "12345678"


# ---- AccountStore in isolation ----


def test_link_and_owner_for_round_trip():
    store = AccountStore()
    store.link(_GH, _OWNER)
    assert store.owner_for(_GH) == _OWNER


def test_owner_for_unknown_github_is_none():
    assert AccountStore().owner_for("nope") is None


def test_link_stores_email_verbatim_but_is_case_insensitive_for_agents():
    """github->owner returns the email verbatim (case preserved); the
    owner->agents join keys on normalized owner so casing can't split it."""
    store = AccountStore()
    store.link(_GH, "Yongbing.E.Tang@GMail.com")
    assert store.owner_for(_GH) == "Yongbing.E.Tang@GMail.com"  # verbatim
    store.add_agent("Yongbing.E.Tang@GMail.com", "oppie")
    # a differently-cased owner resolves the SAME agent set
    assert store.agents_for("yongbing.e.tang@gmail.com") == ["oppie"]


def test_link_last_write_wins():
    store = AccountStore()
    store.link(_GH, "old@x.com")
    store.link(_GH, "new@x.com")
    assert store.owner_for(_GH) == "new@x.com"


def test_add_agent_join_is_sorted_and_deduped():
    store = AccountStore()
    store.add_agent(_OWNER, "zeta")
    store.add_agent(_OWNER, "alpha")
    store.add_agent(_OWNER, "alpha")  # idempotent
    assert store.agents_for(_OWNER) == ["alpha", "zeta"]


def test_agents_for_unknown_owner_is_empty():
    assert AccountStore().agents_for("stranger@x.com") == []


def test_two_owners_keep_separate_agent_sets():
    store = AccountStore()
    store.add_agent("a@x.com", "agent-a")
    store.add_agent("b@x.com", "agent-b")
    assert store.agents_for("a@x.com") == ["agent-a"]
    assert store.agents_for("b@x.com") == ["agent-b"]


def test_link_rejects_blank_github_id():
    with pytest.raises(ValueError, match="github_id"):
        AccountStore().link("  ", _OWNER)


def test_link_rejects_malformed_owner():
    with pytest.raises(ValueError):
        AccountStore().link(_GH, "")


def test_add_agent_rejects_blank_agent_name():
    with pytest.raises(ValueError, match="agent_name"):
        AccountStore().add_agent(_OWNER, "  ")


# ---- gateway boot replay ----


def _gateway(tmp_path: Path) -> ArenaGateway:
    authority = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex()
    )
    return ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
    )


def test_fresh_gateway_has_empty_account_store(tmp_path: Path):
    gw = _gateway(tmp_path)
    assert gw.accounts.owner_for(_GH) is None
    assert gw.accounts.agents_for(_OWNER) == []


def test_replay_hydrates_link_and_agents(tmp_path: Path):
    """Pre-seed the durable log, then a fresh gateway must rebuild the maps."""
    log = EventLog(tmp_path / "events.jsonl")
    log.append("account_link", {"github_id": _GH, "owner": _OWNER})
    log.append("account_enroll", {"owner": _OWNER, "agent_name": "oppie"})
    log.append("account_enroll", {"owner": _OWNER, "agent_name": "scout"})

    gw = _gateway(tmp_path)
    assert gw.accounts.owner_for(_GH) == _OWNER
    assert gw.accounts.agents_for(_OWNER) == ["oppie", "scout"]


def test_replay_link_last_write_wins(tmp_path: Path):
    log = EventLog(tmp_path / "events.jsonl")
    log.append("account_link", {"github_id": _GH, "owner": "old@x.com"})
    log.append("account_link", {"github_id": _GH, "owner": "new@x.com"})
    gw = _gateway(tmp_path)
    assert gw.accounts.owner_for(_GH) == "new@x.com"


def test_replay_skips_malformed_account_events_without_crashing(tmp_path: Path):
    """A malformed account event must be skipped (logged), not abort boot —
    same resilience the membership/quota replay has."""
    log = EventLog(tmp_path / "events.jsonl")
    log.append("account_link", {"github_id": _GH})  # missing owner
    log.append("account_link", {"owner": _OWNER})  # missing github_id
    log.append("account_enroll", {"owner": _OWNER})  # missing agent_name
    log.append("account_enroll", {"agent_name": "ghost"})  # missing owner
    log.append("account_link", {"github_id": "good", "owner": _OWNER})  # valid

    gw = _gateway(tmp_path)  # must not raise
    assert gw.accounts.owner_for("good") == _OWNER  # the one valid row survived
    assert gw.accounts.owner_for(_GH) is None  # the malformed link did not land
    assert gw.accounts.agents_for(_OWNER) == []  # malformed enrolls did not land
