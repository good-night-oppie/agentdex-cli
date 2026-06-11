---
title: "BENE 2.0 design defense cards (12)"
status: active
owner: "@EdwardTang"
created: 2026-06-11
updated: 2026-06-11
type: reference
scope: "task-prep/apple-em/bene2-kit"
layer: cross-cutting
cross_cutting: true
name: bene2-design-defense-cards
description: Twelve challenge→answer cards defending the BENE 2.0 design decisions (D1–D10) for the Apple EM screen.
---

# BENE 2.0 — Design Defense Cards

Prep for: HM screen, Engineering Manager — AI Developer Tools, Apple DevEx (req 200658219-3337, Seattle), Fri 2026-06-12 11:30 AM PT.

Sources (all on disk, all verifiable): `docs/design/DESIGN-RATIONALE.md` (D1–D10), `docs/design/BENE2-DESIGN.md` (pillars, subsumption table, autonomy ladder), `docs/design/KERNEL-SPEC.md`, `docs/research/GAP-AUDIT.md` (14 KAOS + 13 BENE evidenced shortcomings), `docs/research/SYNTHESIS.md` (48 citations).

**Honesty line (use verbatim if pressed):** BENE 0.2.0 is built and verified — shipped 2026-06-11 evening, 699 passing tests (145 kernel, +84 Round-3), 37 MCP tools, kernel phases 4–10 done. The claims audit (docs/design/CLAIMS-AUDIT.md) marks the remaining gaps as planned: skill decay/demotion, nightly consolidation scheduler, runner wiring of ContextOS/loop guards, entropy-routed retrieval, deterministic replay. I will never present a planned feature as working — and the audit is how you can check me.

---

## Card 1 — "Why not just use or extend KAOS? Why a third framework?"

**Q:** You already had two frameworks. Isn't a third just churn?

**A:** It isn't a third codebase — that's the point of D10. BENE 2.0 is an additive kernel inside the existing BENE repo: legacy modules stay untouched and green — verified at every one of the 16 commits; the full suite now sits at 699 passing with 145 new kernel tests plus 84 Round-3 gap-closure tests — adapters mirror writes, supersession is feature-flagged. I didn't extend KAOS because my own audit (GAP-AUDIT) found its structural gaps with command-level evidence: no durable runtime (KAOS-1), SQLite hard-wired with no storage protocol (KAOS-2), an autonomy ladder that exists only as markdown — `grep autonomy kaos/ = 0 hits` (KAOS-3). BENE 0.1.0 already held exactly those surfaces (Temporal, storage protocol, runtime abstraction). The 55-row subsumption table shows 2.0 subsumes both lineages: 20 kept, 11 kept+, 7 re-derived, 17 surpassed.

## Card 2 — "Why local-first SQLite? Does this scale?"

**Q:** A single .db file feels like a toy. How does this survive real load?

**A:** D5 resolves this by separating planes. The data plane stays one auditable SQLite file because legibility is the product — a human or an agent can `sqlite3` into the whole engagement. The execution plane is already Temporal: durable, distributed, retry/replay — the edge KAOS lacks (KAOS-1). When an engagement outgrows one file, the storage protocol (idempotency keys, SQLite + Postgres backends, verified in 0.1.0) swaps the backend without touching the kernel. Scale-out is horizontal engagement sharding plus hub sync, not a cluster dependency. This was the decision the scale instinct pushed hardest against, and the rationale records that tension explicitly — a framework that needs a cluster to demo has already lost the demo.

## Card 3 — "Why evolve harness text instead of fine-tuning the model?"

**Q:** Fine-tuning is the serious approach. Text evolution sounds like prompt fiddling.

**A:** D7, three reasons. Durability: every model upgrade resets a fine-tune but amplifies a good harness — the harness survives the model. Inspectability: the AlphaGo "bug in knowledge" lesson — you can't tinker with a network without affecting how it works; the harness is the layer you can inspect and roll back. Cost: text evolution runs on a laptop; RL-tuning doesn't. And it's not prompt fiddling — AHE found prompt-only edits scored *below seed*, so the genome is structured (memory policy, retrieval policy, tool config, prompt) with per-component credit assignment (ADOPT-style). The honest ceiling is stated in the rationale: BENE's claim is reaching the model's ceiling reliably, not raising it.

