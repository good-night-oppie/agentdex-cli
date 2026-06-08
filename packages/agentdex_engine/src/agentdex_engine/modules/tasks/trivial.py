"""Trivial task + scorer for end-to-end smoke testing."""

from __future__ import annotations

from agentdex_engine.modules.tasks.models import ScorerSpec, TaskContext


class ExactMatchScorer:
    """Scores 1.0 if agent_output matches task.expected_output exactly; 0.0 otherwise.

    MVP objectives: accuracy + cost only. Latency-aware scoring lands when
    we have real agents with meaningful timing variance (PHASE-3).
    """

    def __init__(self, objectives: dict[str, str] | None = None) -> None:
        self._objectives = objectives or {
            "accuracy": "maximize",
            "cost": "minimize",
        }

    @property
    def objectives(self) -> dict[str, str]:
        return dict(self._objectives)

    def score(
        self, task: TaskContext, agent_output: str, *, elapsed_s: float = 0.0
    ) -> dict[str, float]:
        accuracy = (
            1.0
            if task.expected_output is not None and agent_output == task.expected_output
            else 0.0
        )
        scores: dict[str, float] = {"accuracy": accuracy, "cost": 1.0}
        if "latency_s" in self._objectives:
            scores["latency_s"] = elapsed_s
        return scores


TASK_REGISTRY: dict[str, TaskContext] = {
    "uppercase_input": TaskContext(
        id="uppercase_input",
        title="Uppercase the input",
        description="hello world",
        expected_output="HELLO WORLD",
        expects_human=False,
        scorer=ScorerSpec(
            name="exact_match",
            objectives={"accuracy": "maximize", "cost": "minimize"},
        ),
    ),
}


SCORER_REGISTRY: dict[str, type[ExactMatchScorer]] = {
    "exact_match": ExactMatchScorer,
}


def get_task(task_id: str) -> TaskContext:
    try:
        return TASK_REGISTRY[task_id]
    except KeyError as e:
        raise KeyError(f"unknown task {task_id!r}, known: {sorted(TASK_REGISTRY)}") from e


def make_scorer(spec: ScorerSpec) -> ExactMatchScorer:
    try:
        cls = SCORER_REGISTRY[spec.name]
    except KeyError as e:
        raise KeyError(f"unknown scorer {spec.name!r}, known: {sorted(SCORER_REGISTRY)}") from e
    return cls(objectives=spec.objectives)
