---
title: DEFERRED — agentdex-cli phase-8 polish queue
status: active
owner: etang
created: 2026-06-09
updated: 2026-06-09
type: reference
scope: monorepo
layer: cross-cutting
cross_cutting: true
---

# DEFERRED — agentdex-cli phase-8 polish queue

> Closes workflow w0z1i9vcs H2 (deferred-fix tracking) — bd16c47's commit
> body listed SF/D items as "deferred to phase 8" but no tracking artifact
> recorded them anywhere greppable. This file IS the tracking artifact.
>
> Discipline: every entry must carry `Until: <ISO-date>` so the weekly
> harness audit can flag past-due items (per IDEAL_EXPERIENCE.md anti-fire-
> exit clause + the `feedback_fix_all_before_moving_forward` memory). When
> an item lands, delete its row + record the closing commit hash in
> `sweeps/<date>-weekly-harness-audit.md` §5 action queue.

## Format

```
| ID | Surface | Cited finding | Until | Owner | Open commit |
|----|---------|---------------|-------|-------|-------------|
```

## Open

| ID | Surface | Cited finding | Until | Owner | Open commit |
|----|---------|---------------|-------|-------|-------------|
| RD-1 | Weco integration (M2 spike 1) | BYO `--api-key` credits differential UNMEASURED (only gemini/openai/anthropic supported; `~/.sakana` token unusable). Blocks "free on your own subscriptions" copy — do NOT publish until measured with a supported-provider key. | 2026-08-15 | etang | 7d524487 |
| RD-2 | PokeAgent ladder (M5 market) | pokeagentchallenge.com has NO ToS; mirroring its leaderboard needs an organizer ask (email/Discord — Karten/Grigsby) before M5 can display anything beyond a deep-link. Link-out is the safe default until then. | 2026-08-15 | etang | 7d524487 |
| RD-3 | Terminal-Bench 2 leaderboard comparison | Paid coding-agent run explicitly deferred by operator. M2 closes on the genuine $0 Harbor oracle + no-op integration evidence; do not claim leaderboard-comparable TB2 quality until a separately budgeted paid run is authorized and recorded. | 2026-08-15 | etang | (this commit) |

## Closed (delete after one weekly audit cycle confirms gone)

