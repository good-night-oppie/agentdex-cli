"""Subscription-CLI judge clients — Claude Code / Codex as soft Oracle backends.

Per user direction 2026-06-08: when no API key is reachable but the user is
OAuth-authed via subscription CLIs (Claude Code / Codex / Antigravity), the
soft Oracle can shell out to those CLIs instead of failing.

These clients expose the Anthropic-shape ``.messages.create(model, system,
messages, max_tokens)`` and the Gemini-shape ``.models.generate_content(model,
contents, config)`` so they slot into :class:`LlmJudgeOracle` without
backend-specific branching.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess

log = logging.getLogger(__name__)


_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}", re.DOTALL)


class _Block:
    def __init__(self, text: str):
        self.text = text


class _Message:
    def __init__(self, text: str):
        self.content = [_Block(text)]


class _SimpleResponse:
    def __init__(self, text: str):
        self.text = text


class ClaudeCodeJudgeClient:
    """Run ``claude -p`` non-interactively as the soft Oracle judge.

    Uses the locally-installed Claude Code subscription. No API key required.
    ``model`` arg overrides the CLI's default; ``--output-format json`` is
    requested but the body is best-effort parsed (we strip the JSON object
    out even when surrounded by chatter).
    """

    def __init__(self, bin_: str | None = None, default_model: str | None = None):
        self._bin = bin_ or os.environ.get("CLAUDE_BIN", "claude")
        self._default_model = default_model
        self.messages = self
        self.models = self

    # ---- Anthropic-shape -----
    def create(self, *, model, max_tokens=None, system=None, messages, **_):
        text_parts = []
        if system:
            text_parts.append(f"[SYSTEM]\n{system}\n[/SYSTEM]")
        for m in messages:
            content = m.get("content")
            if isinstance(content, list):
                content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
            text_parts.append(f"[{m.get('role', 'user').upper()}]\n{content}")
        prompt = "\n\n".join(text_parts)
        out = self._invoke(model, prompt)
        return _Message(out)

    # ---- Gemini-shape -----
    def generate_content(self, *, model, contents, config=None):
        sys_inst = (config or {}).get("system_instruction") if config else None
        prompt = f"[SYSTEM]\n{sys_inst}\n[/SYSTEM]\n\n{contents}" if sys_inst else contents
        out = self._invoke(model, prompt)
        return _SimpleResponse(out)

    def _invoke(self, model: str, prompt: str) -> str:
        argv = [
            self._bin,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--max-turns",
            "1",
            "--dangerously-skip-permissions",
        ]
        if model and model.startswith("claude-") and not model.startswith("claude-code"):
            argv += ["--model", model]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        # Hard-separate stdout (the channel that carries the JSON envelope)
        # from stderr (warnings, rate-limit chatter). Never parse stderr as
        # if it were the judge verdict — that path silently turns warnings
        # into JSON-decode failures that downstream code reads as
        # "uncertainty=1.0, pass=False" without any clue why.
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        text = self._extract_result(stdout)
        if text:
            return text
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude code exec failed ({proc.returncode}): {(stderr or stdout)[:500]}"
            )
        if stderr.strip():
            raise RuntimeError(
                "claude code exec returned 0 with empty stdout but non-empty "
                f"stderr: {stderr[:500]}"
            )
        return stdout

    @staticmethod
    def _extract_result(raw: str) -> str:
        """Pull the assistant text out of either the JSON-array or single-JSON envelope."""
        if not raw.strip():
            return ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        if isinstance(payload, dict):
            return payload.get("result") or payload.get("text") or payload.get("content") or ""
        if isinstance(payload, list):
            # Walk in reverse — the result frame is last.
            for frame in reversed(payload):
                if not isinstance(frame, dict):
                    continue
                if frame.get("type") == "result" and frame.get("result"):
                    return str(frame["result"])
                if frame.get("type") == "assistant":
                    msg = frame.get("message") or {}
                    content = msg.get("content") or []
                    parts = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    joined = "\n".join(p for p in parts if p)
                    if joined:
                        return joined
        return ""


class CodexJudgeClient:
    """Run ``codex exec`` non-interactively as the soft Oracle judge."""

    def __init__(self, bin_: str | None = None):
        self._bin = bin_ or os.environ.get("CODEX_BIN", "codex")
        self.messages = self
        self.models = self

    def create(self, *, model, max_tokens=None, system=None, messages, **_):
        text_parts = []
        if system:
            text_parts.append(f"[SYSTEM]\n{system}\n[/SYSTEM]")
        for m in messages:
            content = m.get("content")
            if isinstance(content, list):
                content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
            text_parts.append(f"[{m.get('role', 'user').upper()}]\n{content}")
        return _Message(self._invoke("\n\n".join(text_parts)))

    def generate_content(self, *, model, contents, config=None):
        sys_inst = (config or {}).get("system_instruction") if config else None
        prompt = f"[SYSTEM]\n{sys_inst}\n[/SYSTEM]\n\n{contents}" if sys_inst else contents
        return _SimpleResponse(self._invoke(prompt))

    def _invoke(self, prompt: str) -> str:
        argv = [self._bin, "exec", "--full-auto", prompt]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=180)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        if proc.returncode != 0:
            raise RuntimeError(
                f"codex exec failed ({proc.returncode}): {stderr[:400] or stdout[:400]}"
            )
        if not stdout.strip() and stderr.strip():
            raise RuntimeError(
                f"codex exec returned 0 with empty stdout but non-empty stderr: {stderr[:500]}"
            )
        return stdout


def subscription_judge_factory(judge_llm: str):
    """Pick a subscription judge based on the model id prefix.

    Codereview L4 (2026-06-08): when ``judge_llm`` does not match a known
    prefix the factory falls back to Claude Code so legacy callers keep
    working. The fallback is logged at WARNING so a typo (``clade-haiku``)
    does not silently incur a Claude Code subscription charge.
    """
    lower = judge_llm.lower()
    if lower.startswith(("claude-", "claude code", "claude_code")):
        return ClaudeCodeJudgeClient(default_model=judge_llm)
    if lower.startswith(("gpt-", "o1-", "o3-", "o4-", "codex")):
        return CodexJudgeClient()
    log.warning(
        "subscription_judge_factory: no prefix match for %r — defaulting to "
        "ClaudeCodeJudgeClient. Set judge_llm to a known model id "
        "(claude-* / gpt-* / o1-* / o3-* / o4-* / codex*) to silence this.",
        judge_llm,
    )
    return ClaudeCodeJudgeClient(default_model=judge_llm)


__all__ = [
    "ClaudeCodeJudgeClient",
    "CodexJudgeClient",
    "subscription_judge_factory",
]
