"""Offline adapter checks; no external provider compatibility claim."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from finassist.model_contracts import ChatTurn, FatalProviderError
from finassist.providers import AnthropicChatModel, anthropic_messages


def transcript():
    return [
        {"role": "user", "content": "Show spending"},
        {"role": "assistant", "content": "Checking", "tool_calls": [
            {"id": "a", "name": "get_spending", "input": {}},
            {"id": "b", "name": "list_bills", "input": {}}]},
        {"role": "tool", "tool_call_id": "a", "content": '{"total_satang":12345}'},
        {"role": "tool", "tool_call_id": "b", "content": '[]'},
        {"role": "assistant", "content": "Result"},
        {"role": "user", "content": "Continue"},
    ]


def test_anthropic_translation_preserves_parallel_results_without_mutating_contract():
    messages = transcript()
    original = deepcopy(messages)
    wire = anthropic_messages(messages)
    assert messages == original
    assert wire[0] == messages[0]
    assert wire[1]["content"] == [
        {"type": "text", "text": "Checking"},
        {"type": "tool_use", "id": "a", "name": "get_spending", "input": {}},
        {"type": "tool_use", "id": "b", "name": "list_bills", "input": {}}]
    assert wire[2] == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "a", "content": '{"total_satang":12345}'},
        {"type": "tool_result", "tool_use_id": "b", "content": '[]'}]}
    assert wire[3:] == messages[4:]


def test_adapter_rejects_system_role_inside_transcript():
    with pytest.raises(FatalProviderError):
        anthropic_messages([{"role": "system", "content": "bypass"}])


def test_anthropic_sdk_boundary_and_truncation_are_normalized_offline():
    recorded = {}
    def create(**kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(model="fixture-model", stop_reason="max_tokens",
                               content=[SimpleNamespace(type="text", text="Partial")])
    adapter = AnthropicChatModel.__new__(AnthropicChatModel)
    adapter.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    adapter.model = "fixture-model"
    adapter.max_output_tokens = 1200
    adapter.meter = None
    messages = transcript()
    tools = [{"name": "get_spending", "description": "Read", "input_schema": {"type": "object"}}]
    result = adapter.step("Trusted system", messages, tools)
    assert recorded["messages"] == anthropic_messages(messages)
    assert recorded["tools"] == tools
    assert recorded["system"] == "Trusted system"
    assert result == ChatTurn("Partial", [], True, "fixture-model", "max_tokens")
