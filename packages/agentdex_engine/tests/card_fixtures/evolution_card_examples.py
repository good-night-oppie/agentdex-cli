"""EvolutionCard fixtures — ≥3: positive, negative (forbid violation), boundary."""

POSITIVE = {
    "expedition_id": "nvidia-q3-fy2026-exp-001",
    "parent_lineage_root": None,
    "winning_pattern": "claude: cite each numeric claim w/ source:file:line; defer chart layout to final pass",
    "losing_pattern": "manus: skip provenance for derived metrics; oracle.hard rejects 3/9 claims",
    "mutation_seeds": {
        "source": [
            {
                "kind": "provenance_required",
                "description": "Bridge: enforce source:<file>:<line> tag after every numeric claim",
                "evidence_jsonl_excerpt": '{"turn": 4, "agent": "manus", "claim": "revenue_total=35.08B", "source": null}',
                "confidence": "high",
                "seed_provenance": "structural",
            }
        ],
        "reasoning": [
            {
                "kind": "oracle_repair",
                "description": "Soft Oracle uncertainty=0.72 on chart_sanity rubric; strengthen rubric w/ explicit chart-type heuristics",
                "evidence_jsonl_excerpt": '{"verdict_kind": "soft", "uncertainty": 0.72, "rubric": "chart_sanity.md"}',
                "confidence": "med",
                "seed_provenance": "structural",
            }
        ],
    },
    "boundary_annotations": [
        "All seeds structural per M5 gate; learned seeds deferred to M7 seed_extractor.",
    ],
    "langfuse_trace_urls": {
        "claude": "https://cloud.langfuse.com/trace/trace_claude_001",
        "codex": "https://cloud.langfuse.com/trace/trace_codex_001",
        "manus": "https://cloud.langfuse.com/trace/trace_manus_001",
    },
}

NEGATIVE_BAD_CATEGORY_KEY = {
    **POSITIVE,
    "mutation_seeds": {
        "wrong_category": [],  # not in SeedCategory literal — must fail
    },
}

BOUNDARY_EMPTY_SEEDS_ALL_CATEGORIES = {
    **POSITIVE,
    "expedition_id": "nvidia-q3-fy2026-exp-edge-empty",
    "mutation_seeds": {
        "source": [],
        "reasoning": [],
        "coding": [],
        "control": [],
        "harness": [],
    },
    "boundary_annotations": [
        "Edge case: all categories present but empty; M5 gate would fail (needs ≥2 categories with entries).",
    ],
}
