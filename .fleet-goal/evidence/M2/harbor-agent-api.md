---
title: "Harbor custom-agent API capture (M2 WU-9)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal/evidence/M2
layer: cross-cutting
cross_cutting: true
---

# Harbor custom-agent API (verbatim)

Captured from installed `harbor` 0.18.0
(`uv tool` venv at
`~/.config/model_route/grok-profile/.local/share/uv/tools/harbor`).

## Contract used by WU-9 `tb2-noop`

| Need | Real surface (harbor 0.18.0) | Notes |
|------|------------------------------|-------|
| CLI agent flag | `-a` / `--agent` | Accepts builtin name **or** `module.path:ClassName` |
| Import resolution | `harbor.utils.import_path.import_symbol` | `importlib.import_module(module_path)` then `getattr(module, ClassName)` |
| Base class | `harbor.agents.base.BaseAgent` | Abstract: `name`, `version`, `setup`, `run` |
| Constructor kwargs | `logs_dir: Path`, `model_name: str \| None = None`, … | Factory always passes `logs_dir=` + optional `model_name=` / `extra_env=` |
| Builtin no-op reference | `harbor.agents.nop:NopAgent` (`-a nop`) | `setup`/`run` are empty `pass` — our custom agent mirrors this |
| Builtin oracle | `harbor.agents.oracle:OracleAgent` (`-a oracle`) | Replays task `solution/` script — **no LLM**, $0 |

### Import-path requirement (load-bearing)

Harbor does **not** add the candidate directory to `sys.path`. A custom agent
is importable only when its module is already on `PYTHONPATH` (or installed
into the harbor venv). For the WU-9 candidate-pipe leg:

```bash
export PYTHONPATH=".fleet-goal/evidence/M2/candidates/tb2-noop${PYTHONPATH:+:$PYTHONPATH}"
# entrypoint in candidate.yaml: tb2_noop:Tb2NoopAgent
```

`HarborCliClient` passes `candidate.entrypoint` as `-a` (unless
`agent_import_path=` overrides). Subprocess inherits the parent environment,
so exporting `PYTHONPATH` before `adx measure` is sufficient.

### Task discovery (WU-9)

`harbor dataset list` lists registries, not task ids. Discovery used:

```bash
harbor dataset download terminal-bench-sample@2.0 --export -o /tmp/harbor-tb2-export
# → task directory names under terminal-bench-sample/
ls /tmp/harbor-tb2-export/terminal-bench-sample/
# chess-best-move  configure-git-webserver  fix-code-vulnerability
# log-summary-date-ranges  polyglot-c-py  qemu-alpine-ssh  qemu-startup
# regex-log  sqlite-with-gcov  build-cython-ext
```

**Surprise:** bare short names like `regex-log` match the sample export dirs
and `--print-config` filter echo, but
`terminal-bench/terminal-bench-2` package task ids are **org-prefixed**.
`-i regex-log` raises `ValueError: No tasks matched` and prints examples
like `terminal-bench/adaptive-rejection-sampler`. Correct filter:

```bash
harbor run -d terminal-bench/terminal-bench-2 \
  -i 'terminal-bench/regex-log' -a oracle -l 1 -n 1 --print-config
# datasets[0].task_names == ["terminal-bench/regex-log"]
```

Chosen task for both $0 legs: **`terminal-bench/regex-log`**.

### HarborCliClient job_name slash hazard (WU-8 client)

`HarborCliClient.run_task` builds
`job_name = f"adx-{task_id}-{uuid}"` and opens
`jobs_dir / f"{job_name}.harbor.log"`. Org-prefixed package ids embed
`/`, so `open()` raises `FileNotFoundError` (parent dir never created).

WU-9 `measure_cmd --harbor-tasks` rewrites `org/name` → `*name` before
constructing the client (Harbor `-i` accepts globs; single-trial result
parse still works via `_find_trial_result` fallback). Durable fix belongs
in `harbor_cli.py` (sanitize job_name independently of `-i`).

## Real-run summaries (WU-9 ops)

### Oracle leg (`-a oracle`, no LLM)

```
task: terminal-bench/regex-log
passed: true (verifier reward 1.0)
wall_clock_sec: 39
harbor_version: 0.18.0
job_dir: .fleet-goal/evidence/M2/measured/wu9-oracle-jobs/wu9-oracle
```

