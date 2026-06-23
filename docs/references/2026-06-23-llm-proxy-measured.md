---
title: "LLM proxy fan-out - blocked measurement evidence (ADR-0012 must-measure #3)"
status: active
owner: "@EdwardTang"
created: 2026-06-23
updated: 2026-06-23
type: reference
scope: scripts
layer: cross-cutting
cross_cutting: true
---

# LLM proxy fan-out - blocked measurement evidence

ADR-0012 must-measure #3 is the LLM-decision fan-out probe: platform proxy
rate/budget behavior at 100 concurrent `/v1/chat/completions` requests. This is
separate from the already-measured sim-tier load test in
`docs/references/2026-06-17-arena-loadtest-measured.md`.

## Tool

`scripts/llm_proxy_measure.py` sends cheap OpenAI-compatible chat-completion
requests through the configured proxy. It reads:

- proxy base URL: `AI_BUILDER_PROXY_URL`, `PURE100_PROXY_URL`, or `OPENAI_BASE_URL`
- bearer token: `AI_BUILDER_TOKEN`, `PURE100_PROXY_KEY`, or `OPENAI_API_KEY`
- model: `LLM_PROXY_MODEL`, defaulting to the currently advertised lightweight
  alias `haiko`

The script redacts the proxy URL and never prints the bearer token.

## Run on this host

Date: 2026-06-23.

Local gates:

```bash
python3 -m py_compile scripts/llm_proxy_measure.py
uv run --no-sync ruff check scripts/llm_proxy_measure.py
python3 scripts/llm_proxy_measure.py --dry-run
```

Proxy discovery:

- `GET /v1/models` succeeded.
- Advertised models: `fabo`, `oppo`, `haiko`.
- `GET /v1/usage/summary` returned `404 Not Found` on this endpoint.

Chat probes:

| model | command shape | result |
|---|---|---|
| `gpt-4.1-nano` | `--levels 1,2 --skip-usage` | 502, `unknown provider for model gpt-4.1-nano` |
| `fabo` | `--levels 1 --skip-usage` | 403, `INSUFFICIENT_BALANCE` |
| `oppo` | `--levels 1 --skip-usage` | 403, `INSUFFICIENT_BALANCE` |
| `haiko` | `--levels 1,2 --skip-usage` | N=1: 403 `INSUFFICIENT_BALANCE`; N=2: 503 `auth_unavailable` |

## Finding

The platform proxy is reachable and model discovery works, but all advertised
chat models fail before any concurrency measurement can begin. The 100-concurrent
LLM fan-out datapoint is blocked on upstream provider balance/auth, not arena
code or sim-tier capacity.

Action needed before rerun: restore a funded/upstream-authenticated provider for
one advertised proxy model, then run:

```bash
python3 scripts/llm_proxy_measure.py --model haiko --levels 1,2,4,8,16,32,64,100 --requests-per-worker 1 --timeout 60 --skip-usage
```

Remove `--skip-usage` only after `/v1/usage/summary` is available on the active
proxy.
