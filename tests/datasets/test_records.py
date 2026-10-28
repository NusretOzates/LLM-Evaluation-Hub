"""Conversation record contract."""

import json
import math

import pytest
from pydantic import ValidationError

from llm_evaluation_hub.core.datasets.records import (
    AssistantMessage,
    ProcessedExample,
    UserMessage,
    encode_conversation,
    encode_expected_output,
    encode_extras,
)


def test_single_user_turn_gains_an_empty_system_message() -> None:
    example = ProcessedExample(conversation=[{"role": "user", "content": "Where is my order?"}])

    assert example.conversation[0].role == "system"
    assert example.conversation[0].content == ""
    assert example.conversation[1].role == "user"
    assert example.conversation[1].content == "Where is my order?"


def test_existing_system_prompt_is_preserved() -> None:
    example = ProcessedExample(
        conversation=[
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hello"},
        ]
    )

    assert len(example.conversation) == 2
    assert example.conversation[0].content == "Be brief."


def test_user_message_accepts_image_video_and_audio_parts() -> None:
    example = ProcessedExample(
        conversation=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "url": "https://example.com/a.png"},
                    {"type": "video", "path": "/tmp/clip.mp4"},
                    {"type": "audio", "url": "https://example.com/a.flac"},
                    {"type": "text", "text": "What is this?"},
                ],
            }
        ]
    )

    user = example.conversation[1]
    assert isinstance(user, UserMessage)
    assert isinstance(user.content, list)
    assert [part.type for part in user.content] == ["image", "video", "audio", "text"]


def test_media_part_requires_one_locator() -> None:
    with pytest.raises(ValidationError):
        ProcessedExample(
            conversation=[{"role": "user", "content": [{"type": "image"}]}],
        )


def test_tool_call_thinking_and_tool_result_round_trip() -> None:
    example = ProcessedExample(
        conversation=[
            {"role": "user", "content": "What is the temperature?"},
            {
                "role": "assistant",
                "thinking": "I should call the weather tool.",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "Istanbul"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "name": "get_weather", "content": "22"},
        ]
    )

    assistant = example.conversation[2]
    assert isinstance(assistant, AssistantMessage)
    assert assistant.thinking == "I should call the weather tool."
    assert assistant.tool_calls[0].function.arguments == {"city": "Istanbul"}
    payload = json.loads(encode_conversation(example.conversation))
    assert payload[2]["tool_calls"][0]["function"]["arguments"] == {"city": "Istanbul"}
    assert payload[3]["role"] == "tool"
    assert payload[3]["tool_call_id"] == "call-1"


def test_assistant_message_requires_content_tool_calls_or_thinking() -> None:
    with pytest.raises(ValidationError):
        ProcessedExample(
            conversation=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant"},
            ]
        )


def test_tool_result_requires_a_call_id() -> None:
    with pytest.raises(ValidationError):
        ProcessedExample(
            conversation=[
                {"role": "user", "content": "Hello"},
                {"role": "tool", "tool_call_id": "", "content": "22"},
            ]
        )


def test_expected_output_keeps_string_object_and_null_distinct() -> None:
    text = ProcessedExample(
        conversation=[{"role": "user", "content": "Classify"}],
        expected_output="refund",
    )
    structured = ProcessedExample(
        conversation=[{"role": "user", "content": "Classify"}],
        expected_output={"label": "refund"},
    )
    missing = ProcessedExample(conversation=[{"role": "user", "content": "Classify"}])

    assert encode_expected_output(text.expected_output) == '"refund"'
    assert encode_expected_output(structured.expected_output) == '{"label":"refund"}'
    assert encode_expected_output(missing.expected_output) is None


def test_extras_encode_as_a_json_object() -> None:
    example = ProcessedExample(
        conversation=[{"role": "user", "content": "Classify"}],
        extras={"rubric": "Prefer the refund policy."},
    )

    assert json.loads(encode_extras(example.extras)) == {"rubric": "Prefer the refund policy."}


def test_non_finite_expected_output_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProcessedExample(
            conversation=[{"role": "user", "content": "Classify"}],
            expected_output=math.nan,
        )


def test_segment_values_are_strings_and_keys_are_column_names() -> None:
    example = ProcessedExample(
        conversation=[{"role": "user", "content": "Merhaba"}],
        segments={"language": "tr", "difficulty": "hard"},
    )

    assert example.segments == {"language": "tr", "difficulty": "hard"}
    with pytest.raises(ValidationError):
        ProcessedExample(
            conversation=[{"role": "user", "content": "Merhaba"}],
            segments={"conversation": "tr"},
        )


def test_tools_preserve_order_and_nested_schemas_without_call_matching() -> None:
    payload = {
        "conversation": [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "old-call", "function": {"name": "historical", "arguments": {}}}
                ],
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Unicode: İade",
                    "strict": True,
                    "parameters": {
                        "$defs": {"key": {"type": "string"}},
                        "properties": {"id": {"$ref": "#/$defs/key"}},
                    },
                },
            }
        ],
    }
    example = ProcessedExample.model_validate(payload)
    assert example.model_dump(mode="json", exclude_none=True)["tools"] == payload["tools"]
    assert (
        ProcessedExample.model_validate({"conversation": [{"role": "user", "content": "x"}]}).tools
        == []
    )


@pytest.mark.parametrize(
    "tools",
    [
        None,
        [{"type": "function", "function": {"name": "", "parameters": {}}}],
        [{"type": "function", "function": {"name": "x", "parameters": []}}],
        [{"type": "function", "function": {"name": "x", "parameters": {"bad": math.inf}}}],
        [{"type": "function", "function": {"name": "x", "parameters": {1: "bad"}}}],
        [{"type": "function", "function": {"name": "x", "parameters": {"bad": object()}}}],
        [{"type": "function", "function": {"name": "x", "parameters": {}, "extra": 1}}],
        [{"type": "function", "function": {"name": "x", "parameters": {}, "strict": "true"}}],
        [{"type": "function", "function": {"name": "x", "parameters": {}, "description": None}}],
        [{"type": "function", "function": {"name": "x", "parameters": {}}}] * 2,
    ],
)
def test_malformed_available_tool_definitions_fail(tools: object) -> None:
    with pytest.raises(ValidationError):
        ProcessedExample.model_validate(
            {
                "conversation": [{"role": "user", "content": "x"}],
                "tools": tools,
            }
        )
