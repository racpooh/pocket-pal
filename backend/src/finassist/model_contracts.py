"""Provider-neutral adapter contracts (no SDK, network or financial authority).

Trusted application code supplies adapters; this is not a runtime plugin loader.
Adapters translate this transcript and JSON Schemas to their provider's wire format,
normalize responses/errors, and implement provider-specific usage accounting.
A new adapter still requires capability, policy and compatibility review.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, NotRequired, Protocol, TypedDict


class ToolCall(TypedDict):
    id: str
    name: str
    input: dict


class ChatMessage(TypedDict):
    role: Literal['user', 'assistant', 'tool']
    content: str
    tool_calls: NotRequired[list[ToolCall]]
    tool_call_id: NotRequired[str]


class ToolSpec(TypedDict):
    name: str
    description: str
    input_schema: dict


@dataclass
class ChatTurn:
    text: str
    tool_calls: list[ToolCall]
    stop: bool
    model_id: str
    # Normalized reason: adapters map output-limit stops to "max_tokens".
    stop_reason: str | None = None


class ChatModel(Protocol):
    """Requires text, JSON-schema tools and correlated tool-result continuations.

    Map provider output limits to max_tokens, preserving partial text. Raise
    ProviderError for retryable failures and FatalProviderError for permanent ones.
    Never execute tools inside the adapter: the owner-bound service owns dispatch.
    """
    def step(self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]) -> ChatTurn: ...


@dataclass
class ExtractionResult:
    fields: dict
    model_id: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class ExtractionProvider(Protocol):
    """Returns extraction fields for deterministic validation, never ledger writes."""
    def extract(self, image: bytes, mime: str) -> ExtractionResult: ...


class ProviderError(Exception):
    """Retryable provider failure (timeout, 5xx, malformed output)."""


class FatalProviderError(Exception):
    """Non-retryable authentication, permission, model or request failure."""