| ID | Closing commit | Notes |
|----|----------------|-------|
| CLAUDE-BRIDGE-LIVE-EOF | (this commit) | Bumped excerpt cap in claude_bridge.py from 400 to 4000 to capture complete terminal frame |
| BRIDGE-SMOKE-part-1 | 38b23e7 (PR-T) | capture script + validator test landed; live captures still pending (part 2) |
| CALIB-FIXTURES-part-1 | 553ebd4 (PR-U) | 13 hand-labeled rows + round-trip test; full κ ≥ 0.7 inter-rater pending second labeler |
| M7-scaffold | (this PR) | LearnedSeedGenerator Protocol + RecurrencePatternGenerator placeholder + merge helper; real ML post-M9 helios |
| SF5 | phase-8/sf5-bridge-response-class | `BridgeResponse` dataclass returned by `send()` carries `text`/`langfuse_trace_id`/`cost_usd`/`tokens`; orchestrator + 5 stubs migrated off the `getattr(bridge, "last_cost_usd")` back-channel; legacy properties retained for ad-hoc debug |
| H7 + AUDIT-OWNER-SCAN | phase-8/h7-audit-content-scan | weekly audit §2c Owner=TODO scan + §2d orphan doctrine anchor scan (basename-grep heuristic) landed; G13 ep28 [28-0830] sunset citation restored in script header (replaces the pruned TODO comment) |
| BASELINE-DRIFT | phase-8/baseline-drift | `scripts/detect_secrets_no_drift.sh` wraps `detect-secrets-hook`, strips `generated_at`, suppresses exit-3 when timestamp was the only diff; pre-commit hook swapped to local `language: system` entry point. True-positive findings (rc=1) still propagate; verified w/ injected AWS-key fixture |
| BRIDGE-SMOKE | phase-8/bridge-smoke | All 3 live captures (claude/codex/manus) recorded via `tools/agent_senses/capture_bridge_smoke.sh` against installed CLIs; validator (`test_bridge_smoke_fixtures.py`) green for all 3. EVAL.md "Subscription-CLI bridge smoke probe passes at session start" criterion now enforceable on every push |
| CALIB-FIXTURES | phase-8/calib-rater2 | Rater-2 sidecar (`labels_rater_2.yaml`) lands AI-judged labels for all 13 fixtures; `test_inter_rater_kappa.py` asserts Cohen's κ ≥ 0.7 gate (current value 0.846 — 1 marginal disagreement on `nvidia-mixed-format`). Rater-2 is documented as AI by design; promote to human rater-3 when one is available (queue under CALIB-RATER-3 at that point) |
| STATE.MD-REFRESH | phase-8/state-md-refresh | `.supergoal/STATE.md` refreshed in-place per session-2 user authorization ("do 1 to 3 to unblock"); content now reflects M0–M5 done, phase-8 active, the 6 session-2 PRs, and 95 pass + 7 skip test signal. `.supergoal/**` is gitignored so the refresh itself is local-only — this PR carries the DEFERRED row close + a memory-drift note. The `feedback_supergoal_perm_carveout_conflict.md` claim was stale; `echo "test" >> .supergoal/STATE.md` returned rc=0 in session 2 — perm rules now allow Bash-redirect writes |
| MOCK-DATA | phase-8/mock-data-live-q3 | All 4 source MDs rewritten with live Q3 FY2026 results (quarter ended 2025-10-26; released 2025-11-19) + DOC-LINT-010 frontmatter added. New BLAKE3 = `2f3bf8fee53690f76e4701a5097aabb3e19f5bb146a136fe95a2b8d7169c3346` (was `9edcd1a1...`). `bundle.yaml` rehashed + 5 test files (`test_expedition.py` / `test_polish.py` / `test_calibration_fixtures.py` / `test_oracle.py` / `test_balancer.py`) updated to match. Headline numbers: revenue $57.0B (was $35.08B), Data Center $51.21B (was $30.77B), GAAP margin 73.4% (was 74.6%), Q4 guide $65.0B (was $37.5B). `expeditions/*/task_card.yaml` historical records intentionally NOT updated — those are frozen run snapshots, not part of the canonical bundle. 95 pass + 7 skip unchanged |

## PR #704 review-closure deferrals (tc-fugu lineage, 2026-07-19)

