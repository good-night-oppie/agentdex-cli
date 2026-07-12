"""Tests for ``adx evolve-submit`` (M4 frontier submit) with a faked Bene boundary."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from adx_frontier.mh_bridge import BeneApi, BridgeOutcome
from agentdex_cli import evolve_submit_cmd
from agentdex_cli.cli import main
from agentdex_cli.evolve_submit_cmd import (
    _BENE_INSTALL_HINT,
    _EXIT_BENE,
    _EXIT_GATE,
    EvolveSubmitError,
    _load_or_empty_ledger,
    _parse_trust_receipt,
    _record_from_export_dict,
    open_bene_context,
    submit_measured_candidate,
)


class _Genome:
    genome_id = "genome-1"
    scores: dict[str, float] = {}
    engram_id = None

    def encode(self) -> bytes:
        return b"genome"


class _Store:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def append(self, *args: Any, **kwargs: Any) -> str:
        self.calls.append((args, kwargs))
        return "engram-1"


def _write_candidate(tmp_path: Path, *, name: str = "submitter") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "agent.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "candidate.yaml").write_text(
        yaml.safe_dump(
            {
                "name": name,
                "entrypoint": "python agent.py",
                "mutable": ["agent.py"],
                "base_model": "model-a",
                "budget": {"usd": 5.0, "wall_clock_min": 10.0},
                "ladders": ["pokeagent-gen1ou"],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _axes(quality: float, *, cost: float = 1.0, wall: float = 2.0) -> dict[str, float]:
    return {"quality": quality, "cost_dollar": cost, "wall_clock_sec": wall}


def _write_measurement(
    path: Path,
    *,
    quality: float = 2.0,
    receipt: dict[str, Any] | None = None,
    ladder_id: str = "pokeagent-gen1ou",
    base_model: str = "model-a",
    budget: dict[str, float] | None = None,
    candidate: str | None = None,
    scores: dict[str, float] | None = None,
) -> Path:
    payload: dict[str, Any] = {
        "ladder_id": ladder_id,
        "base_model": base_model,
        "scores": scores if scores is not None else _axes(quality),
        "cost_is_measured": True,
        "effective_ladder_class": "live_adversarial",
        "receipt": receipt
        or {
            "tier": "verified",
            "kind": "pokeagent_rating",
            "ref": "rating:submitter",
            "artifacts": [],
        },
        "budget": budget or {"usd": 5.0, "wall_clock_min": 10.0},
        "measured_at_utc": "2026-07-12T00:00:00Z",
    }
    if candidate is not None:
        payload["candidate"] = candidate
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_baseline(path: Path, quality: float = 1.0) -> Path:
    path.write_text(json.dumps(_axes(quality), indent=2) + "\n", encoding="utf-8")
    return path


def _fake_api(status: str, *, promoted: bool | None = None) -> BeneApi:
    if promoted is None:
        promoted = status == "ACCEPT"

    def auto(engram_id: str, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            promoted=promoted,
            status=status,
            verdict_engram="verdict-1",
            reason=f"gate:{status}",
        )

    return BeneApi(lambda _data: _Genome(), auto)


def _submit(
    tmp_path: Path,
    *,
    status: str = "ACCEPT",
    measurement: Path | None = None,
    baseline: Path | None = None,
    api: BeneApi | None = None,
    store: _Store | None = None,
    out: Path | None = None,
) -> dict[str, Any]:
    root = _write_candidate(tmp_path / "agent")
    measure_path = measurement or _write_measurement(tmp_path / "measure.json")
    baseline_path = baseline or _write_baseline(tmp_path / "baseline.json")
    frontier = out or (tmp_path / "frontier.json")
    return submit_measured_candidate(
        agent=root,
        measurement=measure_path,
        baseline=baseline_path,
        metric="quality",
        out=frontier,
        agent_id="collaborative-agent",
        store=store or _Store(),
        conn=object(),
        api=api or _fake_api(status),
        generated_at_utc="2026-07-12T00:00:00Z",
    )


def test_accept_exports_promoted_frontier_record(tmp_path: Path) -> None:
    summary = _submit(tmp_path, status="ACCEPT")
    assert summary["promoted"] is True
    assert summary["status"] == "ACCEPT"
    payload = json.loads(Path(summary["frontier"]).read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["generated_at_utc"] == "2026-07-12T00:00:00Z"
    entry = payload["partitions"][0]["frontier"][0]
    assert entry["candidate"] == "submitter"
    assert entry["promotion"] == {
        "candidate_engram_id": "engram-1",
        "promoted": True,
        "status": "ACCEPT",
        "verdict_engram": "verdict-1",
    }
    assert entry["receipt"]["tier"] == "verified"
    assert entry["receipt"]["kind"] == "pokeagent_rating"
    assert entry["receipt"]["ref"] == "rating:submitter"


def test_non_accept_exports_with_promoted_false(tmp_path: Path) -> None:
    summary = _submit(tmp_path, status="REJECT")
    assert summary["promoted"] is False
    assert summary["status"] == "REJECT"
    entry = json.loads(Path(summary["frontier"]).read_text(encoding="utf-8"))["partitions"][0][
        "frontier"
    ][0]
    assert entry["promotion"]["promoted"] is False
    assert entry["promotion"]["status"] == "REJECT"


def test_preserves_self_reported_trust_receipt(tmp_path: Path) -> None:
    measure = _write_measurement(
        tmp_path / "measure.json",
        receipt={
            "tier": "self_reported",
            "kind": "raw_artifacts",
            "ref": "",
            "artifacts": ["jobs/run.log"],
        },
    )
    summary = _submit(tmp_path, measurement=measure)
    entry = json.loads(Path(summary["frontier"]).read_text(encoding="utf-8"))["partitions"][0][
        "frontier"
    ][0]
    assert entry["receipt"]["tier"] == "self_reported"
    assert entry["receipt"]["artifacts"] == ["jobs/run.log"]


def test_validation_failures_before_bene(tmp_path: Path) -> None:
    store = _Store()
    api = _fake_api("ACCEPT")
    root = _write_candidate(tmp_path / "agent")
    measure = _write_measurement(tmp_path / "measure.json", base_model="other-model")
    baseline = _write_baseline(tmp_path / "baseline.json")

    with pytest.raises(EvolveSubmitError, match="base_model mismatch") as mismatch:
        submit_measured_candidate(
            agent=root,
            measurement=measure,
            baseline=baseline,
            metric="quality",
            out=tmp_path / "frontier.json",
            agent_id="collaborative-agent",
            store=store,
            conn=object(),
            api=api,
        )
    assert mismatch.value.exit_code == _EXIT_GATE
    assert store.calls == []

    with pytest.raises(EvolveSubmitError, match="ladder mismatch"):
        submit_measured_candidate(
            agent=root,
            measurement=_write_measurement(tmp_path / "bad-ladder.json", ladder_id="tb2"),
            baseline=baseline,
            metric="quality",
            out=tmp_path / "frontier.json",
            agent_id="collaborative-agent",
            store=store,
            conn=object(),
            api=api,
        )

    with pytest.raises(EvolveSubmitError, match="budget mismatch"):
        submit_measured_candidate(
            agent=root,
            measurement=_write_measurement(
                tmp_path / "bad-budget.json",
                budget={"usd": 9.0, "wall_clock_min": 10.0},
            ),
            baseline=baseline,
            metric="quality",
            out=tmp_path / "frontier.json",
            agent_id="collaborative-agent",
            store=store,
            conn=object(),
            api=api,
        )

    with pytest.raises(EvolveSubmitError, match="candidate mismatch"):
        submit_measured_candidate(
            agent=root,
            measurement=_write_measurement(
                tmp_path / "bad-candidate.json", candidate="someone-else"
            ),
            baseline=baseline,
            metric="quality",
            out=tmp_path / "frontier.json",
            agent_id="collaborative-agent",
            store=store,
            conn=object(),
            api=api,
        )

    with pytest.raises(EvolveSubmitError, match="missing frontier axes"):
        submit_measured_candidate(
            agent=root,
            measurement=_write_measurement(tmp_path / "bad-scores.json", scores={"quality": 1.0}),
            baseline=baseline,
            metric="quality",
            out=tmp_path / "frontier.json",
            agent_id="collaborative-agent",
            store=store,
            conn=object(),
            api=api,
        )
    assert store.calls == []


def test_bridge_invocation_uses_measurement_and_baseline(tmp_path: Path, monkeypatch) -> None:
    seen: dict[str, Any] = {}

    def fake_bridge(candidate, **kwargs):  # type: ignore[no-untyped-def]
        seen["candidate_name"] = candidate.name
        seen.update(kwargs)
        return BridgeOutcome(
            candidate_engram_id="engram-1",
            genome_id="genome-1",
            promoted=True,
            status="ACCEPT",
            verdict_engram="verdict-1",
            reason="ok",
        )

    monkeypatch.setattr(evolve_submit_cmd, "bridge_collaborative_candidate", fake_bridge)
    root = _write_candidate(tmp_path / "agent")
    measure = _write_measurement(tmp_path / "measure.json", quality=3.5)
    baseline = _write_baseline(tmp_path / "baseline.json", quality=1.25)
    store = _Store()
    conn = object()
    api = _fake_api("ACCEPT")

    submit_measured_candidate(
        agent=root,
        measurement=measure,
        baseline=baseline,
        metric="quality",
        out=tmp_path / "frontier.json",
        agent_id="collaborative-agent",
        store=store,
        conn=conn,
        api=api,
        generated_at_utc="2026-07-12T00:00:00Z",
    )

    assert seen["candidate_name"] == "submitter"
    assert seen["ladder_id"] == "pokeagent-gen1ou"
    assert seen["scores"] == _axes(3.5)
    assert seen["baseline"] == _axes(1.25)
    assert seen["metric"] == "quality"
    assert seen["agent_id"] == "collaborative-agent"
    assert seen["store"] is store
    assert seen["conn"] is conn
    assert seen["api"] is api


def test_frontier_export_is_deterministic_and_atomic(tmp_path: Path) -> None:
    out = tmp_path / "frontier.json"
    summary = _submit(tmp_path / "one", out=out)
    text = out.read_text(encoding="utf-8")
    assert summary["frontier"] == str(out)
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"
    assert not list(tmp_path.glob("*.tmp"))
    payload = json.loads(text)
    assert payload["schema_version"] == 1
    assert payload["partitions"][0]["ladder_id"] == "pokeagent-gen1ou"
    assert payload["partitions"][0]["base_model"] == "model-a"
    assert payload["partitions"][0]["frontier"][0]["promotion"]["status"] == "ACCEPT"


def test_cli_errors_are_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _write_candidate(tmp_path / "agent")
    measure = _write_measurement(tmp_path / "measure.json", base_model="nope")
    baseline = _write_baseline(tmp_path / "baseline.json")
    rc = main(
        [
            "evolve-submit",
            "--agent",
            str(root),
            "--measurement",
            str(measure),
            "--baseline",
            str(baseline),
            "--bene-db",
            str(tmp_path / "missing.db"),
            "--agent-id",
            "collaborative-agent",
            "--metric",
            "quality",
            "--out",
            str(tmp_path / "frontier.json"),
        ]
    )
    err = capsys.readouterr().err
    assert rc == _EXIT_GATE
    assert "base_model mismatch" in err
    assert "Traceback" not in err


def test_cli_bene_missing_db_is_exit_3(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _write_candidate(tmp_path / "agent")
    measure = _write_measurement(tmp_path / "measure.json")
    baseline = _write_baseline(tmp_path / "baseline.json")
    rc = main(
        [
            "evolve-submit",
            "--agent",
            str(root),
            "--measurement",
            str(measure),
            "--baseline",
            str(baseline),
            "--bene-db",
            str(tmp_path / "missing.db"),
            "--agent-id",
            "collaborative-agent",
            "--metric",
            "quality",
            "--out",
            str(tmp_path / "frontier.json"),
        ]
    )
    err = capsys.readouterr().err
    assert rc == _EXIT_BENE
    assert "bene database not found" in err
    assert "Traceback" not in err


def test_bene_extra_declared_in_pyproject() -> None:
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    data = tomllib.loads(pyproject)
    extras = data["project"]["optional-dependencies"]
    assert "bene" in extras
    assert any(req.startswith("bene>=") for req in extras["bene"])
    assert "bene>=0.2.1" in extras["bene"]


def test_missing_bene_install_message_names_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    # Simulate a missing Bene install even if the optional extra is present.
    for name in ("bene", "bene.core", "bene.kernel"):
        monkeypatch.setitem(sys.modules, name, None)

    db = tmp_path / "bene.db"
    db.write_text("placeholder", encoding="utf-8")
    with pytest.raises(EvolveSubmitError) as raised:
        open_bene_context(db, "agent-1")
    assert raised.value.exit_code == _EXIT_BENE
    assert _BENE_INSTALL_HINT in str(raised.value)


def test_bene_boundary_never_echoes_credential_exception_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    import types

    secret = "sk_live_CREDENTIAL_VALUE_9f3a"  # pragma: allowlist secret

    class LeakyDbError(RuntimeError):
        pass

    class FakeBene:
        def __init__(self, db_path: str) -> None:
            raise LeakyDbError(f"sqlite open failed for {secret}")

    bene_pkg = types.ModuleType("bene")
    bene_core = types.ModuleType("bene.core")
    bene_kernel = types.ModuleType("bene.kernel")
    bene_core.Bene = FakeBene  # type: ignore[attr-defined]
    bene_kernel.EngramStore = object  # type: ignore[attr-defined]
    bene_kernel.ensure_v2 = lambda _conn: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "bene", bene_pkg)
    monkeypatch.setitem(sys.modules, "bene.core", bene_core)
    monkeypatch.setitem(sys.modules, "bene.kernel", bene_kernel)

    db = tmp_path / "bene.db"
    db.write_text("placeholder", encoding="utf-8")
    with pytest.raises(EvolveSubmitError) as raised:
        open_bene_context(db, "agent-1")
    msg = str(raised.value)
    assert raised.value.exit_code == _EXIT_BENE
    assert secret not in msg
    assert "LeakyDbError" in msg
    assert "bene database error" in msg


def test_negative_cost_or_wall_rejected_before_bene(tmp_path: Path) -> None:
    store = _Store()
    api = _fake_api("ACCEPT")
    root = _write_candidate(tmp_path / "agent")
    baseline = _write_baseline(tmp_path / "baseline.json")

    with pytest.raises(EvolveSubmitError, match="non-negative") as raised:
        submit_measured_candidate(
            agent=root,
            measurement=_write_measurement(
                tmp_path / "neg-cost.json",
                scores=_axes(2.0, cost=-0.01),
            ),
            baseline=baseline,
            metric="quality",
            out=tmp_path / "frontier.json",
            agent_id="collaborative-agent",
            store=store,
            conn=object(),
            api=api,
        )
    assert raised.value.exit_code == _EXIT_GATE
    assert store.calls == []
    assert not (tmp_path / "frontier.json").exists()

    with pytest.raises(EvolveSubmitError, match="non-negative") as raised_wall:
        submit_measured_candidate(
            agent=root,
            measurement=_write_measurement(
                tmp_path / "neg-wall.json",
                scores=_axes(2.0, wall=-1.0),
            ),
            baseline=baseline,
            metric="quality",
            out=tmp_path / "frontier.json",
            agent_id="collaborative-agent",
            store=store,
            conn=object(),
            api=api,
        )
    assert raised_wall.value.exit_code == _EXIT_GATE
    assert store.calls == []


def test_bridge_valueerror_is_exit_bene_without_echo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bridge ValueError is a Bene-boundary failure; never echo its text (may hold secrets)."""

    secret = "sk_live_BRIDGE_SECRET_VALUE_7c2e"  # pragma: allowlist secret

    def fake_bridge(*_a: Any, **_k: Any) -> BridgeOutcome:
        raise ValueError(f"scores must include quality for bene bridge contract {secret}")

    monkeypatch.setattr(evolve_submit_cmd, "bridge_collaborative_candidate", fake_bridge)
    root = _write_candidate(tmp_path / "agent")
    measure = _write_measurement(tmp_path / "measure.json")
    baseline = _write_baseline(tmp_path / "baseline.json")
    with pytest.raises(EvolveSubmitError) as raised:
        submit_measured_candidate(
            agent=root,
            measurement=measure,
            baseline=baseline,
            metric="quality",
            out=tmp_path / "frontier.json",
            agent_id="collaborative-agent",
            store=_Store(),
            conn=object(),
            api=_fake_api("ACCEPT"),
        )
    msg = str(raised.value)
    assert raised.value.exit_code == _EXIT_BENE
    assert "bene bridge error" in msg
    assert "ValueError" in msg
    assert secret not in msg
    assert "scores must include" not in msg
    assert "bene bridge contract" not in msg