## Card 4 — "Why falsifiable probes instead of benchmarks?"

**Q:** Everyone uses benchmarks. Why invent your own evaluation religion?

**A:** Because benchmark score and real-world generalization demonstrably disconnect — the eval-vs-reality disconnect is one of the field's best-documented embarrassments, and 2025 was the year much of the field admitted it out loud (D6). A probe is a pre-registered, sha256-locked spec with kill gates yielding ACCEPT/REJECT/VOID; tampering makes it refuse to run, and the admissibility self-test voids any probe whose baseline can't trigger a kill — dishonest probes are cheap to detect. Benchmarks aren't discarded: they remain fitness signals *inside* evolution, never promotion evidence. The discipline has a track record: KAOS v0.9 evaluated six candidates under it and shipped zero — REJECT counted as success. No retune-and-rerun: a gate you can renegotiate after seeing results is not a gate.

## Card 5 — "How does this translate to Apple DevEx? What would you build first?"

**Q:** This is your personal project. What's the first thing you'd actually build for our engineers?

**A:** The trust surface, not another agent. Pillar 5's thesis is the DevEx hook: engineers adopt agent tooling only when they trust it — make every claim checkable. Concretely, first quarter: provenance on agent output (what trace produced this change), a computed per-agent trust report (D8's four deterministic signals), and context-assembly manifests showing what the agent saw and dropped — layered onto whatever internal agent tooling Apple already runs, not replacing it. Second: the experience bar — first-run under 60 seconds, keyless, guidance instead of tracebacks, `--json` everywhere for composability. These mechanisms shipped in 0.2.0 — mandatory provenance, `bene trust`, ContextOS manifests — so at Apple I'd be adapting working mechanisms to the existing stack, not importing my codebase or selling a paper design.

## Card 6 — "How would you staff and sequence this as an EM?"

**Q:** Team shape and milestones — walk me through it.

**A:** I'd run the sequence I actually ran: evidence first (GAP-AUDIT-style audit of existing tooling, with command-level receipts), then design with recorded tensions (D1–D10 each document who pushed back and how it resolved), then additive build — existing surface green at every commit (D10), phase-numbered port plan (KERNEL-SPEC §4), claims audit at the end. Team shape: small and ownership-based — a substrate/platform owner, an eval-and-trust owner, an experience/CLI owner — mirroring the pillars. Sequencing follows a 70/30 dual-track: most capacity keeps the working system scaling while the new core grows beside it, and you pivot hard only at the proof point — after the win, not before. Milestones are gated on probe ACCEPTs, not demos.

## Card 7 — "What would you cut under deadline pressure?"

**Q:** Six weeks to ship. What goes?

