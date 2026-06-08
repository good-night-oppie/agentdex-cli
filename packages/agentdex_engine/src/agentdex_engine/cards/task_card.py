from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TaskCard(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    source_bundle_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_spec: dict
    oracle_spec_ref: str
    budget_token_cap: int = Field(ge=0)
    budget_dollar_cap: float = Field(ge=0.0)
    expected_output_kind: Literal["infographic", "report", "code", "answer", "trace"]
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
