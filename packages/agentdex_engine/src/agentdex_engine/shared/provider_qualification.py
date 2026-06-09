"""OpenAI and Anthropic provider qualification contracts.

This module does not call external APIs. It encodes the provider-facing
request-shape gates that Agentdex adapters must pass before live API wiring.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

OPENAI_QUALIFIED_MODEL = "gpt-5.5"
ANTHROPIC_QUALIFIED_MODEL = "claude-opus-4-8"

_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}
_VERBOSITIES = {"low", "medium", "high"}


class Provider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class ApiSurface(StrEnum):
    OPENAI_RESPONSES = "openai.responses"
    ANTHROPIC_MESSAGES = "anthropic.messages"


class ToolContract(BaseModel):
    """Provider-neutral tool contract with strict JSON Schema semantics."""

    name: str
    description: str
    input_schema: dict[str, Any]
    input_examples: list[dict[str, Any]] = Field(default_factory=list)
    strict: bool = True
    cacheable: bool = False

    @field_validator("name")
    @classmethod
    def _valid_tool_name(cls, value: str) -> str:
        if not _TOOL_NAME_RE.fullmatch(value):
            raise ValueError("tool name must match ^[a-zA-Z0-9_-]{1,64}$")
        return value

    @field_validator("description")
    @classmethod
    def _detailed_description(cls, value: str) -> str:
        if len(value.strip()) < 80:
            raise ValueError("tool description must be detailed enough for model selection")
        return value

    @model_validator(mode="after")
    def _strict_schema(self) -> ToolContract:
        schema_type = self.input_schema.get("type")
        if schema_type != "object":
            raise ValueError("tool input_schema must be an object schema")
        if not isinstance(self.input_schema.get("properties"), dict):
            raise ValueError("tool input_schema must define object properties")
        if self.input_schema.get("additionalProperties") is not False:
            raise ValueError("strict tools require additionalProperties=false")
        required = self.input_schema.get("required")
        if not isinstance(required, list):
            raise ValueError("strict tools require an explicit required list")
        if not self.strict:
            raise ValueError("provider qualification requires strict tool schemas")
        required_names = set(required)
        property_names = set(self.input_schema["properties"])
        missing = sorted(required_names - property_names)
        if missing:
            raise ValueError(f"required fields missing from properties: {missing}")
        for example in self.input_examples:
            missing_example_fields = required_names - set(example)
            if missing_example_fields:
                raise ValueError(
                    f"input_examples must include required fields: {sorted(missing_example_fields)}"
                )
        return self

    def to_openai_responses_tool(self) -> dict[str, Any]:
        """Return an OpenAI Responses API function tool definition."""

        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
            "strict": True,
        }

    def to_anthropic_messages_tool(self) -> dict[str, Any]:
        """Return an Anthropic Messages API client-tool definition."""

        tool: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "strict": True,
        }
        if self.input_examples:
            tool["input_examples"] = self.input_examples
        if self.cacheable:
            tool["cache_control"] = {"type": "ephemeral"}
        return tool


class ProviderQualification(BaseModel):
    """A local, testable provider qualification profile."""

    provider: Provider
    api_surface: ApiSurface
    model: str
    tools: list[ToolContract]
    reasoning_effort: str | None = None
    text_verbosity: str | None = None
    prompt_cache_static_prefix: bool = False
    mcp_capable: bool = False
    trace_capable: bool = False

    @model_validator(mode="after")
    def _provider_requirements(self) -> ProviderQualification:
        if not self.tools:
            raise ValueError("provider qualification requires at least one tool contract")

        if self.provider == Provider.OPENAI:
            if self.api_surface != ApiSurface.OPENAI_RESPONSES:
                raise ValueError("OpenAI qualification requires the Responses API")
            if self.model != OPENAI_QUALIFIED_MODEL:
                raise ValueError(f"OpenAI qualification model must be {OPENAI_QUALIFIED_MODEL}")
            if self.reasoning_effort not in _REASONING_EFFORTS:
                raise ValueError("OpenAI reasoning_effort must be low|medium|high|xhigh")
            if self.text_verbosity not in _VERBOSITIES:
                raise ValueError("OpenAI text_verbosity must be low|medium|high")
            if not self.prompt_cache_static_prefix:
                raise ValueError("OpenAI qualification requires prompt-cache-aware prompts")
            if not self.trace_capable:
                raise ValueError("OpenAI qualification requires trace-capable runs")

        if self.provider == Provider.ANTHROPIC:
            if self.api_surface != ApiSurface.ANTHROPIC_MESSAGES:
                raise ValueError("Anthropic qualification requires the Messages API")
            if self.model != ANTHROPIC_QUALIFIED_MODEL:
                raise ValueError(
                    f"Anthropic qualification model must be {ANTHROPIC_QUALIFIED_MODEL}"
                )
            if not self.prompt_cache_static_prefix:
                raise ValueError("Anthropic qualification requires prompt caching support")
            if not self.mcp_capable:
                raise ValueError("Anthropic qualification requires MCP-capable orchestration")

        return self

    def provider_request_skeleton(self) -> dict[str, Any]:
        """Return a provider-specific request skeleton suitable for docs/tests."""

        if self.provider == Provider.OPENAI:
            return {
                "model": self.model,
                "input": [],
                "tools": [tool.to_openai_responses_tool() for tool in self.tools],
                "reasoning": {"effort": self.reasoning_effort},
                "text": {"verbosity": self.text_verbosity},
                "truncation": "disabled",
            }

        return {
            "model": self.model,
            "max_tokens": 4096,
            "system": [
                {
                    "type": "text",
                    "text": "Static Agentdex battle contract and tool instructions.",
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [],
            "tools": [tool.to_anthropic_messages_tool() for tool in self.tools],
            "tool_choice": {"type": "auto"},
        }


class QualificationStatus(BaseModel):
    provider: Provider
    passed: bool
    model: str
    api_surface: ApiSurface
    checks: list[str]


def default_agentdex_tool_contracts() -> list[ToolContract]:
    """Return the minimal Agentdex tool surface shared by both providers."""

    return [
        ToolContract(
            name="agentdex_emit_stop",
            description=(
                "Emit an Agentdex stop signal when the agent needs approval, "
                "clarification, direction, a completion check, or a blocked-state "
                "decision. Use this tool instead of free text whenever execution "
                "should pause and the battle engine must checkpoint state."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "enum": [
                            "approval_needed",
                            "clarification_needed",
                            "direction_needed",
                            "completion_check",
                            "blocked",
                        ],
                        "description": "The stop reason understood by Agentdex.",
                    },
                    "context": {
                        "type": "string",
                        "description": "What the agent was doing when it stopped.",
                    },
                    "options": {
                        "anyOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "null"},
                        ],
                        "description": "Candidate next steps for direction_needed stops.",
                    },
                    "proposed_completion": {
                        "anyOf": [{"type": "object"}, {"type": "null"}],
                        "description": "Structured final payload for completion_check stops.",
                    },
                },
                "required": ["reason", "context", "options", "proposed_completion"],
                "additionalProperties": False,
            },
            input_examples=[
                {
                    "reason": "completion_check",
                    "context": "The requested code change and tests are complete.",
                    "options": None,
                    "proposed_completion": {"summary": "All checks passed."},
                }
            ],
            cacheable=True,
        )
    ]


def default_provider_qualification(provider: Provider) -> ProviderQualification:
    """Build the default qualification profile for one provider."""

    tools = default_agentdex_tool_contracts()
    if provider == Provider.OPENAI:
        return ProviderQualification(
            provider=Provider.OPENAI,
            api_surface=ApiSurface.OPENAI_RESPONSES,
            model=OPENAI_QUALIFIED_MODEL,
            tools=tools,
            reasoning_effort="high",
            text_verbosity="low",
            prompt_cache_static_prefix=True,
            trace_capable=True,
            mcp_capable=True,
        )

    return ProviderQualification(
        provider=Provider.ANTHROPIC,
        api_surface=ApiSurface.ANTHROPIC_MESSAGES,
        model=ANTHROPIC_QUALIFIED_MODEL,
        tools=tools,
        prompt_cache_static_prefix=True,
        mcp_capable=True,
    )


def qualification_status(provider: Provider) -> QualificationStatus:
    """Return a deterministic qualification status for CI and CLI smoke tests."""

    profile = default_provider_qualification(provider)
    checks = [
        f"model={profile.model}",
        f"api_surface={profile.api_surface.value}",
        "strict_tool_schema=true",
        "prompt_cache_static_prefix=true",
    ]
    if provider == Provider.OPENAI:
        checks.extend(
            [
                f"reasoning_effort={profile.reasoning_effort}",
                f"text_verbosity={profile.text_verbosity}",
                "trace_capable=true",
            ]
        )
    else:
        checks.append("mcp_capable=true")

    return QualificationStatus(
        provider=provider,
        passed=True,
        model=profile.model,
        api_surface=profile.api_surface,
        checks=checks,
    )
