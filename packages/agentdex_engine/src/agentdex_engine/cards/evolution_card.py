from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SeedCategory = Literal["source", "reasoning", "coding", "control", "harness"]


class Seed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_jsonl_excerpt: str
    confidence: Literal["low", "med", "high"]
    seed_provenance: Literal["structural", "learned"]


class EvolutionCard(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expedition_id: str = Field(min_length=1)
    parent_lineage_root: str | None = None
    winning_pattern: str
    losing_pattern: str
    mutation_seeds: dict[SeedCategory, list[Seed]]
    boundary_annotations: list[str] = Field(default_factory=list)
    langfuse_trace_urls: dict[str, str] = Field(default_factory=dict)
