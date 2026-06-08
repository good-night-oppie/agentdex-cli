"""TaskCard fixtures — ≥3: positive, negative (forbid violation), boundary."""

POSITIVE = {
    "id": "nvidia-earnings-infographic-q3-fy2026",
    "source_bundle_hash": "a" * 64,
    "environment_spec": {"runtime": "python>=3.11", "deps": ["pydantic>=2.0"]},
    "oracle_spec_ref": "tasks/nvidia-earnings-infographic/oracle/spec.yaml",
    "budget_token_cap": 200000,
    "budget_dollar_cap": 5.0,
    "expected_output_kind": "infographic",
    "version": "0.1.0",
}

NEGATIVE_EXTRA_FIELD = {
    **POSITIVE,
    "rogue_field": "should be forbidden by extra=forbid",
}

BOUNDARY_MIN_BUDGET = {
    **POSITIVE,
    "id": "min-budget-edge",
    "budget_token_cap": 0,
    "budget_dollar_cap": 0.0,
}
