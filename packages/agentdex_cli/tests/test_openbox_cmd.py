"""Tests for ``adx openbox`` — self-service backend binding (v3 MVP #3)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pytest
import yaml
from agentdex_cli.openbox_cmd import (
    OpenboxError,
    cmd_openbox_check,
    cmd_openbox_init,
    load_openbox,
    probe_backend,
    render_openbox,
)


def _policy(tmp_path: Path, pool: list[str] | None = None) -> Path:
    p = tmp_path / "orchestration.yaml"
    names = pool if pool is not None else ["claude-opus", "deepseek", "codex-gpt"]
    lines = ["version: 1", "pool:"]
    lines.extend(f"  - {n}" for n in names)
    lines.append("explore_rate: 0.2\n")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _stub(bin_dir: Path, name: str, exit_code: int = 0) -> Path:
    script = bin_dir / name
    script.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def _ns_init(**kwargs):
    defaults = {
        "policy": ".agentdex/orchestration.yaml",
        "out": ".agentdex/openbox.yaml",
        "force": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _ns_check(**kwargs):
    defaults = {
        "file": ".agentdex/openbox.yaml",
        "policy": ".agentdex/orchestration.yaml",
        "json": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #
def test_init_seeds_every_pool_name_with_heuristics(tmp_path):
    policy = _policy(tmp_path, ["claude-opus", "deepseek", "my-codex-box", "manus-x"])
    out = tmp_path / "openbox.yaml"
    rc = cmd_openbox_init(_ns_init(policy=str(policy), out=str(out)))
    assert rc == 0
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert doc["version"] == 1
    assert set(doc["backends"]) == {"claude-opus", "deepseek", "my-codex-box", "manus-x"}
    assert doc["backends"]["claude-opus"]["probe"] == ["claude", "--version"]
    assert doc["backends"]["claude-opus"]["invoke"] == "claude"
    assert doc["backends"]["my-codex-box"]["probe"] == ["codex", "--version"]
    assert doc["backends"]["manus-x"]["probe"] == ["manus", "--version"]
    assert doc["backends"]["deepseek"]["probe"] == []
    assert doc["backends"]["deepseek"]["invoke"] == "deepseek"
    assert all(b["token_ref"] == "none" for b in doc["backends"].values())


def test_init_refuses_overwrite_without_force(tmp_path, capsys):
    policy = _policy(tmp_path)
    out = tmp_path / "openbox.yaml"
    out.write_text("version: 1\nbackends: {}\n", encoding="utf-8")
    rc = cmd_openbox_init(_ns_init(policy=str(policy), out=str(out), force=False))
    assert rc == 2
    assert str(out) in capsys.readouterr().out
    assert out.read_text(encoding="utf-8") == "version: 1\nbackends: {}\n"


def test_init_force_overwrites(tmp_path):
    policy = _policy(tmp_path, ["claude-opus"])
    out = tmp_path / "openbox.yaml"
    out.write_text("version: 1\nbackends: {}\n", encoding="utf-8")
    rc = cmd_openbox_init(_ns_init(policy=str(policy), out=str(out), force=True))
    assert rc == 0
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert "claude-opus" in doc["backends"]


def test_init_missing_policy_rc2_no_traceback(tmp_path, capsys):
    out = tmp_path / "openbox.yaml"
    rc = cmd_openbox_init(_ns_init(policy=str(tmp_path / "nope.yaml"), out=str(out)))
    assert rc == 2
    err_out = capsys.readouterr().out
    assert "adx interview" in err_out
    assert "Traceback" not in err_out
    assert not out.exists()


# --------------------------------------------------------------------------- #
# check + probe
# --------------------------------------------------------------------------- #
def test_check_statuses_with_path_stubs(tmp_path, monkeypatch, capsys):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "good-cli", 0)
    _stub(bin_dir, "bad-cli", 1)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))

    openbox = tmp_path / "openbox.yaml"
    openbox.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "ready-one": {
                        "kind": "subscription-cli",
                        "probe": ["good-cli", "--version"],
                        "invoke": "good-cli",
                        "token_ref": "none",
                    },
                    "noauth-one": {
                        "kind": "subscription-cli",
                        "probe": ["bad-cli", "--version"],
                        "invoke": "bad-cli",
                        "token_ref": "none",
                    },
                    "missing-one": {
                        "kind": "subscription-cli",
                        "probe": ["definitely-not-on-path-xyz", "--version"],
                        "invoke": "x",
                        "token_ref": "none",
                    },
                    "unprobed": {
                        "kind": "anthropic-endpoint",
                        "probe": [],
                        "invoke": "anthropic-endpoint",
                        "token_ref": "none",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    policy = _policy(tmp_path, ["ready-one", "noauth-one", "missing-one", "unprobed"])
    rc = cmd_openbox_check(_ns_check(file=str(openbox), policy=str(policy)))
    assert rc == 1  # not all READY
    out = capsys.readouterr().out
    assert "READY" in out
    assert "NO-AUTH" in out
    assert "MISSING" in out
    assert "UNPROBED" in out
    assert "pool coverage:" in out


def test_check_full_pool_ready_exits_0(tmp_path, monkeypatch, capsys):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "claude", 0)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))

    openbox = tmp_path / "openbox.yaml"
    openbox.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "claude-opus": {
                        "kind": "subscription-cli",
                        "probe": ["claude", "--version"],
                        "invoke": "claude",
                        "token_ref": "none",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    policy = _policy(tmp_path, ["claude-opus"])
    rc = cmd_openbox_check(_ns_check(file=str(openbox), policy=str(policy), json=True))
    assert rc == 0
    captured = capsys.readouterr().out
    payload = json.loads(captured.strip().splitlines()[-1])
    assert payload["backends"]["claude-opus"] == "READY"
    assert payload["pool_covered"] is True


def test_check_uncovered_pool_name_exits_1(tmp_path, monkeypatch, capsys):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "claude", 0)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))

    openbox = tmp_path / "openbox.yaml"
    openbox.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "claude-opus": {
                        "kind": "subscription-cli",
                        "probe": ["claude", "--version"],
                        "invoke": "claude",
                        "token_ref": "none",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    # pool has an extra name with no backend → uncovered
    policy = _policy(tmp_path, ["claude-opus", "deepseek"])
    rc = cmd_openbox_check(_ns_check(file=str(openbox), policy=str(policy), json=True))
    assert rc == 1
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["pool_covered"] is False


def test_json_shape(tmp_path, monkeypatch, capsys):
    openbox = tmp_path / "openbox.yaml"
    openbox.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "x": {
                        "kind": "subscription-cli",
                        "probe": [],
                        "invoke": "x",
                        "token_ref": "none",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    policy = _policy(tmp_path, ["x"])
    rc = cmd_openbox_check(_ns_check(file=str(openbox), policy=str(policy), json=True))
    assert rc == 1  # UNPROBED ≠ READY
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert set(payload) == {"backends", "pool_covered"}
    assert isinstance(payload["backends"], dict)
    assert isinstance(payload["pool_covered"], bool)
    assert payload["backends"]["x"] == "UNPROBED"


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def test_literal_sk_token_ref_rejected_without_echo(tmp_path):
    secret = "sk-abcdefghijklmnopqrstuvwxyz"
    path = tmp_path / "openbox.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "evil": {
                        "kind": "subscription-cli",
                        "probe": [],
                        "invoke": "x",
                        "token_ref": secret,
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(OpenboxError) as ei:
        load_openbox(path)
    msg = str(ei.value)
    assert "looks like a credential value" in msg
    assert secret not in msg
    assert "evil" in msg


def test_token_ref_env_file_none_accepted(tmp_path):
    cred = tmp_path / "cred"
    cred.write_text("tok\n", encoding="utf-8")
    cred.chmod(0o600)
    path = tmp_path / "openbox.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "a": {
                        "kind": "subscription-cli",
                        "probe": [],
                        "invoke": "a",
                        "token_ref": "none",
                    },
                    "b": {
                        "kind": "anthropic-endpoint",
                        "probe": [],
                        "invoke": "anthropic-endpoint",
                        "token_ref": "env:ANTHROPIC_API_KEY",
                    },
                    "c": {
                        "kind": "openai-endpoint",
                        "probe": [],
                        "invoke": "openai-endpoint",
                        "token_ref": f"file:{cred}",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    doc = load_openbox(path)
    assert set(doc["backends"]) == {"a", "b", "c"}


def test_unknown_kind_rejected(tmp_path):
    path = tmp_path / "openbox.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "x": {
                        "kind": "not-a-kind",
                        "probe": [],
                        "invoke": "x",
                        "token_ref": "none",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(OpenboxError) as ei:
        load_openbox(path)
    msg = str(ei.value)
    assert "unknown kind" in msg
    assert "not-a-kind" not in msg


def test_file_ref_0644_warns_but_passes(tmp_path, capsys):
    cred = tmp_path / "cred"
    cred.write_text("tok\n", encoding="utf-8")
    cred.chmod(0o644)
    path = tmp_path / "openbox.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "c": {
                        "kind": "openai-endpoint",
                        "probe": [],
                        "invoke": "openai-endpoint",
                        "token_ref": f"file:{cred}",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    doc = load_openbox(path)
    assert "c" in doc["backends"]
    err = capsys.readouterr().err
    assert "0600" in err or "warning" in err.lower()


def test_render_openbox_matches_heuristics():
    doc = render_openbox(["Claude-Sonnet", "other"])
    assert doc["backends"]["Claude-Sonnet"]["probe"] == ["claude", "--version"]
    assert doc["backends"]["other"]["probe"] == []
    assert doc["backends"]["other"]["invoke"] == "other"


def test_probe_backend_empty_is_unprobed():
    assert probe_backend({"probe": []}) == "UNPROBED"
    assert probe_backend({}) == "UNPROBED"


# --------------------------------------------------------------------------- #
# secrets-hardening (FIX-A..F)
# --------------------------------------------------------------------------- #
_FAKE_SK = "sk-TESTFAKEabcdefghijklmnop"


def test_check_malformed_yaml_rc2_no_token_no_traceback(tmp_path, capsys):
    """Unterminated quoted scalar with a fake sk- token → rc 2, no echo/traceback."""
    openbox = tmp_path / "openbox.yaml"
    openbox.write_text(
        f'version: 1\nbackends:\n  x:\n    kind: "{_FAKE_SK}\n',
        encoding="utf-8",
    )
    rc = cmd_openbox_check(_ns_check(file=str(openbox), policy=str(tmp_path / "nope.yaml")))
    assert rc == 2
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert _FAKE_SK not in combined
    assert "Traceback" not in combined
    assert "line" in combined and "column" in combined


def test_init_malformed_policy_rc2_no_token_no_traceback(tmp_path, capsys):
    policy = tmp_path / "orchestration.yaml"
    policy.write_text(f'pool: "{_FAKE_SK}\n', encoding="utf-8")
    out = tmp_path / "openbox.yaml"
    rc = cmd_openbox_init(_ns_init(policy=str(policy), out=str(out)))
    assert rc == 2
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert _FAKE_SK not in combined
    assert "Traceback" not in combined
    assert "line" in combined and "column" in combined
    assert not out.exists()


def test_nested_secrets_rejected_without_echo(tmp_path):
    secret = _FAKE_SK
    secret_key = "sk-TESTFAKEkeyvaluexx"
    path = tmp_path / "openbox.yaml"

    # headers list item
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "nested": {
                        "kind": "subscription-cli",
                        "probe": [],
                        "invoke": "x",
                        "token_ref": "none",
                        "headers": [f"Authorization: Bearer {secret}"],
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(OpenboxError) as ei:
        load_openbox(path)
    assert "headers[0]" in str(ei.value)
    assert secret not in str(ei.value)

    # nested dict value
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "nested": {
                        "kind": "subscription-cli",
                        "probe": [],
                        "invoke": "x",
                        "token_ref": "none",
                        "meta": {"api_key": secret},
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(OpenboxError) as ei:
        load_openbox(path)
    assert secret not in str(ei.value)
    assert "meta.api_key" in str(ei.value)

    # secret-looking dict key
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "nested": {
                        "kind": "subscription-cli",
                        "probe": [],
                        "invoke": "x",
                        "token_ref": "none",
                        secret_key: "ok",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(OpenboxError) as ei:
        load_openbox(path)
    msg = str(ei.value)
    assert secret_key not in msg
    assert "field key matches a credential pattern" in msg


def test_secret_backend_name_rejected_without_echo(tmp_path):
    secret_name = _FAKE_SK
    path = tmp_path / "openbox.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    secret_name: {
                        "kind": "subscription-cli",
                        "probe": [],
                        "invoke": "x",
                        "token_ref": "none",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(OpenboxError) as ei:
        load_openbox(path)
    msg = str(ei.value)
    assert secret_name not in msg
    assert "backend name matches a credential pattern" in msg


def test_kind_secret_value_rejected_without_echo(tmp_path):
    secret = _FAKE_SK
    path = tmp_path / "openbox.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "x": {
                        "kind": secret,
                        "probe": [],
                        "invoke": "x",
                        "token_ref": "none",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(OpenboxError) as ei:
        load_openbox(path)
    msg = str(ei.value)
    assert "unknown kind" in msg
    assert secret not in msg


def test_version_non_integer_secret_rejected_without_echo(tmp_path):
    secret = _FAKE_SK
    path = tmp_path / "openbox.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": secret,
                "backends": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(OpenboxError) as ei:
        load_openbox(path)
    msg = str(ei.value)
    assert "non-integer value" in msg
    assert secret not in msg


def test_json_missing_policy_pool_covered_null(tmp_path, capsys):
    openbox = tmp_path / "openbox.yaml"
    openbox.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "x": {
                        "kind": "subscription-cli",
                        "probe": [],
                        "invoke": "x",
                        "token_ref": "none",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    rc = cmd_openbox_check(
        _ns_check(file=str(openbox), policy=str(tmp_path / "missing.yaml"), json=True)
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["pool_covered"] is None


def test_broadened_secret_shapes_rejected_without_echo(tmp_path):
    """C1: hyphenated sk-, JWT Bearer, URL userinfo, github_pat, AIza — no echo."""
    cases = [
        ("api_key", "sk-ant-api03-TESTFAKE0000000000"),
        ("api_key", "sk-proj-TESTFAKE0000000000"),
        ("headers", ["Authorization: Bearer eyJTESTFAKE00000000000000"]),
        ("base_url", "https://user:hunter2@host.example"),
        ("extra", "github_pat_TESTFAKE00000000000000000"),
        ("extra2", "AIzaTESTFAKE000000000000000000000000"),
    ]
    for field, value in cases:
        path = tmp_path / f"ob-{field}.yaml"
        backend: dict = {
            "kind": "subscription-cli",
            "probe": [],
            "invoke": "x",
            "token_ref": "none",
            field: value,
        }
        path.write_text(
            yaml.safe_dump({"version": 1, "backends": {"nested": backend}}, sort_keys=False),
            encoding="utf-8",
        )
        with pytest.raises(OpenboxError) as ei:
            load_openbox(path)
        msg = str(ei.value)
        body = value if isinstance(value, str) else value[0]
        # secret body must never appear; for Bearer the JWT substring is the body
        if "eyJ" in body:
            assert "eyJTESTFAKE00000000000000" not in msg
        elif "hunter2" in body:
            assert "hunter2" not in msg
        else:
            assert body not in msg


def test_legit_openbox_fields_still_pass(tmp_path):
    """C1: base_url without userinfo, probe argv, token_ref forms stay accepted."""
    path = tmp_path / "openbox.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "ok": {
                        "kind": "subscription-cli",
                        "probe": ["claude", "--version"],
                        "invoke": "claude",
                        "token_ref": "none",
                        "base_url": "http://127.0.0.1:8085",
                    },
                    "env-ref": {
                        "kind": "anthropic-endpoint",
                        "probe": [],
                        "invoke": "anthropic-endpoint",
                        "token_ref": "env:ANTHROPIC_API_KEY",
                    },
                    "file-ref": {
                        "kind": "openai-endpoint",
                        "probe": [],
                        "invoke": "openai-endpoint",
                        "token_ref": "file:/tmp/plain-cred-path",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    doc = load_openbox(path)
    assert set(doc["backends"]) == {"ok", "env-ref", "file-ref"}


def test_check_empty_pool_rc2_pool_covered_null(tmp_path, capsys):
    """F2: empty policy pool is not vacuous coverage — rc 2, pool_covered null."""
    openbox = tmp_path / "openbox.yaml"
    openbox.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "x": {
                        "kind": "subscription-cli",
                        "probe": [],
                        "invoke": "x",
                        "token_ref": "none",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    policy = tmp_path / "orchestration.yaml"
    policy.write_text("version: 1\npool: []\n", encoding="utf-8")
    rc = cmd_openbox_check(_ns_check(file=str(openbox), policy=str(policy), json=True))
    assert rc == 2
    captured = capsys.readouterr().out
    assert "empty pool" in captured
    payload = json.loads(captured.strip().splitlines()[-1])
    assert payload["pool_covered"] is None


def test_secret_shaped_file_token_ref_no_echo(tmp_path, capsys):
    """F3: file: path matching SECRET_RE is rejected without echoing the secret body."""
    secret_body = "sk-ant-TESTFAKE0000000000"
    path = tmp_path / "openbox.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "backends": {
                    "x": {
                        "kind": "subscription-cli",
                        "probe": [],
                        "invoke": "x",
                        "token_ref": f"file:/tmp/{secret_body}",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(OpenboxError) as ei:
        load_openbox(path)
    msg = str(ei.value)
    assert secret_body not in msg
    assert "token_ref" in msg
    # Also exercise check path (rc != 0, no secret echo).
    rc = cmd_openbox_check(_ns_check(file=str(path), policy=str(tmp_path / "nope.yaml")))
    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert secret_body not in combined
    assert "token_ref" in combined
    assert "Traceback" not in combined
