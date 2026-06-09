"""Hard Oracles — deterministic number / provenance checks.

Per ADR-0009 §Q5: numbers MUST use hard match (regex extract + exact /
tolerance compare). Never LLM-judge a number.

Two oracles ship here:
- :class:`NumberAccuracyOracle` — reads spec.yaml flat numeric keys
  (revenue_total, gross_margin_pct, ...), extracts agent's claim from
  response text, compares per ``tolerance`` / ``tolerance_pp`` rules.
- :class:`ProvenanceOracle` — every claim must carry a
  ``source: <file>:<line>`` annotation; missing → fail.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from agentdex_engine.cards import TaskCard
from agentdex_engine.oracle.base import OracleVerdict, OracleVerdictMap


_DOLLAR_VALUE_RE = re.compile(
    r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(billion|million|B|M)?",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:%|percent|pp|percentage\s+points?)",
    re.IGNORECASE,
)


def _parse_dollar(text: str) -> float | None:
    """Return a number expressed in dollars (NOT billions). ``$30.77 billion`` → 3.077e10."""
    m = _DOLLAR_VALUE_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    val = float(raw)
    unit = (m.group(2) or "").lower()
    if unit.startswith("b"):
        val *= 1e9
    elif unit.startswith("m"):
        val *= 1e6
    return val


def _parse_percent(text: str) -> float | None:
    m = _PERCENT_RE.search(text)
    if not m:
        return None
    return float(m.group(1))


class NumberAccuracyOracle:
    """Reads ``oracle/spec.yaml`` keys + grades the agent's numeric claims."""

    HARD_NUMERIC_TYPES = {"dollar_string", "percent", "dollar_range_string"}
    BOOLEAN_TYPE = "boolean"

    def __init__(self, spec_path: str | Path):
        self.spec_path = Path(spec_path)
        with self.spec_path.open() as f:
            self.spec: dict[str, Any] = yaml.safe_load(f)

    def _grade_dollar(self, response: str, expected: str, key: str) -> OracleVerdict:
        expected_value = _parse_dollar(expected)
        if expected_value is None:
            return OracleVerdict(
                kind="hard",
                **{"pass": False},
                score=0.0,
                evidence=f"spec.yaml::{key}.expected unparseable: {expected!r}",
            )
        # Tolerate any matching dollar expression in the response.
        for match in _DOLLAR_VALUE_RE.finditer(response):
            seen = _parse_dollar(match.group(0))
            if seen is None:
                continue
            if abs(seen - expected_value) / max(expected_value, 1.0) < 0.001:
                return OracleVerdict(
                    kind="hard",
                    **{"pass": True},
                    score=1.0,
                    evidence=f"{key} matched: response={match.group(0)!r} expected={expected!r}",
                )
        return OracleVerdict(
            kind="hard",
            **{"pass": False},
            score=0.0,
            evidence=f"{key} not found or mismatch: expected={expected!r}",
        )

    def _grade_percent(self, response: str, expected: float, key: str, tolerance_pp: float) -> OracleVerdict:
        # Tolerate match against any percent in the response.
        for match in _PERCENT_RE.finditer(response):
            seen = float(match.group(1))
            if abs(seen - expected) <= tolerance_pp + 1e-9:
                return OracleVerdict(
                    kind="hard",
                    **{"pass": True},
                    score=1.0,
                    evidence=f"{key} matched: response={seen}% expected={expected}% ±{tolerance_pp}pp",
                )
        return OracleVerdict(
            kind="hard",
            **{"pass": False},
            score=0.0,
            evidence=f"{key} not found within ±{tolerance_pp}pp of {expected}%",
        )

    def _grade_boolean(self, response: str, expected: bool, key: str, hint: str) -> OracleVerdict:
        # Heuristic: presence-based check using the key's source_hint substrings.
        # For nvidia spec: china_revenue_disclosure_present, blackwell_rubin_mention_present.
        keywords = _keywords_from_key(key)
        found = any(k.lower() in response.lower() for k in keywords) if keywords else False
        passed = (found == expected)
        return OracleVerdict(
            kind="hard",
            **{"pass": passed},
            score=1.0 if passed else 0.0,
            evidence=(
                f"{key} presence={found} expected={expected} "
                f"keywords={keywords!r} hint={hint!r}"
            ),
        )

    def _grade_dollar_range(self, response: str, expected: str, key: str) -> OracleVerdict:
        # ``$37.5 billion ± 2%`` — accept any response containing the headline number.
        m = _DOLLAR_VALUE_RE.search(expected)
        if not m:
            return OracleVerdict(
                kind="hard",
                **{"pass": False},
                score=0.0,
                evidence=f"spec.yaml::{key}.expected unparseable: {expected!r}",
            )
        head_number = m.group(0)
        head_value = _parse_dollar(head_number)
        if head_value is None:
            return OracleVerdict(
                kind="hard",
                **{"pass": False},
                score=0.0,
                evidence=f"{key} headline number unparseable: {head_number!r}",
            )
        for match in _DOLLAR_VALUE_RE.finditer(response):
            seen = _parse_dollar(match.group(0))
            if seen is None:
                continue
            if abs(seen - head_value) / max(head_value, 1.0) < 0.005:
                return OracleVerdict(
                    kind="hard",
                    **{"pass": True},
                    score=1.0,
                    evidence=f"{key} matched headline: response={match.group(0)!r} expected={expected!r}",
                )
        return OracleVerdict(
            kind="hard",
            **{"pass": False},
            score=0.0,
            evidence=f"{key} headline not found in response: expected={expected!r}",
        )

    def evaluate(self, response: str, task_card: TaskCard) -> OracleVerdictMap:
        out: OracleVerdictMap = {}
        for key, claim in self.spec.items():
            if not isinstance(claim, dict):
                continue
            kind = claim.get("type")
            if kind == "dollar_string":
                out[f"hard.{key}"] = self._grade_dollar(response, claim["expected"], key)
            elif kind == "percent":
                tol = float(claim.get("tolerance_pp", 0.1))
                out[f"hard.{key}"] = self._grade_percent(
                    response, float(claim["expected"]), key, tol
                )
            elif kind == "boolean":
                out[f"hard.{key}"] = self._grade_boolean(
                    response, bool(claim["expected"]), key,
                    claim.get("source_hint", ""),
                )
            elif kind == "dollar_range_string":
                out[f"hard.{key}"] = self._grade_dollar_range(
                    response, claim["expected"], key
                )
        return out


