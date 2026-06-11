---
title: "Apple EM AI Tooling prep — package index"
status: active
owner: "@EdwardTang"
created: 2026-06-11
updated: 2026-06-11
type: reference
scope: "task-prep/apple-em-ai-tooling-enablement"
layer: cross-cutting
cross_cutting: true
name: apple-em-prep-index
description: Apple EM (AI Tooling & Enablement) interview prep package index — what's here, role ground truth, loop schedule, artifact layout.
---

# Apple EM (AI Tooling & Enablement) Interview Prep — Task Package

> Empty replica scaffolded 2026-06-10 from `../outreach-interview-problems/` (source
> session `aac77974`). Fill TODOs as intel lands; delete sections that don't apply.

Source session: `TODO` (cwd `TODO`)

## What's here

| Path | Contents |
|---|---|
| **`apple-prep-BILINGUAL.md`** | **Start here** — single consolidated prep doc (EN/中文 interleaved) — skeleton, fill as you go |
| `dialogue/` | Readable dialogue extracts from prep sessions (empty — see README) |
| `artifacts/` | Prep docs, cheatsheets, mocks, rig pointer, external intel |
| `artifacts/from-eddie-agi-kb/` | **OSINT corpus snapshot** — 159 files copied 2026-06-10 from `~/gh/harness-engineering/eddie-agi-kb/jobs/apple-em-aidev-2026/` (eddie-agi-kb-3 collection; re-sync from there as new OSINT lands) |
| `artifacts/resume/` | The exact resume submitted — what the HM has read |
| `artifacts/bene2/` | BENE 2.0 redesign interview kit (talk track, defense cards, 5-min demo script, paper Q&A) — built 2026-06-11 |
| `artifacts/apple_finalloop_INDEX.md` | Homework map — what to produce before the loop |
| `interview-env/` | Generic live-coding rig (copied verbatim from outreach — already battle-tested) |
| `prep-private/` | **Never screen-share** — pre-warmed drills & cribs |

## Role & people — GROUND TRUTH (verified vs sources 2026-06-10)

- **Role:** Engineering Manager, AI Developer Tools — Apple (req **200658219-3337**)
- **Org/Team:** Developer Experience (DevEx), Software & Services / Cloud & Infrastructure
- **Location:** Seattle, WA · posted 2026-04-17
- **JD:** https://jobs.apple.com/en-us/details/200658219-3337/engineering-manager-ai-developer-tools
- **HM:** NOT YET IDENTIFIED (top open gap — LinkedIn narrowing queued in eddie-agi-kb)
- **Recruiter:** TODO · **Scheduler:** TODO

## Loop

| When | Round | Lead | Shadow |
|---|---|---|---|
| **Fri 2026-06-12, 11:30 AM PT** | **Hiring manager screen (first round)** | HM (name TBD) | — |
| TBD | Full loop expected 4-7 rounds, behavioral-heavy (forum-sourced, confirm w/ recruiter) | TBD | TBD |

## eddie-agi-kb-3 claim audit (2026-06-10)

- ✅ 126 wiki source pages across 9 OSINT sources (23 blind / 8 github / 18 glassdoor / 4 job / 24 linkedin / 14 quora / 26 reddit / 4 wayback / 5 xcom)
- ✅ Ground truth anchored (req id, team, location, posted date — confirmed in `sources/job/01`)
- ✅ 5 BQ themes + 5 sysdesign cards + 16 concept pages + `rehearsal-deck.md` (all `status: draft`)
- ❌ **`LIVING-BRIEF.md` does NOT exist on disk** — claimed live, not found anywhere in harness-engineering; treat as vapor until the session ships it
- Open (per claim, unverified): 3 Blind posts behind auth wall (Camoufox tier-2), no X.com tier-1 key, Wayback force-archive pending

> EM-loop note: unlike the outreach Staff-SWE loop (coding + design), Apple EM loops
> typically weight people-management, cross-functional collaboration, and org/process
> design — confirm round mix with recruiter before building drills.

## Key intel from recruiter prep call

- TODO — round structure, interviewer names, rubric hints
- TODO — coding allowed/required? agent-assisted or raw?
- TODO — design variant (HLD vs LLD vs "how would you run this team/program")

## Comp

- TODO — band research (levels.fyi: Apple ICT/M-track for EM, Seattle/Cupertino)
- TODO — anchoring strategy; make recruiter reveal band first

## Per-interviewer prep convention

When interviewers are known, add per-interviewer files in `artifacts/` following the
outreach naming pattern: `apple_<firstname>_<round>_{prep,playbook,cheatsheet,mock_transcript}.md`

## Artifacts layout

```
artifacts/
├── apple_finalloop_INDEX.md         ← homework map (what to produce, status)
├── apple_external_intel.md          ← public research (Blind/Glassdoor/1p3a/LinkedIn)
├── apple_<interviewer>_<round>_*.md ← per-interviewer prep (create when known)
└── apple-prep/
    ├── logistics.md                 ← schedule, links, open threads
    ├── recruiter-followup-questions.md
    ├── cheatsheet-coding.md
    ├── cheatsheet-design.md
    ├── cheatsheet-behavioral.md     ← EM addition (not in outreach replica source)
    ├── rig/                         ← pointer to ../interview-env
    └── mocks/                       ← coding + design drill problems
```
