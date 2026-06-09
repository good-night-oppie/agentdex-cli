#!/usr/bin/env python3
# PROPAGATED FROM: /home/admin/gh/harness-engineering/scripts/doc_lint.py
# SOURCE SHA at copy time: 
# COPIED ON: 2026-06-09
# DRIFT DETECTION: re-diff against source quarterly; if source has changed, re-propagate or document divergence.
# FUTURE: per P0a' reframing in completeness verdict wlknjnnuu, move to versioned ~/.claude/shared-rules/ + pin version.
"""doc_lint.py — Harness-engineering documentation linter.

Enforces the 63-rule doc-lint specification distilled from the 30-episode
"Harness Engineering" series. Citations use the corpus's NN-mmss anchor
format (matches SEARCH.json).

Rule citation index (lint_rules → episode anchors):
- DOC-LINT-001  ep03 00-0057, ep08 08-0135   agent-fix PRs must touch docs/spec
- DOC-LINT-002  ep03 00-0030, ep03 00-0035   AGENTS.md env-definition surface required
- DOC-LINT-003  ep03 00-0035                 architecture docs need TOOLS/ARCH/CONTEXT
- DOC-LINT-004  ep03 01-0159, ep04 04-0332   specs need falsifiable acceptance criteria
- DOC-LINT-005  ep03 01-0142                 repo scaffolding present + documented
- DOC-LINT-006  ep03 03-0341                 skill files require frontmatter triggers
- DOC-LINT-007  ep03 02-0206                 FEEDBACK loop = executable commands
- DOC-LINT-008  ep03 01-0128, ep06 06-0050   normative docs describe WHAT not HOW
- DOC-LINT-009  ep03 02-0298, ep08 08-0136   agent-bug closures → gaps.md entry
- DOC-LINT-010  ep04 04-0049, ep04 04-0051, ep05 01-1500  YAML frontmatter required
- DOC-LINT-011  ep04 04-0100, ep06 06-0027, ep06 06-0028  verifiable_claims/invariants
- DOC-LINT-012  ep04 04-0213                 structured component inventory block
- DOC-LINT-013  ep04 04-0217                 reproduce + verify executable blocks
- DOC-LINT-014  ep04 04-0247                 logs + metrics + traces (3 pillars)
- DOC-LINT-015  ep04 04-0304, ep06 06-0130   docs must declare scope
- DOC-LINT-016  ep04 04-0332                 SLA numeric threshold + verifier
- DOC-LINT-017  ep04 04-0344, ep06 06-0101   vibe-detector: no hedge in invariants
- DOC-LINT-018  ep04 04-0401                 no manual-verify without automation
- DOC-LINT-019  ep04 04-0411                 closed-loop 5-section template
- DOC-LINT-020  ep04 04-0431, ep05 02-3800   no orphan docs (3-hop reachability)
- DOC-LINT-021  ep05 01-3700, ep05 00-4100   AGENTS.md ≤ 150 lines, map not encyclopedia
- DOC-LINT-022  ep05 00-5500                 priority-marker budget
- DOC-LINT-023  ep05 01-0300, ep09 09-0042   updated date + staleness
- DOC-LINT-024  ep05 01-2900, ep09 09-0107   docs/ canonical, no contradicting duplicates
- DOC-LINT-025  ep05 01-4500                 AGENTS.md + architecture.md baseline
- DOC-LINT-026  ep05 01-5400                 docs/ taxonomy subdirectories
- DOC-LINT-027  ep05 01-5800                 design docs validation-status tag
- DOC-LINT-028  ep05 02-0600                 plans/ lifecycle subdir
- DOC-LINT-029  ep05 02-1500                 quality.md covers all layers
- DOC-LINT-030  ep05 02-2800                 complex PRs need plan with logs
- DOC-LINT-031  ep05 02-5500, ep09 09-0124   doc-lint wired as required CI check
- DOC-LINT-032  ep05 03-0400, ep09 09-0042, 09-0206, 09-0224  doc-gardener sweeper cron
- DOC-LINT-033  ep05 03-3100, ep05 04-1900   external knowledge mirrored in repo
- DOC-LINT-034  ep05 04-1900                 chat-log artifacts forbidden in normative
- DOC-LINT-035  ep05 04-3200                 onboarding docs (principles, norms, culture)
- DOC-LINT-036  ep05 06-0200, ep09 09-0107   no agent-specific silos
- DOC-LINT-037  ep06 06-0025, ep06 06-0027   MUST/SHALL require enforced_by
- DOC-LINT-038  ep06 06-0028                 doc-only rule sweeper
- DOC-LINT-039  ep06 06-0037                 forbid 'code review' as sole enforcement
- DOC-LINT-040  ep06 06-0040                 architecture guardrails section
- DOC-LINT-041  ep06 06-0045, ep09 09-0058   spec ## Translation to Enforcement
- DOC-LINT-042  ep06 06-0057                 external-data ingress = schema invariant
- DOC-LINT-043  ep06 06-0101                 rule_class matches keyword usage
- DOC-LINT-044  ep06 06-0112                 below-invariant split marker
- DOC-LINT-045  ep06 06-0130                 canonical layer: tag
- DOC-LINT-046  ep06 06-0137                 forward-only dep rule for cross-links
- DOC-LINT-047  ep06 06-0242                 cross-cutting via Providers index
- DOC-LINT-048  ep08 08-0035                 architecture commits touch docs/architecture
- DOC-LINT-049  ep08 08-0208                 bugfix PRs need Repro artifact
- DOC-LINT-050  ep08 08-0214                 bugfix PRs need Verified artifact
- DOC-LINT-051  ep08 08-0147                 process-encoding files at known paths
- DOC-LINT-052  ep08 08-0118                 feature PRs link spec with AC
- DOC-LINT-053  ep08 08-0313                 autonomous-agent issues need DoD
- DOC-LINT-054  ep08 08-0323                 autonomy claims need Prereqs/Harness section
- DOC-LINT-055  ep08 08-0346                 LLM-commits repo needs AGENTS.md
- DOC-LINT-056  ep08 08-0353                 doc-density floor as agent share rises
- DOC-LINT-057  ep08 08-0038                 unresolved review threads block merge
- DOC-LINT-058  ep08 08-0043                 monitoring/dashboard defs in repo
- DOC-LINT-059  ep08 08-0036                 agent-capability PRs need eval entry
- DOC-LINT-060  ep09 09-0220                 sweeper PRs small-grained
- DOC-LINT-061  ep09 09-0224                 forbid doc-overhaul epics
- DOC-LINT-062  ep09 09-0042, ep09 09-0318   src changes need paired doc updates
- DOC-LINT-063  ep09 09-0318                 doc rules without checker → flag

Usage:
    doc_lint.py [--staged | <git-range> | <file-or-dir>...]
                [--fix] [--quiet] [--json]

Modes:
    commit-shape  default for --staged or git-range; for each touched code file
                  check required doc + frontmatter + section scaffolding
    doc-only      when args are .md paths; verify schema + sections

Exit codes:
    0  no BLOCK violations (WARN/INFO may still print)
    1  one or more BLOCK violations
    2  invocation error
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / ".harness" / "doc-templates"

# ---------------------------------------------------------------------------
# Severity constants
# ---------------------------------------------------------------------------
BLOCK = "BLOCK"
WARN = "WARN"
INFO = "INFO"

# ---------------------------------------------------------------------------
# Frontmatter schema (subset enforced by this script — full schema in design)
# ---------------------------------------------------------------------------
REQUIRED_FIELDS_ALL = ("title", "status", "owner", "created", "updated", "type", "scope")
STATUS_VALUES = {"draft", "active", "validated", "deprecated", "archived", "advisory", "experimental"}
TYPE_VALUES = {"feature", "bugfix", "architecture", "runbook", "adr", "spec",
               "postmortem", "reference", "skill", "principle", "plan"}
LAYER_VALUES = {"types", "config", "data", "service", "runtime", "ui", "providers", "cross-cutting"}
RULE_CLASS_VALUES = {"invariant", "default", "hint", "advisory", "informational"}

HEDGE_WORDS = ("maybe", "should probably", "TBD", "差不多", "roughly",
               "usually", "mostly", "tend to", "prefer", "should")
SLA_VAGUE = ("fast", "quick", "responsive", "low-latency", "high-throughput")
PRIORITY_MARKERS = ("IMPORTANT", "CRITICAL", "MUST", "重要", "关键")
MANUAL_PHRASES = ("manually verify", "eyeball", "visually inspect",
                  "take a screenshot", "check the dashboard")
NORMATIVE_KEYWORDS = ("MUST", "MUST NOT", "SHALL", "必须", "禁止")

# Code-file → expected doc-type mapping (commit-shape mode)
CODE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
             ".rb", ".sh", ".c", ".cpp", ".h", ".hpp"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class Violation:
    file: str
    rule_id: str
    severity: str
    message: str

    def format(self) -> str:
        return f"{self.file}: {self.rule_id} [{self.severity}] {self.message}"


@dataclass
class LintContext:
    repo_root: Path
    files: list[Path]
    fix: bool = False
    quiet: bool = False
    json_out: bool = False
    violations: list[Violation] = field(default_factory=list)
    mode: str = "commit-shape"  # or "doc-only"

    def add(self, file: Path | str, rule_id: str, severity: str, message: str) -> None:
        rel = str(file) if isinstance(file, str) else self._rel(file)
        self.violations.append(Violation(rel, rule_id, severity, message))

    def _rel(self, p: Path) -> str:
        try:
            return str(p.resolve().relative_to(self.repo_root))
        except ValueError:
            return str(p)


# ---------------------------------------------------------------------------
# Frontmatter parser (stdlib-only mini-YAML)
# ---------------------------------------------------------------------------
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter without PyYAML. Handles scalars, simple lists,
    and inline {k: v} maps — sufficient for the doc-lint schema."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    body = m.group(1)
    return _parse_yaml_block(body)


def _parse_yaml_block(body: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        # strip inline comments (only those preceded by whitespace + '#')
        line = re.sub(r"\s+#.*$", "", line)
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if not re.match(r"^[A-Za-z_][\w-]*\s*:", line):
            i += 1
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            # collect following indented list / map
            items: list[Any] = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    j += 1
                    continue
                if not nxt.startswith((" ", "\t")):
                    break
                stripped = nxt.strip()
                if stripped.startswith("- "):
                    val = stripped[2:].strip()
                    items.append(_parse_scalar_or_inline(val))
                j += 1
            out[key] = items
            i = j
            continue
        out[key] = _parse_scalar_or_inline(rest)
        i += 1
    return out


def _parse_scalar_or_inline(v: str) -> Any:
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar_or_inline(x) for x in _split_csv(inner)]
    if v.startswith("{") and v.endswith("}"):
        inner = v[1:-1].strip()
        d: dict[str, Any] = {}
        for part in _split_csv(inner):
            k, _, val = part.partition(":")
            d[k.strip()] = _parse_scalar_or_inline(val.strip())
        return d
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


def _split_csv(s: str) -> list[str]:
    """Split on commas honoring brace/bracket nesting and quotes."""
    out: list[str] = []
    depth = 0
    cur = []
    in_q: str | None = None
    for ch in s:
        if in_q:
            cur.append(ch)
            if ch == in_q:
                in_q = None
            continue
        if ch in "\"'":
            in_q = ch
            cur.append(ch)
            continue
        if ch in "[{":
            depth += 1
            cur.append(ch)
            continue
        if ch in "]}":
            depth -= 1
            cur.append(ch)
            continue
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return out


# ---------------------------------------------------------------------------
# Section / structure helpers
# ---------------------------------------------------------------------------
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
FENCED_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_-]*\n(.*?)```", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
MDLINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def get_h2_sections(text: str) -> list[str]:
    return [m.group(1).strip() for m in H2_RE.finditer(text)]


def has_section(text: str, name: str) -> bool:
    return any(name.lower() == s.lower() for s in get_h2_sections(text))


def section_body(text: str, name: str) -> str:
    """Return the body text between an H2 ## name and the next ## (or EOF)."""
    pattern = re.compile(
        rf"^##\s+{re.escape(name)}\s*$(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(text)
    return m.group(1) if m else ""


def strip_blockquotes(text: str) -> str:
    """Return text with markdown blockquote lines removed (for hedge-word check)."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(">"))


def parse_date_safe(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    if not isinstance(v, str):
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(v.strip(), fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Per-doc rule checks
# ---------------------------------------------------------------------------
def check_doc(ctx: LintContext, path: Path) -> None:
    """Run all per-doc rule checks against a markdown file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        ctx.add(path, "DOC-LINT-XXX", BLOCK, f"unreadable: {e}")
        return

    fm = parse_frontmatter(text)
    rel = str(path.resolve().relative_to(ctx.repo_root)) if path.is_absolute() else str(path)
    body = text[text.find("\n---\n") + 5:] if fm is not None and "\n---\n" in text else text

    # DOC-LINT-010  YAML frontmatter required
    is_external_verbatim = "docs/references/external/" in rel
    if fm is None:
        if is_external_verbatim and "verbatim_upstream: true" in text:
            pass
        else:
            ctx.add(path, "DOC-LINT-010", BLOCK,
                    "missing YAML frontmatter (ep04 04-0049, 04-0051)")
            return

    # DOC-LINT-015  scope required
    if "scope" not in fm or not fm.get("scope"):
        ctx.add(path, "DOC-LINT-015", BLOCK,
                "frontmatter missing required 'scope' field (ep04 04-0304)")
    else:
        scope_val = str(fm.get("scope", ""))
        if scope_val == "global" and "docs/architecture" not in rel:
            ctx.add(path, "DOC-LINT-015", BLOCK,
                    "scope: global only allowed at docs/architecture/ root")

    # Required-for-all-docs field presence
    for field_name in REQUIRED_FIELDS_ALL:
        if field_name not in fm or fm.get(field_name) in (None, "", []):
            ctx.add(path, "DOC-LINT-010", BLOCK,
                    f"frontmatter missing required field '{field_name}'")

    # status enum
    status = fm.get("status")
    if status and status not in STATUS_VALUES:
        ctx.add(path, "DOC-LINT-010", BLOCK,
                f"frontmatter status='{status}' not in {sorted(STATUS_VALUES)}")

    # type enum
    doc_type = fm.get("type")
    if doc_type and doc_type not in TYPE_VALUES:
        ctx.add(path, "DOC-LINT-010", BLOCK,
                f"frontmatter type='{doc_type}' not in {sorted(TYPE_VALUES)}")

    # DOC-LINT-045  layer enum
    layer = fm.get("layer")
    if layer is None or layer == "":
        ctx.add(path, "DOC-LINT-045", BLOCK,
                "frontmatter missing 'layer' field (ep06 06-0130)")
    elif layer not in LAYER_VALUES:
        ctx.add(path, "DOC-LINT-045", BLOCK,
                f"layer='{layer}' not in {sorted(LAYER_VALUES)}")
    elif layer == "cross-cutting" and not fm.get("cross_cutting"):
        ctx.add(path, "DOC-LINT-045", BLOCK,
                "layer=cross-cutting requires cross_cutting: true")

    # DOC-LINT-011  verifiable_claims / invariants array
    rule_class = fm.get("rule_class")
    if doc_type not in ("runbook", "reference"):
        vc = fm.get("verifiable_claims") or fm.get("invariants")
        if not vc:
            ctx.add(path, "DOC-LINT-011", BLOCK,
                    "frontmatter missing verifiable_claims / invariants array (ep04 04-0100, ep06 06-0027)")
        elif isinstance(vc, list):
            for entry in vc:
                if isinstance(entry, dict) and "enforced_by" not in entry:
                    ctx.add(path, "DOC-LINT-011", BLOCK,
                            f"verifiable_claims entry missing 'enforced_by': {entry}")

    # DOC-LINT-023  updated date + staleness
    upd = parse_date_safe(fm.get("updated"))
    if upd is None:
        ctx.add(path, "DOC-LINT-023", WARN,
                "frontmatter missing 'updated' date (ep05 01-0300)")
    else:
        if (date.today() - upd) > timedelta(days=90):
            sev = INFO if doc_type == "adr" and status == "active" else WARN
            ctx.add(path, "DOC-LINT-023", sev,
                    f"doc updated {(date.today()-upd).days}d ago (>90, ep09 09-0042)")

    # DOC-LINT-037  MUST/SHALL keywords require enforced_by
    has_normative = any(
        re.search(rf"\b{re.escape(kw)}\b", body) for kw in NORMATIVE_KEYWORDS
    )
    enforced = fm.get("enforced_by") or []
    if has_normative and not enforced:
        if status == "advisory":
            ctx.add(path, "DOC-LINT-037", BLOCK,
                    "advisory doc uses MUST/SHALL — switch to SHOULD/MAY (ep06 06-0025)")
        else:
            ctx.add(path, "DOC-LINT-037", BLOCK,
                    "normative keywords (MUST/SHALL) require 'enforced_by:' frontmatter array (ep06 06-0027)")

    # DOC-LINT-017  hedge words in invariant sections
    for sect in ("Invariants", "Acceptance Criteria", "Definition of Done"):
        body_text = strip_blockquotes(section_body(text, sect))
        for hw in HEDGE_WORDS:
            if re.search(rf"\b{re.escape(hw)}\b", body_text, re.IGNORECASE):
                ctx.add(path, "DOC-LINT-017", BLOCK,
                        f"hedge word '{hw}' in ## {sect} (ep04 04-0344)")
                break
    if rule_class == "invariant":
        stripped_body = strip_blockquotes(body)
        for hw in HEDGE_WORDS:
            if re.search(rf"\b{re.escape(hw)}\b", stripped_body, re.IGNORECASE):
                ctx.add(path, "DOC-LINT-043", BLOCK,
                        f"rule_class: invariant doc uses hedge word '{hw}' (ep06 06-0101)")
                break

    # DOC-LINT-016  SLA adjectives need numeric + verifier
    for ln_no, ln in enumerate(body.splitlines(), 1):
        for adj in SLA_VAGUE:
            if re.search(rf"\b{re.escape(adj)}\b", ln, re.IGNORECASE):
                if not re.search(r"\d", ln):
                    # exempt if in background / motivation section
                    in_bg = _line_in_section(body, ln_no, ("Background", "Motivation"))
                    if not in_bg:
                        ctx.add(path, "DOC-LINT-016", BLOCK,
                                f"vague SLA adjective '{adj}' without numeric threshold on line {ln_no} (ep04 04-0332)")
                break

    # DOC-LINT-022  priority-marker budget
    nonblank = [ln for ln in body.splitlines() if ln.strip()]
    marker_lines = [ln for ln in nonblank
                    if any(m in ln for m in PRIORITY_MARKERS)]
    if rule_class != "invariant" and nonblank:
        ratio = len(marker_lines) / len(nonblank)
        if ratio > 0.10 or len(marker_lines) > 5:
            ctx.add(path, "DOC-LINT-022", WARN,
                    f"{len(marker_lines)} priority markers ({ratio:.0%} of lines) — when all is important, none is (ep05 00-5500)")

    # DOC-LINT-018  manual-verify without automation_fallback
    for phrase in MANUAL_PHRASES:
        if phrase.lower() in body.lower():
            if not fm.get("manual_only") and "automation_fallback:" not in body:
                ctx.add(path, "DOC-LINT-018", WARN,
                        f"contains '{phrase}' but no automation_fallback (ep04 04-0401)")
            break

    # DOC-LINT-034  chat-log artifacts in normative docs
    if "docs/references/raw-transcripts/" not in rel and not fm.get("verbatim_upstream"):
        if re.search(r"@[\w-]+", body) and re.search(r"\b\d{1,2}:\d{2}\s*(AM|PM)\b", body):
            ctx.add(path, "DOC-LINT-034", WARN,
                    "chat-log artifacts (@-mentions + AM/PM timestamps) in normative doc (ep05 04-1900)")

    # Type-specific checks
    if doc_type == "feature" or doc_type == "spec":
        check_feature_or_spec(ctx, path, text, fm)
    if doc_type == "bugfix":
        check_bugfix(ctx, path, text, fm)
    if doc_type == "runbook":
        check_runbook(ctx, path, text, fm)
    if doc_type == "architecture":
        check_architecture(ctx, path, text, fm)
    if doc_type in ("runbook", "adr", "postmortem"):
        check_closed_loop(ctx, path, text)

    # DOC-LINT-021  AGENTS.md ≤ 150 lines + ≤30% substantive
    if path.name == "AGENTS.md" and path.parent == ctx.repo_root:
        nlines = len(text.splitlines())
        if nlines > 150:
            ctx.add(path, "DOC-LINT-021", BLOCK,
                    f"AGENTS.md is {nlines} lines (>150); must be a map (ep05 01-3700)")
        link_lines = sum(1 for ln in text.splitlines()
                         if MDLINK_RE.search(ln) or WIKILINK_RE.search(ln))
        nb = max(1, sum(1 for ln in text.splitlines() if ln.strip()))
        substantive = nb - link_lines
        if substantive / nb > 0.30 and nlines > 50:
            ctx.add(path, "DOC-LINT-021", BLOCK,
                    f"AGENTS.md is {substantive/nb:.0%} substantive prose — should be ≤30% (ep05 00-4100)")

    # DOC-LINT-027  design docs require validation status
    if "/docs/design/" in rel or rel.startswith("docs/design/"):
        if status not in {"draft", "validated", "deprecated", "experimental"}:
            ctx.add(path, "DOC-LINT-027", BLOCK,
                    "design doc missing valid status tag (ep05 01-5800)")

    # DOC-LINT-028  plan docs lifecycle subdir
    if doc_type == "plan":
        if not any(seg in rel for seg in ("plans/in-progress/", "plans/done/", "debt/")):
            ctx.add(path, "DOC-LINT-028", BLOCK,
                    "plan doc must live under plans/in-progress|done or debt/ (ep05 02-0600)")


def _line_in_section(text: str, line_no: int, sections: tuple[str, ...]) -> bool:
    """Test whether a 1-indexed line falls inside any of the named H2 sections."""
    cur_section = None
    for i, ln in enumerate(text.splitlines(), 1):
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m:
            cur_section = m.group(1).strip()
        if i == line_no:
            return cur_section in sections if cur_section else False
    return False


def check_feature_or_spec(ctx: LintContext, path: Path, text: str, fm: dict[str, Any]) -> None:
    # DOC-LINT-004
    if not has_section(text, "Acceptance Criteria"):
        ac_status = fm.get("status")
        linked = fm.get("linked_issues") or []
        if not (ac_status == "draft" and not linked):
            ctx.add(path, "DOC-LINT-004", BLOCK,
                    "feature/spec lacks ## Acceptance Criteria (ep03 01-0159)")
    else:
        ac_body = section_body(text, "Acceptance Criteria")
        if not re.search(r"^\s*-\s*\[[ x]\]", ac_body, re.MULTILINE):
            ctx.add(path, "DOC-LINT-004", BLOCK,
                    "## Acceptance Criteria lacks checkbox list (ep04 04-0332)")

    # DOC-LINT-041
    if not has_section(text, "Translation to Enforcement"):
        if not (fm.get("status") == "draft"):
            ctx.add(path, "DOC-LINT-041", BLOCK,
                    "spec/feature lacks ## Translation to Enforcement (ep06 06-0045)")
    else:
        tte = section_body(text, "Translation to Enforcement")
        if not tte.strip() or re.search(r"\bTODO\b", tte):
            ctx.add(path, "DOC-LINT-041", BLOCK,
                    "## Translation to Enforcement is empty or has only TODOs (ep09 09-0058)")

    # DOC-LINT-053  Definition of Done (also covered by frontmatter, but section presence too)
    if not has_section(text, "Definition of Done") and not fm.get("definition_of_done"):
        ctx.add(path, "DOC-LINT-053", BLOCK,
                "feature/spec lacks Definition of Done (ep08 08-0313)")

    # DOC-LINT-012  component inventory for type=architecture handled elsewhere; also feature scope-warning
    if fm.get("type") == "feature" and fm.get("scope") != "single-component":
        # presence of a table or yaml block
        has_inventory = bool(re.search(r"^\|\s*\w+.*\|\s*$", text, re.MULTILINE))
        has_yaml_block = bool(re.search(r"```ya?ml\n.*?```", text, re.DOTALL))
        if not (has_inventory or has_yaml_block):
            ctx.add(path, "DOC-LINT-012", WARN,
                    "feature doc lacks structured inventory (table or YAML block) (ep04 04-0213)")


def check_bugfix(ctx: LintContext, path: Path, text: str, fm: dict[str, Any]) -> None:
    # DOC-LINT-013
    if not has_section(text, "Reproduce"):
        ctx.add(path, "DOC-LINT-013", BLOCK,
                "bugfix doc lacks ## Reproduce fenced shell block (ep04 04-0217)")
    else:
        body = section_body(text, "Reproduce")
        if "```" not in body:
            ctx.add(path, "DOC-LINT-013", BLOCK,
                    "## Reproduce missing fenced code block (ep04 04-0217)")
    if not has_section(text, "Verify"):
        ctx.add(path, "DOC-LINT-013", BLOCK,
                "bugfix doc lacks ## Verify block with exit-code assertion (ep04 04-0217)")
    else:
        body = section_body(text, "Verify")
        if not re.search(r"(exit\s+code|exit_code|\$\?)", body, re.IGNORECASE):
            ctx.add(path, "DOC-LINT-013", BLOCK,
                    "## Verify section missing exit-code assertion (ep04 04-0217)")
    # frontmatter repro/verified
    if "repro" not in fm:
        ctx.add(path, "DOC-LINT-049", BLOCK,
                "bugfix frontmatter missing 'repro:' artifact link (ep08 08-0208)")
    if "verified" not in fm:
        ctx.add(path, "DOC-LINT-050", BLOCK,
                "bugfix frontmatter missing 'verified:' artifact link (ep08 08-0214)")


def check_runbook(ctx: LintContext, path: Path, text: str, fm: dict[str, Any]) -> None:
    if not has_section(text, "Reproduce"):
        ctx.add(path, "DOC-LINT-013", BLOCK,
                "runbook lacks ## Reproduce shell block (ep04 04-0217)")
    if not has_section(text, "Verify"):
        if not fm.get("manual_only"):
            ctx.add(path, "DOC-LINT-013", BLOCK,
                    "runbook lacks ## Verify with exit-code assertion (ep04 04-0217)")
    # DOC-LINT-014  observability frontmatter
    obs = fm.get("observability")
    stateless = fm.get("stateless") and fm.get("side-effects") == "none"
    if not stateless:
        if not obs:
            ctx.add(path, "DOC-LINT-014", WARN,
                    "runbook lacks observability frontmatter {logs, metrics, traces} (ep04 04-0247)")
        elif isinstance(obs, dict):
            missing = [k for k in ("logs", "metrics", "traces") if k not in obs]
            if missing:
                ctx.add(path, "DOC-LINT-014", WARN,
                        f"observability missing {missing} (ep04 04-0247)")


def check_architecture(ctx: LintContext, path: Path, text: str, fm: dict[str, Any]) -> None:
    # DOC-LINT-003  TOOLS / ARCHITECTURE / CONTEXT headers
    required = ("Tools", "Architecture", "Context")
    if fm.get("scope") != "partial-architecture":
        for sect in required:
            if not has_section(text, sect):
                ctx.add(path, "DOC-LINT-003", BLOCK,
                        f"architecture doc missing ## {sect} header (ep03 00-0035)")
    # DOC-LINT-040  Guardrails
    if not has_section(text, "Guardrails"):
        ctx.add(path, "DOC-LINT-040", BLOCK,
                "architecture doc lacks ## Guardrails section (ep06 06-0040)")
    # DOC-LINT-012  inventory block
    has_inventory = bool(re.search(r"^\|\s*\w+.*\|\s*$", text, re.MULTILINE))
    has_yaml_block = bool(re.search(r"```ya?ml\n.*?```", text, re.DOTALL))
    if not (has_inventory or has_yaml_block) and fm.get("scope") != "single-component":
        ctx.add(path, "DOC-LINT-012", WARN,
                "architecture lacks structured component inventory (ep04 04-0213)")


def check_closed_loop(ctx: LintContext, path: Path, text: str) -> None:
    fm = parse_frontmatter(text) or {}
    if fm.get("status") == "draft":
        # grace period: <7 days
        created = parse_date_safe(fm.get("created"))
        if created and (date.today() - created) < timedelta(days=7):
            return
    required = ("Action", "Observation", "Diagnosis", "Fix", "Re-verification")
    for sect in required:
        if not has_section(text, sect):
            ctx.add(path, "DOC-LINT-019", BLOCK,
                    f"closed-loop template missing ## {sect} (ep04 04-0411)")


# ---------------------------------------------------------------------------
# Repo-level checks (run once per invocation)
# ---------------------------------------------------------------------------
def check_repo_baseline(ctx: LintContext) -> None:
    """Run rules that target repo-level invariants: DOC-LINT-002, 005, 025,
    026, 031, 032, 035, 051, 055."""
    root = ctx.repo_root
    agents_md = root / "AGENTS.md"
    agent_disabled = (root / ".agent-disabled").exists()

    # DOC-LINT-002 / DOC-LINT-025  AGENTS.md baseline
    if not agents_md.exists() and not agent_disabled:
        ctx.add("AGENTS.md", "DOC-LINT-002", BLOCK,
                "repo lacks top-level AGENTS.md env-definition surface (ep03 00-0030)")
        ctx.add("AGENTS.md", "DOC-LINT-025", BLOCK,
                "repo lacks AGENTS.md baseline (ep05 01-4500)")
    else:
        if agents_md.exists():
            text = agents_md.read_text(encoding="utf-8", errors="replace")
            for sect in ("Tools", "Architecture", "Context", "Feedback"):
                if not has_section(text, sect):
                    ctx.add("AGENTS.md", "DOC-LINT-002", BLOCK,
                            f"AGENTS.md missing ## {sect} section (ep03 00-0035)")

    # DOC-LINT-025  architecture.md baseline
    arch_md = root / "docs" / "architecture" / "architecture.md"
    if not arch_md.exists() and not agent_disabled:
        ctx.add(str(arch_md.relative_to(root)), "DOC-LINT-025", BLOCK,
                "repo lacks docs/architecture/architecture.md (ep05 01-4500)")

    # DOC-LINT-005  scaffolding
    has_ci = bool(list((root / ".github" / "workflows").glob("*.yml"))
                  if (root / ".github" / "workflows").exists() else [])
    has_lint = any((root / cfg).exists() for cfg in (
        ".pre-commit-config.yaml", "pyproject.toml", ".eslintrc",
        ".eslintrc.json", ".eslintrc.js", "ruff.toml", ".ruff.toml"))
    has_repo_structure = (root / "docs" / "REPO_STRUCTURE.md").exists() \
        or (root / "REPO_STRUCTURE.md").exists()
    has_dev_setup = (root / "docs" / "DEV_SETUP.md").exists() \
        or (root / "DEV_SETUP.md").exists()
    if not has_ci:
        ctx.add(".github/workflows/", "DOC-LINT-005", BLOCK,
                "no CI workflow under .github/workflows/ (ep03 01-0142)")
    if not has_lint:
        ctx.add(".pre-commit-config.yaml", "DOC-LINT-005", BLOCK,
                "no lint config (pre-commit/pyproject/eslintrc/ruff) (ep03 01-0142)")
    if not has_repo_structure:
        ctx.add("docs/REPO_STRUCTURE.md", "DOC-LINT-005", BLOCK,
                "no REPO_STRUCTURE doc (ep03 01-0142)")
    if not has_dev_setup:
        ctx.add("docs/DEV_SETUP.md", "DOC-LINT-005", BLOCK,
                "no DEV_SETUP doc (ep03 01-0142)")

    # DOC-LINT-026  docs/ taxonomy
    docs_dir = root / "docs"
    if docs_dir.exists():
        required_subdirs = ("design", "plans", "debt", "specs", "references", "principles")
        for sub in required_subdirs:
            if not (docs_dir / sub).exists():
                ctx.add(f"docs/{sub}/", "DOC-LINT-026", WARN,
                        f"docs/ taxonomy missing subdir '{sub}' (ep05 01-5400)")
        # files directly under docs/ outside subdirs
        for p in docs_dir.iterdir():
            if p.is_file() and p.suffix == ".md" and p.name != "README.md":
                ctx.add(str(p.relative_to(root)), "DOC-LINT-026", WARN,
                        "doc lives in docs/ root outside taxonomy (ep05 01-5400)")

    # DOC-LINT-031  doc-lint wired in CI
    wf_dir = root / ".github" / "workflows"
    has_doc_lint_ci = False
    if wf_dir.exists():
        for wf in wf_dir.glob("*.y*ml"):
            try:
                wf_text = wf.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "doc_lint" in wf_text or "doc-lint" in wf_text:
                has_doc_lint_ci = True
                break
    if not has_doc_lint_ci:
        ctx.add(".github/workflows/", "DOC-LINT-031", BLOCK,
                "no CI job runs doc_lint.py (ep05 02-5500)")

    # DOC-LINT-032  doc-sweeper cron
    solo = (root / ".solo-maintainer").exists()
    sweeper_paths = (
        wf_dir / "doc-sweeper.yml",
        wf_dir / "doc-sweeper.yaml",
        wf_dir / "doc-gardener.yml",
    )
    has_sweeper = any(p.exists() for p in sweeper_paths)
    nfiles = sum(1 for _ in root.rglob("*") if _.is_file())
    if not has_sweeper and not (solo and nfiles < 50):
        ctx.add(".github/workflows/doc-sweeper.yml", "DOC-LINT-032", WARN,
                "no scheduled doc-sweeper job (ep05 03-0400)")

    # DOC-LINT-035  onboarding docs
    principles_dir = root / "docs" / "principles"
    if not solo:
        for fn in ("principles.md", "engineering-norms.md", "team-culture.md"):
            if not (principles_dir / fn).exists():
                ctx.add(f"docs/principles/{fn}", "DOC-LINT-035", WARN,
                        f"missing onboarding doc '{fn}' (ep05 04-3200)")

    # DOC-LINT-051  process-encoding files
    for p in ("AGENTS.md", ".github/PULL_REQUEST_TEMPLATE.md",
              "docs/review-checklist.md"):
        if not (root / p).exists() and not solo:
            ctx.add(p, "DOC-LINT-051", WARN,
                    f"process-encoding file '{p}' missing (ep08 08-0147)")
    if not has_ci and not solo:
        ctx.add(".github/workflows/", "DOC-LINT-051", WARN,
                "CI workflow YAML missing (ep08 08-0147)")

    # DOC-LINT-055  LLM commits without AGENTS.md
    if not agents_md.exists() and not agent_disabled:
        try:
            log = subprocess.run(
                ["git", "log", "--all", "--format=%B", "-200"],
                cwd=root, capture_output=True, text=True, timeout=20,
            ).stdout
            if re.search(r"Co-Authored-By:\s*(Claude|Codex|GPT|Cursor)",
                         log, re.IGNORECASE):
                ctx.add("AGENTS.md", "DOC-LINT-055", BLOCK,
                        "repo has agent-authored commits but no AGENTS.md/.agent-disabled (ep08 08-0346)")
        except Exception:
            pass

    # DOC-LINT-036  agent-specific silos
    for silo in (".codex", ".aardvark", ".cursor-private"):
        d = root / silo
        if d.is_dir():
            for p in d.rglob("*.md"):
                if p.read_text(encoding="utf-8", errors="replace").strip():
                    ctx.add(str(p.relative_to(root)), "DOC-LINT-036", BLOCK,
                            f"agent-specific knowledge silo in {silo}/ — move to docs/ (ep05 06-0200)")
                    break


def check_skill_files(ctx: LintContext) -> None:
    """DOC-LINT-006  skills require frontmatter triggers."""
    for skills_root in (".skills", "skills", ".claude/skills"):
        d = ctx.repo_root / skills_root
        if not d.exists():
            continue
        for p in d.rglob("*.md"):
            text = p.read_text(encoding="utf-8", errors="replace")
            fm = parse_frontmatter(text)
            if fm is None or not all(k in fm for k in ("name", "description", "scope")):
                ctx.add(str(p.relative_to(ctx.repo_root)),
                        "DOC-LINT-006", BLOCK,
                        "skill file missing YAML frontmatter {name, description, scope} (ep03 03-0341)")


def check_orphans(ctx: LintContext) -> None:
    """DOC-LINT-020  3-hop reachability from AGENTS.md."""
    root = ctx.repo_root
    agents_md = root / "AGENTS.md"
    if not agents_md.exists():
        return
    docs_dir = root / "docs"
    if not docs_dir.exists():
        return
    # Build link graph among AGENTS.md + all docs/**.md
    files: dict[Path, list[Path]] = {}
    for p in [agents_md] + list(docs_dir.rglob("*.md")):
        text = p.read_text(encoding="utf-8", errors="replace")
        targets: list[Path] = []
        for m in MDLINK_RE.finditer(text):
            tgt = m.group(1).split("#")[0]
            if tgt.startswith(("http://", "https://", "mailto:")):
                continue
            cand = (p.parent / tgt).resolve()
            if cand.exists():
                targets.append(cand)
        for m in WIKILINK_RE.finditer(text):
            tgt = m.group(1).split("#")[0]
            cand = (root / tgt).resolve()
            if not cand.suffix:
                cand = cand.with_suffix(".md")
            if cand.exists():
                targets.append(cand)
        files[p.resolve()] = targets
    # BFS from AGENTS.md, 3 hops
    seen = {agents_md.resolve()}
    frontier = [agents_md.resolve()]
    for _ in range(3):
        nxt: list[Path] = []
        for f in frontier:
            for t in files.get(f, []):
                if t not in seen:
                    seen.add(t)
                    nxt.append(t)
        frontier = nxt
    for p in docs_dir.rglob("*.md"):
        rp = p.resolve()
        if rp in seen:
            continue
        rel = str(p.relative_to(root))
        if "docs/archive/" in rel:
            continue
        ctx.add(rel, "DOC-LINT-020", BLOCK,
                "orphan doc — unreachable from AGENTS.md within 3 hops (ep04 04-0431)")


# ---------------------------------------------------------------------------
# Commit-shape mode (DOC-LINT-001, 048, 062)
# ---------------------------------------------------------------------------
def check_commit_shape(ctx: LintContext, changed: list[Path]) -> None:
    """Run rules that key off the shape of a git diff:
       DOC-LINT-001  agent-fix PR must touch docs
       DOC-LINT-048  architecture-shaped commit touches docs/architecture
       DOC-LINT-062  src change w/o paired doc update → warn
    """
    if not changed:
        return
    root = ctx.repo_root
    src_files = [p for p in changed
                 if any(str(p).startswith(s) for s in ("src/", "scripts/"))
                 or p.suffix in CODE_EXTS]
    doc_files = [p for p in changed
                 if p.suffix == ".md"
                 or str(p).startswith(("docs/", "AGENTS.md", ".harness/"))]

    # DOC-LINT-001 agent-fix detection — read latest commit msg
    try:
        msg = subprocess.run(
            ["git", "log", "-1", "--format=%B"],
            cwd=root, capture_output=True, text=True, timeout=10,
        ).stdout.lower()
    except Exception:
        msg = ""
    agent_fix = any(t in msg for t in ("agent stuck", "unblock", "gap", "clarif"))
    if agent_fix and src_files and not doc_files:
        if "env-sufficient:" not in msg:
            ctx.add("HEAD", "DOC-LINT-001", BLOCK,
                    "agent-fix commit touches only code, no docs/spec change (ep03 00-0057)")

    # DOC-LINT-048  architecture-shaped commits
    has_arch_shape = any(
        ("schema" in str(p).lower() or "models/" in str(p) or "/services/" in str(p))
        for p in src_files
    )
    if has_arch_shape:
        touched_arch_docs = any(
            str(p).startswith(("docs/architecture/", "docs/adr/")) for p in changed
        )
        if not touched_arch_docs and "internal-refactor" not in msg:
            ctx.add("HEAD", "DOC-LINT-048", BLOCK,
                    "architecture-shaped commit lacks docs/architecture/ or docs/adr/ touch (ep08 08-0035)")

    # DOC-LINT-062  src change without paired doc
    for sp in src_files:
        if not doc_files and "[docs-followup:" not in msg:
            ctx.add(str(sp), "DOC-LINT-062", WARN,
                    "src change without paired docs/** update (ep09 09-0042)")
            break


# ---------------------------------------------------------------------------
# Fix mode — stub doc from template
# ---------------------------------------------------------------------------
def create_stub_doc(ctx: LintContext, target: Path, doc_type: str = "feature") -> None:
    """Auto-create a stub doc from a template at TEMPLATES_DIR.
    Cites the template path in the new doc."""
    template = TEMPLATES_DIR / f"{doc_type}.md"
    if not template.exists():
        print(f"--fix: template missing: {template}", file=sys.stderr)
        return
    body = template.read_text(encoding="utf-8")
    today = date.today().isoformat()
    body = re.sub(r"(created: )\d{4}-\d{2}-\d{2}", rf"\g<1>{today}", body)
    body = re.sub(r"(updated: )\d{4}-\d{2}-\d{2}", rf"\g<1>{today}", body)
    header = f"<!-- generated from {template.relative_to(ctx.repo_root)} by doc_lint.py --fix -->\n\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(header + body, encoding="utf-8")
    print(f"--fix: created stub {target.relative_to(ctx.repo_root)} from {template.relative_to(ctx.repo_root)}")


# ---------------------------------------------------------------------------
# Argument parsing + dispatch
# ---------------------------------------------------------------------------
def get_staged_files(repo: Path) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=repo, capture_output=True, text=True, timeout=10, check=True,
        ).stdout
    except Exception:
        return []
    return [repo / ln for ln in out.splitlines() if ln.strip()]


