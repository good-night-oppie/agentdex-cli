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
DEFAULT_ARENA_PROXY_URL = "https://space.ai-builders.com/backend/v1"


@dataclass(frozen=True)
class ProxyConfig:
    base_url: str
    token: str
    token_env: str


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


def _provider_candidates() -> list[tuple[str, str, str | None]]:
    return [
        ("ADX_BUILDER_PROXY_URL", "AI_BUILDER_TOKEN", None),
        ("AI_BUILDER_PROXY_URL", "AI_BUILDER_TOKEN", None),
        ("PURE100_PROXY_URL", "PURE100_PROXY_KEY", None),
        ("OPENAI_BASE_URL", "OPENAI_API_KEY", None),
    ]


def _select_proxy_config(base_url: str | None, token_env: str | None) -> ProxyConfig:
    token_envs = [name.strip() for name in (token_env or "").split(",") if name.strip()]
    if base_url:
        selected_token_envs = token_envs or [
            candidate_token
            for env_name, candidate_token, default_url in _provider_candidates()
            if base_url == os.environ.get(env_name)
            or (default_url is not None and base_url == default_url)
        ]
        if not selected_token_envs and base_url == DEFAULT_ARENA_PROXY_URL:
            selected_token_envs = ["AI_BUILDER_TOKEN"]
        if not selected_token_envs:
            raise SystemExit(
                "explicit --base-url requires --token-env so the bearer token matches the proxy"
            )
        token_name = next((name for name in selected_token_envs if os.environ.get(name)), None)
        if token_name is None:
            raise SystemExit(
                f"missing bearer token; set one of {','.join(selected_token_envs)} for proxy {base_url}"
            )
        token = os.environ[token_name]
        return ProxyConfig(base_url=base_url, token=token, token_env=token_name)

    for url_env, provider_token_env, _default_url in _provider_candidates():
        candidate_url = os.environ.get(url_env)
        if candidate_url:
            token = os.environ.get(provider_token_env)
            if not token:
                raise SystemExit(
                    f"missing bearer token; set {provider_token_env} for proxy from {url_env}"
                )
            return ProxyConfig(base_url=candidate_url, token=token, token_env=provider_token_env)
    if os.environ.get("AI_BUILDER_TOKEN"):
        return ProxyConfig(
            base_url=DEFAULT_ARENA_PROXY_URL,
            token=os.environ["AI_BUILDER_TOKEN"],
            token_env="AI_BUILDER_TOKEN",
        )
    raise SystemExit(
        "missing proxy config; set ADX_BUILDER_PROXY_URL + AI_BUILDER_TOKEN, "
        "AI_BUILDER_TOKEN for the arena default proxy, PURE100_PROXY_URL + "
        "PURE100_PROXY_KEY, OPENAI_BASE_URL + OPENAI_API_KEY, or --base-url + --token-env"
    )


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
    idx = min(len(values) - 1, max(0, math.ceil(len(values) * pct) - 1))
    return round(sorted(values)[idx], 1)


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
    start_event = threading.Event()

    def _worker() -> list[RequestResult]:
        start_event.wait()
        return [
            _one_chat(
                url,
                token=token,
                model=model,
                prompt=prompt,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            for _ in range(requests_per_worker)
        ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=level) as executor:
        futures = [executor.submit(_worker) for _ in range(level)]
        start_event.set()
        results = [
            result
            for future in concurrent.futures.as_completed(futures)
            for result in future.result()
        ]
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
            "Proxy base URL. Defaults to ADX_BUILDER_PROXY_URL, AI_BUILDER_PROXY_URL, "
            "AI_BUILDER_TOKEN with the arena default proxy, PURE100_PROXY_URL, or OPENAI_BASE_URL."
        ),
    )
    parser.add_argument(
        "--token-env",
        default=None,
        help="Bearer token env var. Required with custom --base-url when the provider cannot be inferred.",
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

    proxy = _select_proxy_config(args.base_url, args.token_env)

    levels = [int(item) for item in args.levels.split(",") if item.strip()]
    if not levels or any(level < 1 for level in levels):
        raise SystemExit("--levels must contain positive integers")
    if args.requests_per_worker < 1:
        raise SystemExit("--requests-per-worker must be >= 1")

    chat_url = _join_url(proxy.base_url, args.endpoint)
    usage_url = _join_url(proxy.base_url, args.usage_endpoint)
    print(
        "# llm proxy fan-out measure "
        f"base={_redact_url(proxy.base_url)} endpoint={args.endpoint} "
        f"token_env={proxy.token_env} model={args.model} levels={levels} "
        f"requests_per_worker={args.requests_per_worker}"
    )
    if args.dry_run:
        print("DONE_JSON " + json.dumps({"ok": True, "dry_run": True, "levels": levels}))
        return 0

    usage_before = None if args.skip_usage else _usage_summary(usage_url, proxy.token, args.timeout)
    rows = []
    for level in levels:
        row = _run_level(
            level,
            requests_per_worker=args.requests_per_worker,
            url=chat_url,
            token=proxy.token,
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
    usage_after = None if args.skip_usage else _usage_summary(usage_url, proxy.token, args.timeout)
    print(
        "DONE_JSON "
        + json.dumps(
            {
                "ok": True,
                "base_url": _redact_url(proxy.base_url),
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
