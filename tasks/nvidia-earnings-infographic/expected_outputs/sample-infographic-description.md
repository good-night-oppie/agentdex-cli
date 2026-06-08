# Sample Infographic Description — NVIDIA Q3 FY2026

> Textual spec for what a passing infographic should contain. NOT a binary file; baselines emit infographic descriptions that the Oracle grades against this shape + the claim-evidence map. Per ADR-0009 §D5 M5 gate, the infographic-spec-plus-claim-evidence-map output kind is what's expected.

## Required sections (in order)

### 1. Headline section
- Quarter: Q3 FY2026 prominently displayed
- Total revenue: $35.08B, with YoY (+94%) and QoQ (+17%) growth deltas
- Operating margin or GAAP gross margin: 74.6%
- Diluted GAAP EPS: $0.78
- Visual: large numeric callouts with subtitles for context

### 2. Segment breakdown
- Bar chart or stacked bar: Data Center, Gaming, Professional Visualization, Automotive, OEM/Other
- Data Center dominance visualized (87.7% of revenue)
- YoY growth per segment annotated (Data Center +112%, Gaming +15%, ProViz +17%, Auto +72%, OEM/Other -3%)
- Sum-to-total invariant: segments must sum to $35.08B (chart_sanity rubric item 3)

### 3. Product roadmap timeline
- Three-track horizontal timeline: Hopper end-of-life, Blackwell volume ramp, Rubin sampling
- Time-axis: FY2026 Q3 → FY2027 H2
- Color encoding: muted for end-of-life, bright for volume product, distinct for sampling
- Rubin H2 CY2026 sampling milestone clearly marked as forward-looking

### 4. Geographic split
- Pie or donut: US 52%, Taiwan 14%, China 16%, Other 18%
- China inset with context: export-control regime, compliant SKU mix
- Total cited: $35.08B (matches headline)

### 5. Forward guidance
- Q4 FY2026: $37.5B ± 2% revenue guidance
- GAAP gross margin guidance: 73.0% ± 0.5pp
- Visual distinction from actuals: dashed border, "GUIDANCE" label, or shaded background (chart_sanity rubric item 5)

### 6. Cash + capex context
- Cash + securities: $38.50B
- Operating cash flow: $17.6B
- Capex: $1.85B
- Trailing-twelve-month capex: $5.20B
- Visual: stacked bar OR side-by-side cards

## Narrative arc (text accompanying the visualization)

1. **Opening:** "Q3 FY2026 was a record quarter for NVIDIA: $35.08B revenue, up 94% YoY, driven by Data Center."
2. **Middle:** Segment commentary (Data Center momentum, Gaming normalization, Auto strength, ProViz steady).
3. **Roadmap:** Blackwell shipping in volume; Rubin announced for FY2027 H2 ramp.
4. **Geography + risk:** China revenue $5.40B (16%) navigated through compliant SKUs; export controls remain a risk factor.
5. **Closing:** Q4 guidance reflects Rubin engineering ramp costs but continued demand strength.

## Citation requirement

Every numeric claim in the description AND every callout in the visualization must carry a `source: <file>:<line>` annotation referencing the source bundle. Missing citation triggers a `Seed(kind="provenance_required", seed_provenance="structural")`.

## What this is NOT

- Not a stock-recommendation document.
- Not an analyst price-target update.
- Not a quarter-over-quarter comparison only — YoY context required.
- Not a charts-without-narrative dump — the narrative arc is part of the rubric.
- Not an actuals-vs-guidance conflation — see chart_sanity rubric item 5.