def test_cli_invalid_frontier_record_is_clean_exit_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _write_candidate(tmp_path / "agent")
    measure = _write_measurement(
        tmp_path / "measure.json",
        scores=_axes(2.0, cost=-3.0),
    )
    baseline = _write_baseline(tmp_path / "baseline.json")
    rc = main(
        [
            "evolve-submit",
            "--agent",
            str(root),
            "--measurement",
            str(measure),
            "--baseline",
            str(baseline),
            "--bene-db",
            str(tmp_path / "missing.db"),
            "--agent-id",
            "collaborative-agent",
            "--metric",
            "quality",
            "--out",
            str(tmp_path / "frontier.json"),
        ]
    )
    err = capsys.readouterr().err
    assert rc == _EXIT_GATE
    assert "invalid frontier record" in err
    assert "non-negative" in err
    assert "Traceback" not in err
    assert not (tmp_path / "frontier.json").exists()


def test_post_promotion_unwritable_out_is_clean_exit_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "frontier.json"

    def boom(*_a: Any, **_k: Any) -> Path:
        raise OSError(f"Permission denied writing secret=sk_live_SHOULD_NOT_LEAK to {out}")

    monkeypatch.setattr(evolve_submit_cmd.FrontierLedger, "export", boom)
    root = _write_candidate(tmp_path / "agent")
    measure = _write_measurement(tmp_path / "measure.json")
    baseline = _write_baseline(tmp_path / "baseline.json")

    with pytest.raises(EvolveSubmitError) as raised:
        submit_measured_candidate(
            agent=root,
            measurement=measure,
            baseline=baseline,
            metric="quality",
            out=out,
            agent_id="collaborative-agent",
            store=_Store(),
            conn=object(),
            api=_fake_api("ACCEPT"),
        )
    msg = str(raised.value)
    assert raised.value.exit_code == _EXIT_GATE
    assert "frontier persistence failed after Bene verdict" in msg
    assert "promoted=True" in msg
    assert "sk_live_SHOULD_NOT_LEAK" not in msg

    def fake_open(*_a: Any, **_k: Any) -> tuple[Any, Any]:
        return _Store(), object()

    monkeypatch.setattr(evolve_submit_cmd, "open_bene_context", fake_open)
    monkeypatch.setattr(
        evolve_submit_cmd,
        "bridge_collaborative_candidate",
        lambda *_a, **_k: BridgeOutcome(
            candidate_engram_id="engram-1",
            genome_id="genome-1",
            promoted=True,
            status="ACCEPT",
            verdict_engram="verdict-1",
            reason="ok",
        ),
    )
    rc = main(
        [
            "evolve-submit",
            "--agent",
            str(root),
            "--measurement",
            str(measure),
            "--baseline",
            str(baseline),
            "--bene-db",
            str(tmp_path / "any.db"),
            "--agent-id",
            "collaborative-agent",
            "--metric",
            "quality",
            "--out",
            str(out),
        ]
    )
    err = capsys.readouterr().err
    assert rc == _EXIT_GATE
    assert "frontier persistence failed after Bene verdict" in err
    assert "promoted=True" in err
    assert "Traceback" not in err
    assert "sk_live_SHOULD_NOT_LEAK" not in err


