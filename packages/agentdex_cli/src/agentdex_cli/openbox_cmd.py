"""``adx openbox`` — bind pool model names to invokable backends (v3 MVP #3).

``adx interview`` captures a pool of model NAMES; nothing binds a name to an
invokable backend. Openbox is that binding — declared self-service by the
user, holding ZERO credential values (BYO-creds: agentdex never holds user
creds; fleet secrets discipline: no secret value may land in a file that
panes/logs can quote).

``.agentdex/openbox.yaml`` is TRUSTED LOCAL CONFIG — ``probe`` argvs execute
as local commands (same trust level as a Makefile); do not run
``adx openbox check`` against an untrusted repo's openbox.yaml.

stdlib + PyYAML only. Imports ``load_policy`` / ``_policy_list`` from
``run_cmd`` (no copy).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from agentdex_cli.run_cmd import _policy_list, _yaml_loc, load_policy

# --------------------------------------------------------------------------- #
# constants
# --------------------------------------------------------------------------- #
KNOWN_KINDS = frozenset({"subscription-cli", "anthropic-endpoint", "openai-endpoint"})
SECRET_RE = re.compile(
    r"("
    r"sk-[A-Za-z0-9-]{8,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|glpat-[A-Za-z0-9_-]{15,}"
    r"|xoxb-"
    r"|AKIA[0-9A-Z]{12,}"
    r"|AIza[0-9A-Za-z_-]{30,}"
    r"|Bearer\s+[A-Za-z0-9._~+/-]{16,}"
    r"|eyJ[A-Za-z0-9_-]{20,}"
    r"|[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^@\s]+@"
    r")",
    re.IGNORECASE,
)
TOKEN_REF_RE = re.compile(r"^(none|env:[A-Za-z_][A-Za-z0-9_]*|file:/.+)$")
PROBE_TIMEOUT_SEC = 10


class OpenboxError(ValueError):
    """Validation / load failure — message is safe to print (no secret echo)."""


# --------------------------------------------------------------------------- #
# heuristics + skeleton
# --------------------------------------------------------------------------- #
def _heuristic(name: str) -> dict[str, Any]:
    """Known-name probe/invoke heuristics (case-insensitive substring match)."""
    low = name.lower()
    if "claude" in low:
        return {
            "kind": "subscription-cli",
            "probe": ["claude", "--version"],
            "invoke": "claude",
            "token_ref": "none",
        }
    if "codex" in low:
        return {
            "kind": "subscription-cli",
            "probe": ["codex", "--version"],
            "invoke": "codex",
            "token_ref": "none",
        }
    if "manus" in low:
        return {
            "kind": "subscription-cli",
            "probe": ["manus", "--version"],
            "invoke": "manus",
            "token_ref": "none",
        }
    return {
        "kind": "subscription-cli",
        "probe": [],
        "invoke": name,
        "token_ref": "none",
    }


def render_openbox(pool: list[str]) -> dict[str, Any]:
    """Build a skeleton openbox document for every pool name."""
    return {
        "version": 1,
        "backends": {name: _heuristic(name) for name in pool},
    }


# --------------------------------------------------------------------------- #
# load + validate
# --------------------------------------------------------------------------- #
def _field_looks_secret(value: str) -> bool:
    return SECRET_RE.search(value) is not None


def _check_string_field(backend: str, field: str, value: str) -> None:
    if _field_looks_secret(value):
        raise OpenboxError(
            f"backend {backend!r} field {field!r} looks like a credential value — "
            "use a reference (none | env:NAME | file:/abs/path), never the value itself"
        )


def _scan_strings(backend: str, field_path: str, value: Any) -> None:
    """Recursively reject any string (value or dict key) matching SECRET_RE."""
    if isinstance(value, str):
        if field_path:
            _check_string_field(backend, field_path, value)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and _field_looks_secret(k):
                raise OpenboxError(
                    f"backend {backend!r}: a field key matches a credential pattern "
                    "(offending key not shown)"
                )
            child = f"{field_path}.{k}" if field_path else str(k)
            _scan_strings(backend, child, v)
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            _scan_strings(backend, f"{field_path}[{i}]", item)


def _validate_token_ref(backend: str, token_ref: Any) -> None:
    if not isinstance(token_ref, str):
        raise OpenboxError(f"backend {backend!r} field 'token_ref': must be a string")
    _check_string_field(backend, "token_ref", token_ref)
    if TOKEN_REF_RE.match(token_ref) is None:
        raise OpenboxError(
            f"backend {backend!r} field 'token_ref': token_ref holds a reference, "
            "never a secret value"
        )


def _warn_file_ref(token_ref: str) -> None:
    """Non-fatal stderr warn when file: path missing or mode is not 0600."""
    if not token_ref.startswith("file:"):
        return
    path = Path(token_ref[len("file:") :])
    if SECRET_RE.search(str(path)):
        print(
            "warning: token_ref file path matches a credential pattern — "
            "path withheld; use a plain file path",
            file=sys.stderr,
        )
        return
    if not path.exists():
        print(f"warning: token_ref file does not exist: {path}", file=sys.stderr)
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o600:
        print(
            f"warning: token_ref file mode is {mode:04o}, expected 0600: {path}",
            file=sys.stderr,
        )


def _validate_backend(name: str, entry: Any) -> None:
    if not isinstance(entry, dict):
        raise OpenboxError(f"backend {name!r}: entry must be a mapping")
    kind = entry.get("kind")
    if kind not in KNOWN_KINDS:
        raise OpenboxError(
            f"backend {name!r}: unknown kind (allowed: "
            "subscription-cli, anthropic-endpoint, openai-endpoint)"
        )
    if "invoke" not in entry or entry.get("invoke") in (None, ""):
        raise OpenboxError(f"backend {name!r}: missing invoke")
    invoke = entry.get("invoke")
    if invoke is not None and not isinstance(invoke, str):
        raise OpenboxError(f"backend {name!r} field 'invoke': must be a string")

    probe = entry.get("probe", [])
    if probe is None:
        probe = []
    if not isinstance(probe, list) or not all(isinstance(x, str) for x in probe):
        raise OpenboxError(f"backend {name!r}: probe must be a list of strings")

    _scan_strings(name, "", entry)

    token_ref = entry.get("token_ref", "none")
    _validate_token_ref(name, token_ref if token_ref is not None else "none")
    if isinstance(token_ref, str):
        _warn_file_ref(token_ref)


def load_openbox(path: Path) -> dict[str, Any]:
    """Load and validate ``openbox.yaml``. Raises ``OpenboxError`` / FileNotFoundError."""
    if not path.exists():
        raise FileNotFoundError(f"no openbox config at {path} — run `adx openbox init` first")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise OpenboxError(
            f"invalid YAML in openbox at {path}{_yaml_loc(exc)} — fix the file"
        ) from None
    if not isinstance(doc, dict):
        raise OpenboxError(f"openbox at {path} must be a YAML mapping")
    version = doc.get("version")
    if version != 1:
        if isinstance(version, int):
            raise OpenboxError(f"openbox.yaml version must be 1 (got {version})")
        raise OpenboxError("openbox.yaml version must be 1 (got a non-integer value)")
    backends = doc.get("backends")
    if not isinstance(backends, dict):
        raise OpenboxError("openbox.yaml 'backends' must be a mapping")
    for name, entry in backends.items():
        name_str = str(name)
        if _field_looks_secret(name_str):
            raise OpenboxError(
                "a backend name matches a credential pattern — backend names must not "
                "hold secrets (offending name not shown)"
            )
        _validate_backend(name_str, entry)
    return doc


# --------------------------------------------------------------------------- #
# probe
# --------------------------------------------------------------------------- #
def probe_backend(entry: dict[str, Any]) -> str:
    """Return status: UNPROBED | MISSING | READY | NO-AUTH | TIMEOUT."""
    probe = entry.get("probe") or []
    if not probe:
        return "UNPROBED"
    cmd0 = probe[0]
    if shutil.which(cmd0) is None:
        return "MISSING"
    try:
        proc = subprocess.run(
            probe,
            shell=False,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SEC,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except OSError:
        return "MISSING"
    if proc.returncode == 0:
        return "READY"
    return "NO-AUTH"


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_openbox_init(args: argparse.Namespace) -> int:
    out = Path(args.out).expanduser()
    if out.exists() and not args.force:
        print(f"refusing to overwrite existing openbox at {out} (pass --force)")
        return 2
    try:
        policy = load_policy(Path(args.policy).expanduser())
    except (FileNotFoundError, ValueError, OpenboxError) as exc:
        print(str(exc))
        return 2
    pool = _policy_list(policy.get("pool"))
    doc = render_openbox(pool)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        yaml.safe_dump(doc, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    print(f"wrote openbox skeleton → {out}  ({len(pool)} backend(s))")
    print("next: fill token_ref / base_url as needed, then `adx openbox check`.")
    return 0


def cmd_openbox_check(args: argparse.Namespace) -> int:
    path = Path(args.file).expanduser()
    try:
        doc = load_openbox(path)
    except (FileNotFoundError, ValueError, OpenboxError) as exc:
        print(str(exc))
        return 2

    backends: dict[str, Any] = doc.get("backends") or {}
    statuses: dict[str, str] = {}
    for name, entry in backends.items():
        statuses[str(name)] = probe_backend(entry if isinstance(entry, dict) else {})

    # Human lines (aligned) — iterate original items so non-string keys keep kind.
    if statuses:
        width = max(len(n) for n in statuses)
        for name, entry in backends.items():
            name_str = str(name)
            status = statuses[name_str]
            kind = entry.get("kind", "?") if isinstance(entry, dict) else "?"
            print(f"{name_str:<{width}}  {status:<8}  {kind}")

    # Pool coverage.
    policy_path = Path(args.policy).expanduser()
    pool_covered: bool | None
    empty_pool = False
    if not policy_path.exists():
        print(f"pool coverage: skipped (no policy at {policy_path})")
        pool_covered = None
        exit_ok = True
    else:
        try:
            policy = load_policy(policy_path)
        except (FileNotFoundError, ValueError, OpenboxError):
            print(f"pool coverage: skipped (unreadable policy at {policy_path})")
            pool_covered = None
            exit_ok = True
        else:
            pool = _policy_list(policy.get("pool"))
            if not pool:
                print("policy has an empty pool — run `adx interview` to set one")
                pool_covered = None
                exit_ok = False
                empty_pool = True
            else:
                ready_count = 0
                for pname in pool:
                    if statuses.get(pname) == "READY":
                        ready_count += 1
                print(f"pool coverage: {ready_count}/{len(pool)} pool names have a READY backend")
                pool_covered = ready_count == len(pool)
                exit_ok = pool_covered

    if args.json:
        payload = {"backends": statuses, "pool_covered": pool_covered}
        print(json.dumps(payload))

    if empty_pool:
        return 2
    return 0 if exit_ok else 1


def register_openbox_parser(subs: argparse._SubParsersAction) -> None:
    p = subs.add_parser(
        "openbox",
        help="bind pool model names to invokable backends (self-service, zero creds)",
    )
    openbox_subs = p.add_subparsers(dest="openbox_cmd", required=True)

    init_p = openbox_subs.add_parser(
        "init",
        help="seed .agentdex/openbox.yaml from the interview policy pool",
    )
    init_p.add_argument(
        "--policy",
        default=".agentdex/orchestration.yaml",
        help="orchestration policy from `adx interview`",
    )
    init_p.add_argument(
        "--out",
        default=".agentdex/openbox.yaml",
        help="where to write the openbox skeleton",
    )
    init_p.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing openbox file",
    )
    init_p.set_defaults(func=cmd_openbox_init)

    check_p = openbox_subs.add_parser(
        "check",
        help="probe each backend (liveness/auth, zero spend) and report pool coverage",
    )
    check_p.add_argument(
        "--file",
        default=".agentdex/openbox.yaml",
        help="openbox config to check",
    )
    check_p.add_argument(
        "--policy",
        default=".agentdex/orchestration.yaml",
        help="orchestration policy (for pool coverage)",
    )
    check_p.add_argument("--json", action="store_true", help="also emit a JSON summary")
    check_p.set_defaults(func=cmd_openbox_check)