| id | tracked | why deferred, and what closing it requires |
|---|---|---|
| OPENBOX-BRIDGES-WIRING | [issue #706](https://github.com/good-night-oppie/agentdex-cli/issues/706) | `adx run --engine bridges` dispatches raw pool names to the single loopback TeamClaude gateway and never reads `.agentdex/openbox.yaml`, so a backend can report READY in `openbox check` yet be ignored or routed under a different model name at run time — and `openbox init` emits a `base_url` key with zero consumers anywhere in the workspace. Not a patch: `LiteLLMWorker` sets `api_base`/`api_key` globally per worker, not per slot (`mini.py:254-255`), so honouring per-backend bindings needs per-slot base-URL plumbing. Closing it means either wiring that, or explicitly declaring openbox advisory-only and marking `check` output as such — plus a test asserting the doc claim matches behaviour so the note cannot drift. Current behaviour is documented in the `run_cmd` module docstring and `adx run --help`. |


## PR #704 fleet-review findings (tc-fugu lineage, 2026-07-19)

| id | tracked | state |
|---|---|---|
| SECRET-RE-RECALL | this row | `Basic <base64>` auth headers loaded at rc 0 — found by ai-scientist-17's AI-Scientist-v2 harness review, FIXED. Regex is now case-sensitive with literal vendor prefixes plus inline `(?i)` on the HTTP auth schemes only; added Stripe/HuggingFace/Groq/Replicate/DigitalOcean/SendGrid/ASIA arms and removed the false positives on `sk-model-v2` / `task-sk-runner-service` / lowercase `akia`. **Still a denylist** — it is defence-in-depth behind the structural `token_ref` contract, not the boundary itself. Any new vendor prefix is a new gap by construction. |
| SELECTION-UNVALIDATED | [#708](https://github.com/good-night-oppie/agentdex-cli/issues/708) | ai-scientist-17: the suite proves selection is *correct*, not that it *picks good models*. No baseline comparison against random / round-robin / epsilon-greedy on the same pool. This is the same root as #708 — a baseline harness would have caught "selects for non-answers" immediately, which is precisely why it belongs before any "measurement engine" claim. |


## PR #704 disposition ruling (tc-fugu-4, 2026-07-19)

| id | tracked | ruling |
|---|---|---|
| SCAFFOLD-RULING | [#707](https://github.com/good-night-oppie/agentdex-cli/issues/707) [#708](https://github.com/good-night-oppie/agentdex-cli/issues/708) | **MERGE AS SCAFFOLD, claim downgraded.** #704 ships the CLI surfaces, seed ledger, allocation loop and selection plumbing — all sound and tested (251 + 44 passing). It does **not** ship a working measurement engine: `policy["gate"]` has zero consumers, so `quality` is never really scored. Merging is right because the blockers are about INPUTS, not about the shipped code being wrong, and because the alternative — 4k tested lines rotting on a branch while M3 stalls — buys nothing. Merging *silently* would be wrong, so three honesty guardrails land with it: simulated rows never average with or outrank measured ones; a constant primary axis is reported as a loud WARNING naming #708 instead of silently ranking on cost; and `--engine fake` output is labelled SIMULATED in both human and JSON. The docs and PR framing no longer call this "the measurement engine". Preconditions before that claim may be made: wire the gate (#707), then a random/round-robin/epsilon-greedy baseline harness (#708) — without the baseline there is no evidence the selector beats chance. |


## Merge-governance exception (tc-fugu-4, 2026-07-19)

| id | what | why recorded |
|---|---|---|
| ADMIN-BYPASS-704 | PR #704 (4412 additions, 13 commits) was merged into `redesign/evolution-market` via **admin bypass**, with **no approving human review** and **one review thread deliberately left unresolved** (the openbox↔bridges contract gap, tracked as #706). Authorised explicitly by Eddie ("merge it") after I declined to request the bypass myself. | I had stated on the bus that #698 was a gate fix with a narrow blast radius while #704 is 4k lines of product surface, and that those deserve different bars — so a bypass here must not pass unrecorded. Merged state at `c588f778`: clean-state CI green, 255 + 44 tests passing, ruff clean. What merged is a SCAFFOLD: `policy["gate"]` still has zero consumers, so the frontier measures nothing yet. The measurement-engine claim is withheld until #707 (wire the gate) and #708 (baseline harness) land. |


## AI-Scientist-v2 deep-review Q&A + new findings (tc-fugu-5, 2026-07-19)

All 12 of ai-scientist-17's technical questions (bus #3930) are answered against HEAD
with `file:line` citations in the Q&A section further down this file. The findings
table immediately below records three things that were NOT raised by the review and
are not documentation gaps — they came out of the verification passes run to answer it.

| id | tracked | finding |
|---|---|---|
| AS17-N1 | this row | **The empty-path scanner hole was LIVE, not LATENT — the earlier severity downgrade is retracted.** Bus #3932 called it "CONFIRMED AS LATENT … NOT EXPLOITABLE" on the grounds that the entry-must-be-a-mapping check (`openbox_cmd.py:219`) fires first. That is true of the `_validate_backend` call site (`:238`) and *only* that site; `_scan_strings` has a second call site — the top-level sweep at `:282` — which passes a `key_str` that can be `""`. Reproduced against `c588f778^`: a secret under an empty top-level key **loaded clean at rc 0** (flat and nested), while the normal-key control was rejected. HEAD rejects all three, so `c588f778` genuinely closed it; the live window was `03dc3fde`→`c588f778`. **Still open:** the in-code comment at `openbox_cmd.py:159-164` continues to assert "Not currently reachable", encoding the same one-call-site error for the next reader. Fix the comment. |
| AS17-N2 | **FIXED this commit** | **Uncaught `PermissionError` in the credential path — TWO independent escapes, both live at HEAD before this commit.** `Path.exists()` swallows ENOENT/ENOTDIR/EBADF/ELOOP but **propagates EACCES**, and `PermissionError` is an `OSError`, absent from the `(FileNotFoundError, ValueError, OpenboxError)` tuple the CLI catches at `:364`/`:381`/`:411`. (1) `_warn_file_ref` — a `token_ref: file:/…` under an unreadable parent raised out of a function whose docstring says *non-fatal*. (2) `load_openbox` — `path.exists()` returns True for a file we may not READ, so `read_text` still raised on an unreadable `openbox.yaml` itself; this second site was found only while writing the fix for the first. Both surfaced as bare tracebacks, which is a regression against a stated property — exception traces are a channel this module explicitly defends. Fixed at the two sources rather than by widening the boundary tuple, which would also swallow genuine I/O bugs: `_warn_file_ref` now warns and continues; `load_openbox` converts to `OpenboxError` in the same shape as the existing `YAMLError` arm. Only the exception **type** is named in either message, never `str(exc)`. Regression tests pinned in `test_openbox_cmd.py`; both fail against the unfixed source. |
| AS17-N3 | [#708](https://github.com/good-night-oppie/agentdex-cli/issues/708) | **Second structural degeneracy: unmetered models cost exactly $0 and are classified as MEASURED.** `_cost_dollar_and_kind` (`run_cmd.py:466-482`) returns `0.0, "adx-run-bridges-unmetered"` whenever the model is absent from `_RATE_TABLE` (`:410`) or has fallback-0 rates. `_measured_rows` (`:258-273`) partitions provenance solely on the `-fake` suffix, and `"adx-run-bridges-unmetered"` does not end in `-fake` — so those rows count as real measurements. With `quality` pinned at 0.5 (`:650`), dominance reduces to (cost, wall-clock) and **no metered candidate can beat a cost of 0.0**, so an unmetered model wins the cost axis by construction regardless of output. Distinct from the known refusal-optimum, reachable without `--engine fake`, and it silently defeats the `8b68f6e0` honesty guardrail. Related correction: "a refusal strictly dominates any candidate that did the work" is FALSE — rates are per-model, so the accurate claim is that the shortest reply wins *among comparable rates*, and unmetered wins outright. |
| AS17-DENYLIST-GAPS | this row | Disclosed `SECRET_RE` misses, recorded so they are greppable rather than rediscovered: short Basic credentials under the 16-char floor (`Basic YWRtaW46cHc=` = `admin:pw`) are not caught; token-as-username URLs with no colon (`https://<token>@host/v1`) load at rc 0; scheme-relative `//user:pw@host` is not caught; base64url payloads with `-`/`_` inside the first 16 chars miss the Basic arm. Not a regression — a denylist is not a boundary, and these are the known cost of that design. The structural guarantee is `token_ref`, which covers exactly one field. |
| AS17-INTERVIEW-UNSCANNED | this row | **`adx interview` scans nothing, and the abstract sentence claiming it does is retracted.** `interview_cmd.py:109` prompts with bare `input()` for all six questions; `render_policy_yaml` (`:165-194`) serialises answers verbatim with no `SECRET_RE` import; `test_interview_cmd.py` has zero secret-related tests (vs ~15 in `test_openbox_cmd.py`). Because the pool feeds `run_cmd.py:674`, a credential typed at the pool prompt persists verbatim into the seed ledger (`:181-189`) *and* `frontier.json` (`:347-401`), both mode 0644. `.agentdex/` is gitignored (`.gitignore:189-190`), so the accidental-commit path is closed — but "zero credential persistence" does not hold for the interview surface, and the docs must not say it does. |
| AS17-LEDGER-DURABILITY | this row | Seed ledger provides fewer guarantees than "append-only ledger" implies: no `fsync`, no advisory lock, no per-row checksum, no schema-version field, mode 0644. Concurrent `adx run` invocations interleave appends (UNSAFE); a torn final line is possible and the reader silently skips unparseable rows, so the failure mode is silent row loss. Sub-`PIPE_BUF` append atomicity is a platform property, not a guarantee of this code. `attempts.json` *is* written atomically (`run_cmd.py:219-222`); the ledger is not. Q9's poison-row guard is a read-time mitigation for a write-time gap — write-time validation is the better design and was previously unfiled. |

## AI-Scientist-v2 deep review: the 12 questions, answered (tc-fugu-5, 2026-07-19)

Reviewer `ai-scientist-17`, AI-Scientist-v2 harness (`perform_review`, gpt-5.5, 3
reflections). Reviewer output: `/tmp/as17-ai-scientist-review-agentdex-v3.json`.

**How to read this.** The harness reviewed a *paper rendering of the PR diff*, not the
repo, and scored it 3/10 Reject on an academic rubric the fleet agreed is the wrong
instrument. The score is not a software verdict and is not treated as one. The
**questions** were the valuable output. Two independent verification passes were run
over the repo at HEAD, each with adversarial verifiers instructed to refute rather than
agree; where they disagreed, the disagreement was settled by direct execution, and the
executed result is what is written here.

| Q | Topic | Verdict | Lands |
|---|---|---|---|
| Q1 | Threat model for "zero credential persistence" | Answered; claim narrowed, one abstract sentence retracted | AS17-INTERVIEW-UNSCANNED |
| Q2 | Secret-detection grammar, Basic auth, URL userinfo | Answered; two denylist gaps disclosed | AS17-DENYLIST-GAPS |
| Q3 | Empty-path scanner hole; path handling | **"LATENT" label corrected to LIVE** | AS17-N1 |
| Q4 | What of `--engine bridges` is exercised e2e | Open gap, stated plainly | #706 |
| Q5 | Per-defect severity for X1–X7 | Answered; 9/10 closed, survivor is #706 | #706 |
| Q6 | "Hardware-enforced budget constraints" | **Dismissed — reviewer hallucination, retracted by the reviewer** | — |
| Q7 | Precise constrained-Pareto definition | Answered; several behaviours UNDEFINED IN CODE | #707 |
| Q8 | Preventing degenerate optima | Open — detected, not prevented; second degeneracy found | #708, AS17-N3 |
| Q9 | OverflowError on inflated quality | Premise stale — fixed at `c588f778` | — |
| Q10 | Seed-ledger guarantees | Answered; fewer guarantees than implied | AS17-LEDGER-DURABILITY |
| Q11 | How many tests exercise real bridge behaviour | **Zero.** Counted, not estimated | #706 |
| Q12 | Baselines evaluated | None. That is exactly #708 | #708 |

### Q1 — threat model

The implemented property is narrower than the phrase suggests. Honest statement:
`openbox.yaml` is the only file agentdex treats as credential-adjacent; (a) no credential
*value* can be written into it via `adx openbox init`; (b) a hand-edited file carrying a
credential-shaped string in a backend field, nested dict, list element, dict *key*,
backend name, or top-level sibling key fails closed at rc 2; (c) no error message ever
quotes the offending value; (d) agentdex **never dereferences** `token_ref`.

(d) is load-bearing and genuinely strong — grepping `openbox_cmd.py` for
`os.environ`/`getenv`/`open(`/`read_text` returns nothing; the only thing done with a
`file:` ref is an existence + mode check (`openbox_cmd.py:194-214`).

| # | Channel | Status |
|---|---|---|
| 1 | Terminal echo | MIXED — defended in openbox; **undefended** in `interview`/`run` |
| 2 | Shell history | OUT OF SCOPE, undefended |
| 3 | Logs | No channel exists (no logging framework in the module) |
| 4 | Exception traces | Defended — but see AS17-N2 |
| 5 | Generated templates | openbox defended; **interview undefended** |
| 6 | Seed ledgers | **Undefended** |
| 7 | Temp files | Defended (write-tmp + `os.replace`); mode 0644, not 0600 |
| 8 | Bridge request dumps | Outbound defended; `--save-outputs` undefended |
| 9 | Process argv / env | Undefended, out of scope by construction (`openbox_cmd.py:9-11`) |

### Q2 — secret-detection grammar

`SECRET_RE` at `openbox_cmd.py:45-72`, 19 arms, **no global flags** — `re.IGNORECASE` was
removed in `9d7c6055`; only the two HTTP-scheme arms carry inline `(?i:)`. The Basic arm
(`:69`) was **added** by `9d7c6055`; before it, `Authorization: Basic <base64>` loaded at
rc 0. The reviewer found that; it was not on our own weakness list. False-positive control:
`-` removed from the raw-key class so hyphenated *model names* cannot match at any length;
floors raised 8 → 16. Pinned by `_BENIGN` (`test_openbox_cmd.py:895-902`) and 15
`_CREDENTIAL_SHAPES` (`:867-883`) asserted rejected *and* never echoed. Gaps: see
AS17-DENYLIST-GAPS. The structural point stands and is not contested — **a regex denylist
is not a security boundary**; it is defence-in-depth behind `token_ref`, which covers one field.

### Q3 — empty-path scanner hole and path handling

See AS17-N1: the hole was LIVE, and the in-code comment claiming unreachability is still
wrong. Path handling in `_warn_file_ref` (`openbox_cmd.py:194-214`): `TOKEN_REF_RE` accepts
`file:/.+` — **absolute only, no tilde expansion**. Symlinks, unreadable files, directories
and FIFOs get **no special handling**; the function only calls `.exists()` and `.stat()` and
**never opens or reads** the file. A `file:` path matching `SECRET_RE` is refused with the
path withheld (`:199-205`).

### Q4 — what of `adx run --engine bridges` is exercised end-to-end

**Nothing, against a production-like gateway.** Coverage at HEAD reports lines `531-550` in
`Missing` — the entire `_post_messages` body never executes under test. `grep -n
'urlopen|socket|requests\.|httpx'` over `run_cmd.py` returns exactly one hit (`:548`), the
only socket in the bridges path, and it is never reached.

| Behaviour | Evidence |
|---|---|
| Dispatch | mocked only — 7 `monkeypatch` sites (`test_run_cmd.py:500,538,559,574,711,785,851`) |
| Credential resolution | none — no credentials are sent (`:540-544`: `content-type` + `anthropic-version` only) |
| Budget / spend control | pre-dispatch estimate only (`:485`); never validated against a real bill |
| Timeout | **no evidence** — `dispatch_timeout` only ever *assigned* (`:471,732,797,861`), never asserted |
| Failure recovery | drop-on-exception (`:660-664`), type name logged, no body |
| Retry / backoff | **does not exist** — zero hits. The reviewer's premise of a retry path is false |
| Ledger write | exercised, but only with mocked dispatch results |

`require_loopback_base_url` (`:456-464`) hard-refuses any non-loopback host, so the bridges
path cannot egress to a remote even if misconfigured.

### Q5 — per-defect severity, X1–X7

Reviewer believed X1–X7 were all live. **Stale**: these were the PR #704 review findings,
nine of ten closed with evidence; the survivor is #706.

| id | Defect | State | Severity class |
|---|---|---|---|
| C1 | Basic-auth bypass in credential guard | CLOSED `9d7c6055` | credential exposure |
| X4 | budget basis mismatch in export | CLOSED `512338b2` | wrong selection |
| X5 | policy emitter quoting (missed leading `-`) | CLOSED `bfb90e2b` | silent invalid output |
| X6 | poison-row `OverflowError` | CLOSED `c588f778` | crash |
| X7 | simulated rows averaging with measured | CLOSED `8b68f6e0` | wrong selection |
| X8 | honesty labelling of `--engine fake` | CLOSED `8b68f6e0` | silent invalid output |
| X9 / X10 | frontier export / objective-case handling | CLOSED `03dc3fde` | wrong selection |
| **#706** | `bridges` ignores `openbox.yaml` bindings | **OPEN** | silent invalid output |

State is sourced to the **fix commits**, not to `/home/admin/.harness/pr704-verification-verdicts.md`,
whose headers still read `PARTIAL`/`NOT_CLOSED` because that ledger predates the fix batch.

### Q6 — "hardware-enforced budget constraints" — DISMISSED

Not our claim. `grep -rn "hardware-enforced\|hardware enforced"` across the repo returns
**zero hits**. The phrase was synthesised by the harness when rendering the diff into paper
form, and `ai-scientist-17` formally retracted it (bus #3933). What exists is a **software
pre-dispatch estimate** (`run_cmd.py:485`) with three disclosed limits: per-candidate not
per-task; inert for models absent from `_RATE_TABLE` (`:410`); heuristic input-token figure.
Recorded rather than silently "fixed" — fixing a claim we never made would write the
hallucination into our own record.

### Q7 — the constrained-Pareto algorithm, precisely

Objectives `(quality ↑, cost_dollar ↓, wall_clock_sec ↓)`. Dominance (`ledger.py:79-89`):
*A* dominates *B* iff *A* is at least as good on every objective and strictly better on at
least one, within a partition keyed `(ladder_id, base_model)`. Every seed row is written
with a **constant** partition — `ladder_id=f"job:{sig}"`, `base_model="adx-pool"`
(`run_cmd.py:246-247, 604-605`) — which is *why* cross-model dominance fires at all; had
`base_model` been the model name, dominance would be a no-op.

**Hard gates: `policy["gate"]` has ZERO consumers** — grepped over all `*.py`, no hits,
though `interview_cmd.py:71` faithfully collects it. The "constrained" half of
constrained-Pareto is **not wired**. This is #707 and it is the single reason v3 may not
yet claim to measure anything.

Undefined in code, stated rather than papered over: **NaN** — no guard; NaN comparisons are
all False, so a NaN row neither dominates nor is dominated and survives as a spurious
frontier point. **Inf** — no guard. **Tie-breaking** — undefined; falls out of ledger append
order, not deterministic across runs with concurrent writers. **Missing values** — rows
lacking a key are skipped at parse (`run_cmd.py:146-152`), silently shrinking the candidate
set. **Bounded exploration** — an `explore_rate` branch exists; it is *not* true that it
cannot displace the incumbent, since `best_model` re-runs selection over mean records on
every invocation (`run_cmd.py:342-344`).

### Q8 — preventing degenerate optima

**It does not prevent them. It detects one and announces it.** Deliberate:
`degenerate_primary_axis` (`run_cmd.py:323-341`) is computed at `:886`, printed as a WARNING
naming #708 at `:889-894`, exported in `--json` at `:907`. The guard **reports and does not
re-rank**, because silently re-ranking would hide the defect. The reviewer's line — *"the
selector degenerated in a way the prose description would never predict"* — is accurate and
is the best sentence in either review. Actual fix is #707 then #708. See also AS17-N3: a
second degeneracy this guard does **not** detect.

### Q9 — OverflowError on inflated quality

**Premise stale — fixed at `c588f778`.** `_parse_axes` guarded `(TypeError, ValueError)`;
`OverflowError` subclasses **neither** (it derives from `ArithmeticError`), so one poisoned
ledger row killed `adx run` with a bare traceback. Widened at `run_cmd.py:146-152` and at
every other `float()`/record-construction site taking ledger-controlled input, since they
share the failure class.

Why it was missed, recorded because the lesson generalises: our own adversarial sweep **did**
test inflated quality — as a `float` (`1e9`, correctly rejected) — and never as a large
`int`. *Testing one encoding of a value is not testing the value.*

As asked: rejection happens by **skipping the poisoned row at read time**, not by validating
at ledger-write time. Write-time validation is the better design and was previously unfiled —
now under AS17-LEDGER-DURABILITY.

### Q10 — seed-ledger guarantees

Fewer than "append-only ledger" implies. JSONL; plain appends (`run_cmd.py:181-189`).

| Property | Reality |
|---|---|
| Atomicity | **Not guaranteed** — no `fsync`, no lock. Sub-`PIPE_BUF` append atomicity is a platform property, not a guarantee of this code, and rows can exceed it |
| Crash consistency | Torn final line possible; reader skips unparseable rows → silent row loss |
| Concurrency | **UNSAFE** — no advisory locking; concurrent `adx run` invocations interleave |
| Tamper resistance | None — plain text, mode 0644, no checksum |
| Partial-run semantics | Rows appended per candidate as results arrive; an interrupted run reads as complete |
| Duplicate seeds | Not deduplicated; duplicates skew the mean that selection consumes |
| Schema changes | **Unhandled** — no schema-version field |

`attempts.json` *is* written atomically (`run_cmd.py:219-222`); the ledger is not.

### Q11 — how many tests exercise real bridge behaviour

**Zero.** Real totals are **255 passed / 1 skipped** (`agentdex_cli`) + **44 passed**
(`adx_frontier`) = 299/1 — the reviewer's "235" is stale. Of these, 7 tests touch the bridges
path (`test_run_cmd.py:484,530,553,567,703,771,828`) and **all 7 monkeypatch the dispatch**.
Method: `grep -n 'engine="bridges"'` cross-referenced against `grep -n monkeypatch` in the
same file; coverage corroborates (`_post_messages` `531-550` in `Missing`). The only real
sockets in the suite belong to `test_arena_ui.py` (`:121,125,129,169`) against a local stub.

### Q12 — baselines evaluated

**None.** No comparison against random, round-robin, or epsilon-greedy on the same pool
exists anywhere in the repo. This is exactly #708 and why the measurement-engine claim is
withheld. The reviewer's framing is worth preserving verbatim: passing tests prove the
selector is *correct*, not that it *picks good models*. A baseline harness would have caught
"selects for non-answers" immediately — which is why it belongs **before** any measurement
claim, not after.

### What this pass did NOT do

- **AS17-N1's stale comment is not fixed** (`openbox_cmd.py:159-164` still claims the
  empty-path branch is unreachable). Recorded, not corrected.
- **#707** (wire `policy["gate"]`, zero consumers) and **#708** (baseline harness, now also
  carrying AS17-N3) remain the preconditions before v3 may claim to measure anything.
- **#706** (openbox↔bridges contract) stays queued with mroute.

## Cross-references

- `cron/weekly_harness_audit.sh` §2 doctrine-vs-filesystem cross-check
  SHOULD grep this file for past-due `Until:` dates (post-H7 fix lands)
- `.supergoal/STATE.md` Notable events log captures cross-cutting
  doctrine pivots; this file captures fine-grained deferred-fix
  obligations that don't rise to a Notable event but must not be
  silently lost
- `~/.claude/projects/-home-admin-gh-agentdex-cli/memory/feedback_fix_all_before_moving_forward.md`
  — standing policy: when surfacing a ranked-issue list, work the queue
  top-to-bottom; this file is the ranked-issue list for phase-8 polish

## Session 2 lint follow-ups (post-DEFERRED-drain)

- PR #15 squash-merged with an unused SimpleNamespace import the CI flagged after-the-fact; PR #16 drops it. Doc-lint pairing for the import-drop lives in this note.
- PR #16 squash-merge still flagged a UP038 ruff rule in claude_bridge.py + a ruff-format diff in test_rate_table.py; PR #17 lands both fixes so main is green again.
- PR #18 wraps judge SDK calls in a 3-attempt exponential-backoff retry classifier (anthropic / openai / gemini exception names + Cloudflare 5xx body markers) so a transient upstream 525 / 502 / 503 does not excluded-fail every baseline in the Expedition.
- PR #19 adds --dangerously-skip-permissions to the claude cold-shot argv (was only in build_argv long-lived) so the fallback path does not hang on a stdin permission prompt + surfaces stdout in the CliDead message when stderr is empty.
- PR #20 honors explicit Cloudflare "retryable":false / "owner_action_required":true flags in the classifier so a 525 origin-config failure surfaces immediately instead of burning 14 s of exponential backoff.
- PR #21 drops unused `body` local var in PR-20 retry test (F841).