def get_range_files(repo: Path, rng: str) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", rng],
            cwd=repo, capture_output=True, text=True, timeout=10, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return []
    return [repo / ln for ln in out.splitlines() if ln.strip()]


def is_git_range(s: str) -> bool:
    return ".." in s or re.fullmatch(r"[A-Za-z0-9_/-]+\.\.[A-Za-z0-9_/-]+", s) is not None


def collect_targets(args: list[str], repo: Path) -> tuple[str, list[Path]]:
    """Return (mode, files). Mode = 'commit-shape' or 'doc-only'."""
    if not args or args == ["--staged"]:
        return ("commit-shape", get_staged_files(repo))
    if len(args) == 1 and is_git_range(args[0]):
        return ("commit-shape", get_range_files(repo, args[0]))
    files: list[Path] = []
    for a in args:
        p = Path(a)
        if not p.is_absolute():
            p = repo / a
        if p.is_dir():
            files.extend(p.rglob("*.md"))
        elif p.exists():
            files.append(p)
    only_md = files and all(p.suffix == ".md" for p in files)
    return ("doc-only" if only_md else "commit-shape", files)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="doc_lint.py",
        description="Documentation linter — 63 rules from harness-engineering corpus.",
    )
    parser.add_argument("--staged", action="store_true",
                        help="lint files in git index (default)")
    parser.add_argument("--fix", action="store_true",
                        help="auto-create stub docs from template when missing")
    parser.add_argument("--quiet", action="store_true",
                        help="only print BLOCK violations")
    parser.add_argument("--json", dest="json_out", action="store_true",
                        help="machine-readable JSON output")
    parser.add_argument("--repo", default=str(REPO_ROOT),
                        help="repo root (default: parent of scripts/)")
    parser.add_argument("targets", nargs="*",
                        help="git-range or files/dirs to lint")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    target_args = (["--staged"] if args.staged and not args.targets else args.targets)
    mode, files = collect_targets(target_args, repo)

    ctx = LintContext(
        repo_root=repo, files=files,
        fix=args.fix, quiet=args.quiet, json_out=args.json_out, mode=mode,
    )

    # Always run repo-level baseline + skill + orphan checks
    check_repo_baseline(ctx)
    check_skill_files(ctx)
    check_orphans(ctx)

    # Per-file checks
    md_files = [p for p in files if p.exists() and p.suffix == ".md"]
    for md in md_files:
        check_doc(ctx, md)

    # Commit-shape rules
    if mode == "commit-shape":
        check_commit_shape(ctx, files)

    # --fix: for each missing-doc BLOCK, create stub
    if args.fix:
        for v in list(ctx.violations):
            if v.severity == BLOCK and v.rule_id in ("DOC-LINT-002",):
                create_stub_doc(ctx, repo / "AGENTS.md", "feature")

    # Report
    code = 0
    rendered: list[dict[str, str]] = []
    for v in ctx.violations:
        rendered.append(asdict(v))
        if v.severity == BLOCK:
            code = 1
        if args.quiet and v.severity != BLOCK:
            continue
        if args.json_out:
            continue
        out = v.format()
        if v.severity == INFO:
            print(out, file=sys.stderr)
        else:
            print(out)

    if args.json_out:
        json.dump({"violations": rendered, "exit_code": code},
                  sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")

    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
