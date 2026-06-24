#!/usr/bin/env python3
"""Measure ADR-0012 must-measure #3: LLM proxy fan-out under concurrency.

The arena sim tier is already measured by ``scripts/arena_loadtest.py``. This
probe isolates the expected bottleneck: concurrent OpenAI-compatible
``/chat/completions`` calls through the shared platform proxy.

Defaults are intentionally cheap: a tiny prompt and ``max_tokens=1``. Increase
``--levels`` to include 100 for the production go/no-go measurement.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_LEVELS = "1,2,4,8,16,32,64,100"

# (base-URL env, matching bearer-token env) — selected as a PAIR so the token always
# matches the proxy it is sent to. Resolving them independently could send e.g.
# AI_BUILDER_TOKEN to OPENAI_BASE_URL — leaking the credential to the wrong service AND
# measuring a different proxy than the production decision path (#528 review).
_PROXY_PROVIDERS: list[tuple[str, str]] = [
    ("AI_BUILDER_PROXY_URL", "AI_BUILDER_TOKEN"),
    ("ADX_BUILDER_PROXY_URL", "AI_BUILDER_TOKEN"),
    ("PURE100_PROXY_URL", "PURE100_PROXY_KEY"),
    ("OPENAI_BASE_URL", "OPENAI_API_KEY"),
]
# The arena bridge's default proxy (adx_bridges/showdown_battle_bridge.py) — fall back to
# it so the probe measures the SAME path the arena LLM bridge uses for ADR-0012.
_BRIDGE_DEFAULT_PROXY = "https://space.ai-builders.com/backend/v1"


def _resolve_base_and_token(base_url_arg: str | None, token_env_arg: str) -> tuple[str, str | None]:
    """Resolve (base_url, token) as a matched pair. Default base URL = the first provider
    whose URL env is set, else the bridge default; the token is always the env bound to the
    chosen provider. An explicit --base-url binds the matching provider's token when it is a
    known proxy, else falls back to the explicit --token-env list."""
    base_url = base_url_arg
    token_env: str | None = None
    if not base_url:
        for url_env, tok_env in _PROXY_PROVIDERS:
            if os.environ.get(url_env):
                base_url, token_env = os.environ[url_env], tok_env
                break
        else:
            base_url, token_env = _BRIDGE_DEFAULT_PROXY, "AI_BUILDER_TOKEN"
    else:
        for url_env, tok_env in _PROXY_PROVIDERS:
            if os.environ.get(url_env) == base_url:
                token_env = tok_env
                break
    if token_env is not None:
        return base_url, os.environ.get(token_env)
    # base_url is not a known provider — fall back to the explicit token-env search
    return base_url, _env_first([n.strip() for n in token_env_arg.split(",") if n.strip()])


@dataclass(frozen=True)
class RequestResult:
    ok: bool
    status: int | None
    latency_ms: float
    retry_after: str | None = None
    error: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


def _env_first(names: list[str]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    endpoint = path if path.startswith("/") else f"/{path}"
    if base.endswith("/v1") and endpoint.startswith("/v1/"):
        endpoint = endpoint[3:]
    return base + endpoint


def _redact_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.netloc
    if "@" in host:
        host = "***@" + host.rsplit("@", 1)[1]
    path_hint = "/..." if parsed.path and parsed.path != "/" else ""
    return urllib.parse.urlunsplit((parsed.scheme, host, path_hint, "", ""))


def _request_json(
    method: str,
    url: str,
    *,
    token: str,
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw) if raw else {}
        return resp.status, data, dict(resp.headers.items())


def _chat_payload(model: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }


def _one_chat(
    url: str,
    *,
    token: str,
    model: str,
    prompt: str,
    max_tokens: int,
    timeout: float,
) -> RequestResult:
    payload = _chat_payload(model, prompt, max_tokens)
    start = time.monotonic()
    try:
        status, data, headers = _request_json(
            "POST", url, token=token, payload=payload, timeout=timeout
        )
        usage = data.get("usage") if isinstance(data, dict) else {}
        usage = usage if isinstance(usage, dict) else {}
        return RequestResult(
            ok=200 <= status < 300,
            status=status,
            latency_ms=(time.monotonic() - start) * 1000,
            retry_after=headers.get("retry-after") or headers.get("Retry-After"),
            prompt_tokens=_as_int(usage.get("prompt_tokens")),
            completion_tokens=_as_int(usage.get("completion_tokens")),
            total_tokens=_as_int(usage.get("total_tokens")),
        )
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("retry-after") or exc.headers.get("Retry-After")
        detail = exc.read(300).decode("utf-8", errors="replace").strip()
        return RequestResult(
            ok=False,
            status=exc.code,
            latency_ms=(time.monotonic() - start) * 1000,
            retry_after=retry_after,
            error=detail or exc.reason,
        )
    except Exception as exc:
        return RequestResult(
            ok=False,
            status=None,
            latency_ms=(time.monotonic() - start) * 1000,
            error=f"{type(exc).__name__}: {exc}",
        )


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    # Nearest-rank (ceil): the lower-element index int((n-1)*pct) understates the tail
    # on the small samples this probe prints — at n=2 it returned the FASTEST request as
    # p95, at n=4 it ignored the slowest entirely (#528 review). 1-based rank = ceil(pct*n),
    # clamped to [1, n].
    ordered = sorted(values)
    n = len(ordered)
    rank = min(n, max(1, math.ceil(pct * n)))
    return round(ordered[rank - 1], 1)


def _summarize(level: int, results: list[RequestResult]) -> dict[str, Any]:
    oks = [r for r in results if r.ok]
    latencies = [r.latency_ms for r in results]
    status_counts: dict[str, int] = {}
    retry_after_values = sorted({r.retry_after for r in results if r.retry_after})
    errors: dict[str, int] = {}
    for result in results:
        key = str(result.status) if result.status is not None else "transport"
        status_counts[key] = status_counts.get(key, 0) + 1
        if result.error:
            snippet = result.error.replace("\n", " ")[:120]
            errors[snippet] = errors.get(snippet, 0) + 1
    total_tokens = sum(r.total_tokens or 0 for r in results)
    return {
        "concurrency": level,
        "requests": len(results),
        "ok": len(oks),
        "errors": len(results) - len(oks),
        "status_counts": status_counts,
        "latency_ms_p50": _percentile(latencies, 0.50),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "latency_ms_mean": round(statistics.mean(latencies), 1) if latencies else None,
        "retry_after_values": retry_after_values,
        "total_tokens_reported": total_tokens,
        "error_samples": errors,
    }


def _run_level(
    level: int,
    *,
    requests_per_worker: int,
    url: str,
    token: str,
    model: str,
    prompt: str,
    max_tokens: int,
    timeout: float,
) -> dict[str, Any]:
    total = level * requests_per_worker
    # Hold every worker at a shared gate until all `level` are parked, then release them
    # together — otherwise an early future can finish (or be proxy-rejected) before later
    # ones are even submitted, so `--levels N` only caps the pool at N instead of putting
    # N requests simultaneously in flight, under-testing the ADR-0012 fan-out (#528 review).
    start_gate = threading.Event()

    def _gated_chat() -> dict[str, Any]:
        start_gate.wait()
        return _one_chat(
            url,
            token=token,
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=level) as executor:
        futures = [executor.submit(_gated_chat) for _ in range(total)]
        start_gate.set()  # release all queued workers at once
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    return _summarize(level, results)


def _usage_summary(url: str, token: str, timeout: float) -> dict[str, Any] | None:
    try:
        status, data, _headers = _request_json("GET", url, token=token, timeout=timeout)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": 200 <= status < 300, "status": status, "data": data}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "Proxy base URL. Default: the first set of AI_BUILDER_PROXY_URL / "
            "ADX_BUILDER_PROXY_URL / PURE100_PROXY_URL / OPENAI_BASE_URL, else the arena "
            "bridge proxy. The bearer token is bound to the chosen proxy (never mixed)."
        ),
    )
    parser.add_argument(
        "--token-env",
        default="AI_BUILDER_TOKEN,PURE100_PROXY_KEY,OPENAI_API_KEY",
        help="Fallback bearer-token env(s), comma-separated — used only for an explicit "
        "--base-url that is not one of the known proxies.",
    )
    parser.add_argument("--endpoint", default="/v1/chat/completions")
    parser.add_argument("--usage-endpoint", default="/v1/usage/summary")
    parser.add_argument("--model", default=os.environ.get("LLM_PROXY_MODEL", "haiko"))
    parser.add_argument("--levels", default=DEFAULT_LEVELS)
    parser.add_argument("--requests-per-worker", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-tokens", type=int, default=1)
    parser.add_argument("--prompt", default="Reply with exactly: ok")
    parser.add_argument("--skip-usage", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate config without network calls."
    )
    args = parser.parse_args()

    # Resolve base URL + token as a MATCHED pair (no cross-proxy credential leak, #528 review).
    base_url, token = _resolve_base_and_token(args.base_url, args.token_env)
    args.base_url = base_url
    if not base_url:
        raise SystemExit(
            "missing proxy base URL; set AI_BUILDER_PROXY_URL / ADX_BUILDER_PROXY_URL / "
            "PURE100_PROXY_URL / OPENAI_BASE_URL or pass --base-url"
        )
    if not token:
        raise SystemExit(
            f"missing bearer token for proxy {_redact_url(base_url)}; set the matching token "
            f"env (e.g. AI_BUILDER_TOKEN) or --token-env"
        )

    levels = [int(item) for item in args.levels.split(",") if item.strip()]
    if not levels or any(level < 1 for level in levels):
        raise SystemExit("--levels must contain positive integers")
    if args.requests_per_worker < 1:
        raise SystemExit("--requests-per-worker must be >= 1")

    chat_url = _join_url(args.base_url, args.endpoint)
    usage_url = _join_url(args.base_url, args.usage_endpoint)
    print(
        "# llm proxy fan-out measure "
        f"base={_redact_url(args.base_url)} endpoint={args.endpoint} "
        f"model={args.model} levels={levels} requests_per_worker={args.requests_per_worker}"
    )
    if args.dry_run:
        print("DONE_JSON " + json.dumps({"ok": True, "dry_run": True, "levels": levels}))
        return 0

    usage_before = None if args.skip_usage else _usage_summary(usage_url, token, args.timeout)
    rows = []
    for level in levels:
        row = _run_level(
            level,
            requests_per_worker=args.requests_per_worker,
            url=chat_url,
            token=token,
            model=args.model,
            prompt=args.prompt,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
        )
        rows.append(row)
        print(
            f"N={row['concurrency']:>3} requests={row['requests']:>3} ok={row['ok']:>3} "
            f"errors={row['errors']:>3} p50={row['latency_ms_p50']}ms "
            f"p95={row['latency_ms_p95']}ms status={row['status_counts']}"
        )
    usage_after = None if args.skip_usage else _usage_summary(usage_url, token, args.timeout)
    print(
        "DONE_JSON "
        + json.dumps(
            {
                "ok": True,
                "base_url": _redact_url(args.base_url),
                "endpoint": args.endpoint,
                "usage_endpoint": None if args.skip_usage else args.usage_endpoint,
                "model": args.model,
                "levels": rows,
                "usage_before": usage_before,
                "usage_after": usage_after,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