**A:** Cut by the design's own non-goals (BENE2-DESIGN §6) and the claims audit's planned column. Defer: the still-planned column — nightly consolidation scheduler, entropy-routed retrieval, deterministic replay, the Postgres/scale path (D5 says it's pluggable, so it can wait) — plus LLM-based pollution scorers, because D9 deliberately puts deterministic signals first and the scorer interface is pluggable above the kernel. The harness middleware (sweeper, guards) already shipped cheap and is built to be deleted, so it costs nothing to keep. Never cut: kill-gated promotion (D3 — `PromotionBlocked` is a kernel exception, not a convention), mandatory provenance, and the legacy suite staying green. The rationale's own line is the answer: a gate you can renegotiate under pressure is not a gate. Cutting verification to ship faster is how you ship slop faster.

## Card 8 — "How do you stop agents from shipping slop at scale?"

**Q:** Agents generate volume. How do you keep that from rotting the codebase?

**A:** Defense in depth, all shipped in 0.2.0 (the one tracked gap: wiring loop guards into the live runner loop). Promotion gates: nothing evolved goes active without an ACCEPT verdict (D3), and the verifier is process-isolated from the evolver — AEVO observed reward hacking in 2 of 3 runs when that boundary was removed. Blast radius: the autonomy ladder (D4) keeps agents at L2 sandbox until trust is earned per capability domain; denials are recorded. Continuous GC: an on-demand debt sweeper (`bene sweep`; scheduling it is a cron line away) scans for slop signatures — debug prints, stale TODOs, duplicated blocks, dead imports — emitting report engrams (pillar 4, after OpenAI's harness-engineering pt 7). Loop guards trip on repeated near-identical actions. And the default-fail stance: everything is unverified until an end-to-end check says otherwise.

## Card 9 — "Why should an engineer trust agent output — concretely?"

**Q:** Not philosophy. What does the engineer actually see?

**A:** Three artifacts, all specified in pillar 5 and D8. First, `bene trust <agent>`: a computed ledger — verification coverage, audit completeness, checkpoint discipline, recency-weighted outcome reliability — per capability domain, never one magic number, formulas documented and deterministic. Trust is computed from logged events, never declared; a claim with no verifying event scores against the agent. Second, provenance: every engram requires it, so "which traces does this skill compress, and did they pass eval?" is one lineage query. Third, the context manifest: exactly what the agent saw and what was dropped when it produced the output. Goodhart is addressed: trust inputs are themselves gated verification artifacts. Status: shipped in 0.2.0 — `bene trust` is a live CLI command, provenance is enforced at engram write time, and ContextOS emits budget-capped context manifests as a kernel module (wiring it into the live runner loop is the one tracked next step).

## Card 10 — "What's the 6-month roadmap and how do you measure it?"

**Q:** Where is this in six months, and how do I know it's working?

**A:** Honestly: the kernel shipped last night — phases 4–10 done, 0.2.0 out, closed with a claims audit reconciling implemented vs planned. The next six months are the audit's planned column: skill decay/demotion, nightly consolidation scheduler, runner wiring of ContextOS and loop guards, entropy-routed retrieval, deterministic replay tooling. Measurement stays the same litmus tests: full suite green (699 today), `bene demo` keyless in ~0.3s, probe ACCEPTs per pillar, trust ledger live and consumed by L3/L4 gating. Every milestone is a falsifiable artifact — which is also how I'd report progress upward.

## Card 11 — "Isn't this over-engineered? Ten decisions through three famous lenses sounds like decoration."

**Q:** Engram ladders, autonomy ladders, a three-lens rationale — is this architecture astronautics?

**A:** The lenses are three questions — what would prove this wrong (science), what's the smallest representation that still works (compression), what breaks at the tail (engineering) — and the proof they're not decoration is that several decisions came out *differently* than a single-lens design would: in D10, the compression lens's clean-rewrite purity loses to deployment realism; in D5, the scale instinct loses to separation of planes. The anti-over-engineering pushback is itself built into the architecture — D1 keeps the substrate deliberately thin (kind, tier, payload-ref, provenance, links) precisely because a universal store risks doing nothing well, and D10 forbids the big-bang rewrite. Every tension is recorded with its resolution, which is the project's thesis applied to itself: make every claim checkable, including the design's own.

## Card 12 — "What failed in v1? What did your own audit find?"

**Q:** You audited your own frameworks. What's the most embarrassing finding?

**A:** GAP-AUDIT documents 13 evidenced shortcomings of BENE 0.1.0 — my own code — with the same command-level rigor I applied to KAOS. The sharpest: Pareto multi-objective search existed but promotion was completely ungated — every candidate joined the archive directly (BENE-9); no falsifiable eval anywhere (BENE-1); shared-log votes unweighted with no trust ledger (BENE-8); and doc drift on my own headline number — CLAUDE.md claimed 18 MCP tools while the server had 37 (BENE-12), the exact rot I criticize elsewhere. Each finding maps to a D-decision: BENE-9 drove D3's kill gates, BENE-8 drove D8's trust ledger. The audit culture is the product: I graded my own work before redesigning it.

---

*12 cards. All claims trace to docs read on disk; the 2.0 kernel shipped 2026-06-11 (phases 4–10, v0.2.0, 699 tests post-Round-3) — remaining gaps tracked as planned in CLAIMS-AUDIT.md.*
