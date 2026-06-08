"""ResultCard fixtures — ≥3: positive, negative (forbid violation), boundary."""

POSITIVE = {
    "expedition_id": "nvidia-q3-fy2026-exp-001",
    "task_id": "nvidia-earnings-infographic-q3-fy2026",
    "agent_id": "claude",
    "pass_rate": 0.85,
    "cost_dollar": 0.42,
    "cost_token": 18500,
    "speed_wall_clock_sec": 47.3,
    "failure_trace_path": None,
    "pareto_position": "undominated",
    "langfuse_trace_id": "trace_abc123",
    "langfuse_trace_url": "https://cloud.langfuse.com/trace/trace_abc123",
}

NEGATIVE_OUT_OF_RANGE_PASS_RATE = {
    **POSITIVE,
    "pass_rate": 1.5,  # > 1.0, must fail
}

BOUNDARY_ZERO_PASS_RATE = {
    **POSITIVE,
    "expedition_id": "nvidia-q3-fy2026-exp-edge-zero",
    "agent_id": "codex",
    "pass_rate": 0.0,
    "cost_dollar": 0.0,
    "cost_token": 0,
    "speed_wall_clock_sec": 0.0,
    "pareto_position": "dominated",
    "failure_trace_path": "expeditions/.../trace/codex_full_trace.jsonl",
    "langfuse_trace_id": None,
    "langfuse_trace_url": None,
}
