"""Account store — the ``github_id ↔ owner`` link and ``account → agents`` join
that back the ADR-0013 onboarding (D3/D6).

Two maps, both rebuilt at boot from the durable EventLog (the same
write-ahead-then-replay discipline as ``membership_grant`` / ``quota_spend``):

  - ``github_id → owner email`` — written when a human completes device-flow
    login (D2 ``/auth/device/poll``); lets a returning login resolve to the
    SAME verified email (so memberships + quota stay single-keyed per human).
  - ``owner → {agent_name, …}`` — written when an account enrolls an agent (D3
    ``/enroll/account``); this is the account→agents join ``adx status`` reads
    (D6) to list a human's agents and their per-agent budgets.

Owner keying matches the rest of the arena: the ``owner → agents`` join keys on
``_normalize_owner`` (NFKC + strip + lowercase) so it agrees with the
quota/membership keys regardless of the email's casing, while the
``github_id → owner`` map stores the email VERBATIM (that is the value the
session token + account records carry; normalization is a key-time concern, not
a storage one).

This module is intentionally storage-only — no signing, no HTTP. The writers
(device-flow login, account-enroll) live in the gateway and append the durable
event *before* mutating this store, so a crash can never leave a token issued
for a link this store does not know.
"""

from __future__ import annotations

from collections.abc import Mapping

from agentdex_arena.consent import _normalize_owner


class AccountStore:
    """In-memory account maps, hydrated from the EventLog at boot.

    Not thread-safe by itself; the gateway mutates it from the asyncio event
    loop (single-threaded) under the same discipline as ``_registered``.
    """

    def __init__(self) -> None:
        self._owner_by_github: dict[str, str] = {}
        self._agents_by_owner: dict[str, dict[str, dict[str, int] | None]] = {}

    # ---- github_id <-> owner email ----

    def link(self, github_id: str, owner: str) -> None:
        """Bind a GitHub identity to its verified owner email (last-write-wins).

        ``owner`` is validated via ``_normalize_owner`` (fail-closed on empty /
        control-char / over-long) but stored VERBATIM — the map returns the
        email a fresh session token should carry. Raises ``ValueError`` (from
        ``_normalize_owner``) on a malformed owner; the caller appends the
        durable event only after this returns, so a bad value reserves nothing.
        """
        if not isinstance(github_id, str) or not github_id.strip():
            raise ValueError("github_id required")
        _normalize_owner(owner)  # validate; store original
        self._owner_by_github[github_id] = owner

    def owner_for(self, github_id: str) -> str | None:
        """The verified email previously linked to this GitHub id, or None."""
        return self._owner_by_github.get(github_id)

    # ---- owner -> agents join (D6 /status) ----

    @staticmethod
    def _quota_snapshot(quotas: Mapping[str, object]) -> dict[str, int]:
        snap: dict[str, int] = {}
        for scope, cap in quotas.items():
            if not isinstance(scope, str) or not scope.strip():
                raise ValueError("quota scope required")
            if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
                raise ValueError(f"quota cap for {scope!r} must be a non-negative int")
            snap[scope] = cap
        return snap

    def add_agent(
        self, owner: str, agent_name: str, *, quotas: Mapping[str, object] | None = None
    ) -> None:
        """Record that ``owner``'s account enrolled ``agent_name``. Keyed by
        normalized owner so it agrees with the quota/membership keys. Idempotent
        for legacy rows; newer rows may include the token's quota caps so
        ``adx status`` reports against the enrolled token rather than today's
        defaults."""
        if not isinstance(agent_name, str) or not agent_name.strip():
            raise ValueError("agent_name required")
        key = _normalize_owner(owner)
        agents = self._agents_by_owner.setdefault(key, {})
        if quotas is not None:
            agents[agent_name] = self._quota_snapshot(quotas)
        else:
            agents.setdefault(agent_name, None)

    def agents_for(self, owner: str) -> list[str]:
        """The account's enrolled agent names, sorted (stable for `adx status`
        rendering + contract tests). Empty list for an unknown owner."""
        return sorted(self._agents_by_owner.get(_normalize_owner(owner), {}))

    def agent_quotas_for(self, owner: str) -> dict[str, dict[str, int] | None]:
        """Per-agent quota snapshots from the enrollment token, keyed by agent.

        ``None`` means a legacy ``account_enroll`` row without quota metadata; the
        caller should fall back to the current default caps for that agent.
        """
        agents = self._agents_by_owner.get(_normalize_owner(owner), {})
        return {
            name: (dict(quotas) if quotas is not None else None) for name, quotas in agents.items()
        }


__all__ = ["AccountStore"]