def _keywords_from_key(key: str) -> list[str]:
    """Map known boolean-spec keys to keyword sets (MVP heuristic)."""
    if key == "china_revenue_disclosure_present":
        return ["china", "5.40", "$5.4", "16%"]
    if key == "blackwell_rubin_mention_present":
        return ["blackwell", "rubin"]
    # Fallback: tokenize key.
    return [t for t in key.replace("_", " ").split() if len(t) >= 4]


class ProvenanceOracle:
    """Every claim should cite via ``source: <file>:<line>`` annotation.

    The Oracle scans the response for substantive bullets / claim sentences
    and counts how many have an attached citation token. Missing citation
    leads to a single verdict ``provenance_required`` with ``pass_=False``.
    """

    CITATION_RE = re.compile(
        r"\bsource\s*:\s*[\w\-./]+\.md\s*:\s*\d+",
        re.IGNORECASE,
    )
    # MF6 (harness-praxis tracer follow-up, 2026-06-09): match BOTH bullet
    # markers (-, *, •) AND numbered / lettered enumeration (`1. `, `1) `,
    # `a. `, `i. `). Earlier per-bullet regex only matched `[-*•]` and
    # forced a 0/0 ratio = forced fail whenever the LLM responded with
    # numbered enumeration (a common output style).
    CLAIM_LINE_RE = re.compile(
        r"^[ \t]*(?:[-*•]|(?:\d+|[a-zA-Z]|[ivxIVX]+)[.)])[ \t]+(.+)$",
        re.MULTILINE,
    )

    def evaluate(self, response: str, task_card: TaskCard) -> OracleVerdictMap:
        claim_bodies = [m.group(1) for m in self.CLAIM_LINE_RE.finditer(response)]
        n_claims = len(claim_bodies)
        n_cited = sum(1 for body in claim_bodies if self.CITATION_RE.search(body))
        n_global_citations = len(self.CITATION_RE.findall(response))
        ratio = (n_cited / n_claims) if n_claims else 0.0

        passed = n_claims > 0 and ratio >= 0.9
        if n_claims == 0 and n_global_citations > 0:
            evidence = (
                f"provenance indeterminate: response has 0 bullet-formatted "
                f"claims but {n_global_citations} `source:` citations in prose; "
                f"cannot verify per-claim provenance without bulleted structure"
            )
        else:
            evidence = (
                f"provenance: {n_cited}/{n_claims} bullet claim lines carry "
                f"`source: <file>:<line>` annotation (ratio={ratio:.2f}); "
                f"global citation count={n_global_citations}; "
                f"format=`source: <file>:<line>`"
            )
        verdict = OracleVerdict(
            kind="hard",
            **{"pass": passed},
            score=ratio,
            evidence=evidence,
            uncertainty=None,
        )
        return {"hard.provenance_required": verdict}
