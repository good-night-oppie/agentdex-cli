---
title: "Sample Infographic Description — NVIDIA Q3 FY2026"
status: active
owner: "@EdwardTang"
created: 2026-06-09
updated: 2026-06-09
type: reference
scope: tasks/nvidia-earnings-infographic/expected_outputs
layer: cross-cutting
cross_cutting: true
---

# Sample Infographic Description — NVIDIA Q3 FY2026

> Textual spec for what a passing infographic should contain. NOT a binary file; baselines emit infographic descriptions that the Oracle grades against this shape + the claim-evidence map. Per ADR-0009 §D5 M5 gate, the infographic-spec-plus-claim-evidence-map output kind is what's expected.

## Required sections (in order)

### 1. Headline section
- Quarter: Q3 FY2026 prominently displayed (ended October 26, 2025)
- Total revenue: $57.0B, with YoY (+62%) and QoQ (+22%) growth deltas
- GAAP gross margin: 73.4% (sequential improvement ~0.9pp from Q2 FY2026)
- Diluted GAAP EPS: $1.30
- Net income: $31.91B
- Visual: large numeric callouts with subtitles for context

### 2. Segment breakdown
- Bar chart or stacked bar: Data Center, Gaming, Professional Visualization, Automotive, OEM/Other
- Data Center dominance visualized (~90% of revenue)
- YoY growth per segment annotated (Data Center +66%, Gaming +30%, ProViz +56%, Auto +32%, OEM/Other +79%)
- Data Center sub-segment callouts: Compute $43.03B (+56% YoY) + Networking $8.19B (+162% YoY)
- Sum-to-total invariant: segments must sum to $57.0B (chart_sanity rubric item 3)

### 3. Product family timeline
- Three-track horizontal timeline: prior Blackwell, Blackwell Ultra (lead architecture), Rubin family (succession on track)
- Shipment pace callout: 1,000+ Blackwell racks per week
- $500B Blackwell + Rubin opportunity through CY2026 (CFO disclosure) called out as forward-looking
- Color encoding: continued demand for prior Blackwell, bright for Blackwell Ultra lead, distinct for Rubin succession

### 4. Geographic split
- Pie or donut: US 55%, Taiwan 16%, China 3%, Other 26%
- China inset with context: H20 sales insignificant in Q3; Q4 outlook assumes zero data center compute from China
- Total cited: $57.0B (matches headline)

### 5. Forward guidance
- Q4 FY2026: $65.0B ± 2% revenue guidance (~14% sequential growth at midpoint)
- Non-GAAP gross margin guidance: 75.0% ± 50 bps
- Tax rate: 17%
- Visual distinction from actuals: dashed border, "GUIDANCE" label, or shaded background (chart_sanity rubric item 5)

### 6. Cash + capital return context
- Net income: $31.91B
- Cash + securities: $69.8B
- Quarterly cash dividend: $0.01 per share (paid December 26, 2025)
- Share repurchases continue per existing authorization
- Visual: stacked bar OR side-by-side cards

## Narrative arc (text accompanying the visualization)

1. **Opening:** "Q3 FY2026 was a record quarter for NVIDIA: $57.0B revenue, up 62% YoY, driven by Data Center at $51.21B."
2. **Middle:** Three platform shifts framing (accelerated computing, generative AI mainstreaming, agentic AI emergence); networking emerges as the new #2 business, overtaking Gaming.
3. **Roadmap:** Blackwell Ultra is the lead architecture across every customer tier; shipment pace exceeds 1,000 racks per week; Rubin succession on track.
4. **Geography + risk:** H20 sales insignificant; Q4 outlook excludes data center compute from China.
5. **Closing:** Q4 guidance reflects continued Blackwell + Blackwell Ultra demand; CFO frames the $500B Blackwell + Rubin opportunity through CY2026.

## Citation requirement

Every numeric claim in the description AND every callout in the visualization must carry a `source: <file>:<line>` annotation referencing the source bundle. Missing citation triggers a `Seed(kind="provenance_required", seed_provenance="structural")`.

## What this is NOT

- Not a stock-recommendation document.
- Not an analyst price-target update.
- Not a quarter-over-quarter comparison only — YoY context required.
- Not a charts-without-narrative dump — the narrative arc is part of the rubric.
- Not an actuals-vs-guidance conflation — see chart_sanity rubric item 5.