def test_rejects_string_promoted_in_persisted_frontier(tmp_path: Path) -> None:
    path = tmp_path / "frontier.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at_utc": "2026-07-12T00:00:00Z",
                "partitions": [
                    {
                        "ladder_id": "pokeagent-gen1ou",
                        "base_model": "model-a",
                        "frontier": [
                            {
                                "candidate": "submitter",
                                "ladder_id": "pokeagent-gen1ou",
                                "base_model": "model-a",
                                "scores": _axes(2.0),
                                "budget_usd": 5.0,
                                "budget_wall_clock_min": 10.0,
                                "receipt": {
                                    "tier": "verified",
                                    "kind": "pokeagent_rating",
                                    "ref": "rating:submitter",
                                    "artifacts": [],
                                },
                                "measured_at_utc": "2026-07-12T00:00:00Z",
                                "promotion": {
                                    "candidate_engram_id": "engram-1",
                                    "promoted": "false",
                                    "status": "REJECT",
                                    "verdict_engram": "verdict-1",
                                },
                            }
                        ],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(EvolveSubmitError, match="promotion.promoted must be a bool"):
        _load_or_empty_ledger(path)


def test_rejects_non_string_receipt_artifacts() -> None:
    with pytest.raises(EvolveSubmitError, match="artifacts entries must be strings"):
        _parse_trust_receipt(
            {
                "tier": "self_reported",
                "kind": "raw_artifacts",
                "ref": "",
                "artifacts": [{"path": "jobs/run.log"}],
            }
        )
    with pytest.raises(EvolveSubmitError, match="artifacts entries must be strings"):
        _record_from_export_dict(
            {
                "candidate": "submitter",
                "ladder_id": "pokeagent-gen1ou",
                "base_model": "model-a",
                "scores": _axes(2.0),
                "budget_usd": 5.0,
                "budget_wall_clock_min": 10.0,
                "receipt": {
                    "tier": "self_reported",
                    "kind": "raw_artifacts",
                    "ref": "",
                    "artifacts": [123],
                },
                "measured_at_utc": "2026-07-12T00:00:00Z",
                "promotion": None,
            }
        )


def test_evolve_prompt_names_evolve_submit() -> None:
    from agentdex_cli.evolve_cmd import _outer_prompt

    prompt = _outer_prompt("x", "tb2", inner_weco_run=False)
    assert "adx evolve-submit" in prompt
