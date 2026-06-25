"""Pluggable battle agents — the abstract decision seam.

An **Agent** is the policy plugged into :func:`codex_adapter.select_codex_move`:
given the harness + a serialized battle context, it proposes an action id (a move
id or a switch species), or ``None`` to abstain (the adapter then substitutes a
legal order). This is the abstract base that different decision backends inherit.

Why this exists (the "why ``codex_decide`` and not ``agent_decide``?" question):
historically the ONLY backend was the live openai/codex CLI, so the ``DecideFn``
was named ``codex_decide``. That name is the codex-SPECIFIC implementation, not
the generic seam. :class:`Agent` is the generic seam; ``codex_decide`` is now just
:class:`CodexAgent`'s body. New backends (other models, scripted policies) inherit
:class:`Agent` and implement :meth:`Agent.decide` instead of adding more free
functions. An :class:`Agent` instance is itself a :data:`~codex_adapter.DecideFn`
(via ``__call__``), so it is a drop-in for ``select_codex_move(decide=...)``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from adx_showdown.selfplay.codex_adapter import DecideFn

__all__ = ["Agent", "CodexAgent", "GreedyAgent", "agent_decide"]


class Agent(ABC):
    """A battle decision policy.

    Subclass and implement :meth:`decide`. Because :meth:`__call__` delegates to
    :meth:`decide`, an instance satisfies the :data:`~codex_adapter.DecideFn`
    contract and can be passed straight to
    ``select_codex_move(..., decide=my_agent)``.
    """

    #: short, stable backend id (used in logs / metrics / strategy routing)
    name: str = "agent"

    @abstractmethod
    def decide(self, harness: Any, ctx: Mapping[str, Any]) -> str | None:
        """Propose an action id (move id or switch species), or ``None`` to abstain.

        Legality is NOT gated here — ``select_codex_move`` is the single legality
        gate (it counts an illegal proposal and substitutes a legal order). Returning
        ``None`` means *abstain*, which is distinct from *proposed something illegal*.
        Implementations must never raise on a backend fault: catch and return
        ``None`` so a flaky backend can never crash a battle.
        """
        raise NotImplementedError

    def __call__(self, harness: Any, ctx: dict[str, Any]) -> str | None:
        return self.decide(harness, ctx)


class CodexAgent(Agent):
    """The live openai/codex CLI agent — the original ``codex_decide`` path.

    Delegates verbatim to :func:`codex_decide.codex_decide` (kept as the canonical
    implementation + back-compat export). ``run`` is the injectable CLI runner so
    unit tests never shell out.
    """

    name = "codex"

    def __init__(self, *, run: Any | None = None) -> None:
        self._run = run

    def decide(self, harness: Any, ctx: Mapping[str, Any]) -> str | None:
        # lazy import: keeps the subprocess/codex module off the default + test +
        # poke-env-free path (mirrors runner._resolve_agent's laziness).
        from adx_showdown.selfplay.codex_decide import codex_decide

        return codex_decide(harness, ctx, run=self._run)


class GreedyAgent(Agent):
    """The deterministic STAB/effectiveness greedy default — no subprocess, on-loop.

    The same policy ``select_codex_move`` falls back to when ``decide`` is ``None``;
    exposing it as an Agent lets callers select it explicitly (and demonstrates a
    second, zero-cost backend inheriting the same seam).
    """

    name = "greedy"

    def decide(self, harness: Any, ctx: Mapping[str, Any]) -> str | None:
        from adx_showdown.selfplay.codex_adapter import _greedy_decide

        return _greedy_decide(harness, dict(ctx))


def agent_decide(agent: Agent) -> DecideFn:
    """Adapt an :class:`Agent` to a :data:`~codex_adapter.DecideFn`.

    An ``Agent`` is already callable with the ``DecideFn`` shape, so this is
    identity-with-typing — it names the generic ``(harness, ctx) -> id`` seam that
    the codex-specific ``codex_decide`` predated, and gives call sites a clear,
    backend-agnostic entry point.
    """
    return agent
