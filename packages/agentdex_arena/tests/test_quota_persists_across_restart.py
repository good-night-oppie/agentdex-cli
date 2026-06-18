"""ADX-P2-004 — the per-UTC-day quota counter must survive a gateway restart.

Before this fix `ConsentAuthority.quota_used` lived only in memory and the boot
replay (which already rehydrates `register` / `membership_grant`) ignored quota,
so a restart reset every agent's daily cap — letting an owner exceed the daily
rated cap by triggering/awaiting a restart (ADR-0011 §3a/§5e adjacent).

The fix emits a durable `quota_spend` event on each successful spend (carrying
the exact day-stamped key the spend debited) and re-folds today's events into
`quota_used` at boot. These tests drive that path directly — no live sidecar
battle is needed to prove reconstruction, so the file is NOT sidecar-gated.
"""

from __future__ import annotations

import json

import pytest
from agentdex_arena.consent import ConsentAuthority, ConsentClaims, ConsentError
from agentdex_arena.gateway import ArenaGateway
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_NOW = 1_700_000_000.0  # fixed clock so the UTC day-bucket is deterministic


def _claims(*, owner: str = "eddie@oppie.xyz", agent_name: str = "QuotaBot") -> ConsentClaims:
    pubkey = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    return ConsentClaims(
        token_id="t" + "0" * 16,
        owner=owner,
        agent_name=agent_name,
        agent_pubkey_hex=pubkey,
        scopes=["enroll", "battle", "evolve", "badge_mint"],
        issued_at=_NOW - 1_000,
        expires_at=_NOW + 1_000_000,
        confirmed_via="test",
    )


def _gateway(tmp_path, *, now: float = _NOW) -> ArenaGateway:
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    authority = ConsentAuthority(signing_key_hex=signing, now=lambda: now)
    return ArenaGateway(
        authority=authority,
        events_path=tmp_path / "events.jsonl",
        artifacts_dir=tmp_path / "arena",
        notify_owner=lambda owner, code: None,
        now=lambda: now,
    )


# A gateway pair MUST share signing key so a token minted on gw1 verifies on gw2.
def _gateway_pair(tmp_path, *, now: float = _NOW) -> tuple[ArenaGateway, ArenaGateway]:
    """gw1 + a 'restarted' gw2 reading the SAME event log with a FRESH authority
    (empty quota_used) — exactly what a process restart looks like."""
    signing = Ed25519PrivateKey.generate().private_bytes_raw().hex()
    events_path = tmp_path / "events.jsonl"
    arts = tmp_path / "arena"

    def build() -> ArenaGateway:
        return ArenaGateway(
            authority=ConsentAuthority(signing_key_hex=signing, now=lambda: now),
            events_path=events_path,
            artifacts_dir=arts,
            notify_owner=lambda owner, code: None,
            now=lambda: now,
        )

    return build(), build  # gw1, and a builder for the post-restart gw2


# --------------------------------------------------------------------------- #
# unit: spend_quota now returns the debited key + scope-conditional keying
# --------------------------------------------------------------------------- #


def test_spend_quota_returns_debited_key():
    auth = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex(),
        now=lambda: _NOW,
    )
    claims = _claims()
    remaining, key = auth.spend_quota(claims, scope="battle")
    assert remaining == claims.quotas["battle"] - 1
    # battle keys on normalized owner; key is exactly what the live counter used
    assert key == auth.quota_key(claims, scope="battle")
    assert key.startswith("eddie@oppie.xyz:battle:")
    assert auth.quota_used[key] == 1


def test_quota_key_scope_conditional():
    auth = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex(),
        now=lambda: _NOW,
    )
    claims = _claims(owner="OWNER@X.com", agent_name="AgentA")
    # battle -> normalized owner (ADR-0011 §3b/§5e); others -> agent_name
    assert auth.quota_key(claims, scope="battle").startswith("owner@x.com:battle:")
    assert auth.quota_key(claims, scope="badge_mint").startswith("AgentA:badge_mint:")
    assert auth.quota_key(claims, scope="evolve").startswith("AgentA:evolve:")


def test_replay_quota_spend_today_only():
    auth = ConsentAuthority(
        signing_key_hex=Ed25519PrivateKey.generate().private_bytes_raw().hex(),
        now=lambda: _NOW,
    )
    today_key = auth.quota_key(_claims(), scope="battle")
    stale_key = "eddie@oppie.xyz:battle:20000101"  # a prior UTC day
    auth.replay_quota_spend(today_key)
    auth.replay_quota_spend(stale_key)
    auth.replay_quota_spend(today_key)
    assert auth.quota_used.get(today_key) == 2, "today's key folds in"
    assert stale_key not in auth.quota_used, "a prior-day key self-drops"


# --------------------------------------------------------------------------- #
# the headline: a daily cap survives a restart (no reset-on-restart bypass)
# --------------------------------------------------------------------------- #