### Candidate-pipe leg (`adx measure --engine harbor-cli`, custom `tb2_noop:Tb2NoopAgent`)

```
quality: 0.0
cost_dollar: 0.01          # declared-budget fallback (agent_result.cost_usd was null)
cost_is_measured: false
receipt: tier=self_reported kind=raw_artifacts
wall_clock_sec: ~34.4
PYTHONPATH: .fleet-goal/evidence/M2/candidates/tb2-noop
--harbor-tasks terminal-bench/regex-log  → client saw *regex-log (slash-safe)
```

### Budget gate note

WU-1 `AgentCandidate.validate()` rejects `budget.usd <= 0`. Declared
`usd: 0.01` (smallest practical >0 ceiling) for the $0-intent no-op
candidate; measured `cost_dollar` still comes from Harbor trial
`agent_result.cost_usd` when present.

## Background

Verbatim upstream excerpts (harbor 0.18.0) — quoted reference text,
not SLA claims by this repo.

### `harbor.utils.import_path` (IMPORT_PATH_FORMAT + import_symbol)

```
IMPORT_PATH_FORMAT = "module.path:ClassName"


def import_symbol(import_path: str) -> Any:
    if ":" not in import_path:
        raise ValueError(f"Import path must be in format '{IMPORT_PATH_FORMAT}'")

    module_path, symbol_name = import_path.split(":", 1)
    if not module_path or not symbol_name:
        raise ValueError(f"Import path must be in format '{IMPORT_PATH_FORMAT}'")

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ValueError(f"Failed to import module '{module_path}': {exc}") from exc

    try:
        return getattr(module, symbol_name)
    except AttributeError as exc:
        raise ValueError(
            f"Module '{module_path}' has no class '{symbol_name}'"
        ) from exc
```

### `AgentFactory.create_agent_from_import_path` + unified `--agent`

```
@classmethod
def create_agent_from_import_path(
    cls,
    import_path: str,
    logs_dir: Path,
    model_name: str | None = None,
    **kwargs,
) -> "BaseAgent":
    """
    Create an agent from an import path.

    Args:
        import_path (str): The import path of the agent. In the format
            'module.path:ClassName'.
    ...
    """
    agent_class = _import_agent_class(import_path)
    return agent_class(logs_dir=logs_dir, model_name=model_name, **kwargs)
```

From `create_agent_from_config` (unified `-a`):

```
# `--agent` is unified, so `name` may carry a custom-agent import path
# ('module.path:ClassName'); treat it as the import path in that case.
if (
    import_path is None
    and name is not None
    and ":" in name
    and not is_acp_registry_shorthand(name)
):
    import_path, name = name, None
```

### `BaseAgent` abstract surface (`harbor/agents/base.py`)

```
class BaseAgent(ABC):
    ...
    def __init__(
        self,
        logs_dir: Path,
        model_name: str | None = None,
        logger: logging.Logger | None = None,
        mcp_servers: list[MCPServerConfig]
        | None = None,  # MCP servers from task config; see setup()/run() for usage
        skills_dir: str | None = None,  # Skills directory path in the environment
        *args,
        extra_env: dict[str, str] | None = None,
        **kwargs,
    ):
        self.logs_dir = logs_dir
        self.model_name = model_name
        ...

    @staticmethod
    @abstractmethod
    def name() -> str:
        """The name of the agent."""

    @abstractmethod
    def version(self) -> str | None:
        """The version of the agent."""

    @classmethod
    def import_path(cls) -> str:
        """
        The import path of the agent. Formatted as 'some.import.path:AgentClass'.
        """
        return f"{cls.__module__}:{cls.__name__}"

    @abstractmethod
    async def setup(self, environment: BaseEnvironment) -> None:
        """
        Run commands to setup the agent & its tools.
        ...
        """

    @abstractmethod
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """
        Runs the agent in the environment. Be sure to populate the context with the
        results of the agent execution. ...
        """
```

### Builtin `NopAgent` (`harbor/agents/nop.py`) — reference no-op

```
class NopAgent(BaseAgent):
    SUPPORTS_WINDOWS: bool = True

    @staticmethod
    @override
    def name() -> str:
        return AgentName.NOP.value

    @override
    def version(self) -> str:
        return "1.0.0"

    @override
    async def setup(self, environment: BaseEnvironment) -> None:
        pass

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        pass
```