def test_rated_battle_quota_survives_gateway_restart(tmp_path):
    gw1, build_gw2 = _gateway_pair(tmp_path)
    claims = _claims()
    cap = claims.quotas["battle"]

    # Exhaust the daily battle cap on gw1, recording each spend durably exactly
    # as the gateway's rated /battle/begin path does.
    for _ in range(cap):
        _, key = gw1.authority.spend_quota(claims, scope="battle")
        gw1._record_quota_spend(key)
    with pytest.raises(ConsentError):
        gw1.authority.spend_quota(claims, scope="battle")  # cap hit pre-restart

    # RESTART: a fresh authority (empty quota_used) replays the event log.
    gw2 = build_gw2()
    # The cap is rehydrated — a post-restart spend STILL 403s (the bug was that
    # this used to succeed because quota_used reset to {}).
    with pytest.raises(ConsentError):
        gw2.authority.spend_quota(claims, scope="battle")
    assert gw2.authority.quota_used == gw1.authority.quota_used


def test_badge_and_evolve_quota_survive_restart(tmp_path):
    gw1, build_gw2 = _gateway_pair(tmp_path)
    claims = _claims(agent_name="MultiScopeBot")

    for scope in ("badge_mint", "evolve"):
        cap = claims.quotas[scope]
        for _ in range(cap):
            _, key = gw1.authority.spend_quota(claims, scope=scope)
            gw1._record_quota_spend(key)

    gw2 = build_gw2()
    for scope in ("badge_mint", "evolve"):
        with pytest.raises(ConsentError):
            gw2.authority.spend_quota(claims, scope=scope)
    assert gw2.authority.quota_used == gw1.authority.quota_used


def test_quota_spend_event_payload_shape(tmp_path):
    gw1 = _gateway(tmp_path)
    claims = _claims()
    _, key = gw1.authority.spend_quota(claims, scope="battle")
    gw1._record_quota_spend(key)

    rows = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    quota_rows = [r for r in rows if r.get("type") == "quota_spend"]
    assert len(quota_rows) == 1
    payload = quota_rows[0]["payload"]
    assert payload["key"] == key
    # key shape: "<owner-or-agent>:<scope>:<YYYYMMDD>"
    owner_part, scope_part, day_part = key.rsplit(":", 2)
    assert scope_part == "battle"
    assert len(day_part) == 8 and day_part.isdigit()
    assert isinstance(payload["spent_at"], int | float)


# --------------------------------------------------------------------------- #
# robustness: stale-day drop, malformed-event tolerance, best-effort append
# --------------------------------------------------------------------------- #


def test_stale_prior_day_quota_spend_not_hydrated(tmp_path):
    """A quota_spend row whose key ends in a PRIOR UTC day must not count toward
    today's cap after a restart — it self-drops (a fresh quota, not a lockout)."""
    gw1, build_gw2 = _gateway_pair(tmp_path)
    claims = _claims()
    # one legitimate spend today
    _, today_key = gw1.authority.spend_quota(claims, scope="battle")
    gw1._record_quota_spend(today_key)
    # plus a hand-written stale (yesterday) event straight into the log
    stale_key = "eddie@oppie.xyz:battle:20000101"
    gw1.events.append("quota_spend", {"key": stale_key, "spent_at": _NOW - 86_400})

    gw2 = build_gw2()
    assert gw2.authority.quota_used.get(today_key) == 1
    assert stale_key not in gw2.authority.quota_used


def test_boot_replay_skips_malformed_quota_spend(tmp_path):
    """A malformed quota_spend row (missing/non-string key) between valid ones
    must not abort the replay loop — the surrounding defensive try/except logs
    and skips it, and the valid keys still hydrate."""
    gw1, build_gw2 = _gateway_pair(tmp_path)
    claims = _claims()
    _, good_key = gw1.authority.spend_quota(claims, scope="battle")
    gw1._record_quota_spend(good_key)
    gw1.events.append("quota_spend", {"spent_at": _NOW})  # no 'key' -> malformed
    gw1.events.append("quota_spend", {"key": 12345, "spent_at": _NOW})  # non-string

    gw2 = build_gw2()  # must not raise
    assert gw2.authority.quota_used.get(good_key) == 1


def test_quota_spend_append_failure_does_not_fail_request(tmp_path):
    """Class B best-effort: a failed quota_spend append must NOT propagate — the
    in-memory debit already committed (and a rated battle is already live), so a
    500 here would be worse than the bug. Pins the best-effort posture."""
    gw1 = _gateway(tmp_path)

    def _boom(type_, payload):
        raise RuntimeError("disk full")

    gw1.events.append = _boom  # type: ignore[assignment]
    # Must swallow the append failure and return normally.
    gw1._record_quota_spend("eddie@oppie.xyz:battle:20231114")
