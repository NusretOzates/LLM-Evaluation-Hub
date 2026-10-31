"""Conversation records stored for later evaluation."""

import json
import math
import re
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    TypeAdapter,
    field_validator,
    model_serializer,
    model_validator,
)

_SEGMENT_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
RESERVED_COLUMNS = frozenset({"source_index", "conversation", "expected_output", "extras", "tools"})
_JSON_SEPARATORS = (",", ":")


def validate_segment_key(key: str) -> None:
    """Reject a segment name that cannot be a Parquet column."""
    if _SEGMENT_KEY.fullmatch(key) is None or key in RESERVED_COLUMNS:
        raise ValueError(f"invalid segment key: {key}")


def parse_json_value(value: object) -> object:
    """Return a JSON value and reject non-finite numbers and non-JSON objects."""
    if isinstance(value, bool) or value is None or isinstance(value, str | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers are not valid JSON values")
        return value
    if isinstance(value, dict):
        parsed: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            parsed[key] = parse_json_value(item)
        return parsed
    if isinstance(value, list):
        return [parse_json_value(item) for item in value]
    raise ValueError("value must be a JSON string, number, boolean, object, array, or null")


type JsonValue = str | bool | int | float | list["JsonValue"] | dict[str, "JsonValue"] | None


class TextPart(BaseModel):
    """A text content part."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["text"] = "text"
    text: str


class MediaPart(BaseModel):
    """An image, video, or audio part addressed by a URL or a local path."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["image", "video", "audio"]
    url: str | None = None
    path: str | None = None

    @model_validator(mode="after")
    def one_locator(self) -> Self:
        """Require exactly one non-empty locator."""
        locators = [locator for locator in (self.url, self.path) if locator is not None]
        if len(locators) != 1 or locators[0] == "":
            raise ValueError("a media part needs a url or a path")
        return self


ContentPart = Annotated[TextPart | MediaPart, Field(discriminator="type")]


class FunctionDefinition(BaseModel):
    """An available function schema, independent from historical calls."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    parameters: dict[str, JsonValue]
    description: str | None = None
    strict: bool | None = None

    @model_serializer(mode="wrap")
    def canonical_payload(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        """Omit absent optional fields so serialized definitions remain canonical."""
        payload = handler(self)
        return {key: value for key, value in payload.items() if value is not None}

    @field_validator("description", "strict", mode="before")
    @classmethod
    def optional_nonnull(cls, value: object) -> object:
        """Omitted optional fields are allowed; explicit null is not canonical."""
        if value is None:
            raise ValueError("optional tool fields must not be null")
        return value

    @field_validator("parameters", mode="before")
    @classmethod
    def finite_parameters(cls, value: object) -> object:
        """Preserve JSON schemas and reject unsupported/nonfinite contents."""
        if not isinstance(value, dict):
            raise ValueError("tool parameters must be a JSON object")
        return parse_json_value(value)


class ToolDefinition(BaseModel):
    """A canonical available function definition; never an executable capability."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["function"]
    function: FunctionDefinition


class FunctionCall(BaseModel):
    """A function call nested inside a tool call."""

    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, JsonValue]

    @model_validator(mode="before")
    @classmethod
    def parse_argument_string(cls, value: object) -> object:
        """Parse OpenAI-style JSON-string arguments into an object."""
        if not isinstance(value, dict):
            return value
        arguments = value.get("arguments")
        if not isinstance(arguments, str):
            return value
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise ValueError("tool call arguments must be a JSON object")
        updated = dict(value)
        updated["arguments"] = parsed
        return updated

    @model_validator(mode="after")
    def name_and_arguments(self) -> Self:
        """Reject an empty function name and non-finite argument numbers."""
        if self.name == "":
            raise ValueError("tool name must not be empty")
        parse_json_value(self.arguments)
        return self


class ToolCall(BaseModel):
    """An assistant function call."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["function"] = "function"
    function: FunctionCall

    @model_validator(mode="after")
    def id_present(self) -> Self:
        """Reject an empty tool-call id."""
        if self.id == "":
            raise ValueError("tool call id must not be empty")
        return self


class SystemMessage(BaseModel):
    """A system turn. Content may be empty."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system"] = "system"
    content: str


class UserMessage(BaseModel):
    """A user turn. Content is text or a list of typed parts."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user"] = "user"
    content: str | list[ContentPart]

    @model_validator(mode="after")
    def content_present(self) -> Self:
        """Reject an empty user turn."""
        if self.content == []:
            raise ValueError("user content must not be an empty list")
        return self


class AssistantMessage(BaseModel):
    """An assistant turn with text, tool calls, thinking, or any combination."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant"] = "assistant"
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    thinking: str | None = None

    @model_validator(mode="after")
    def payload_present(self) -> Self:
        """Require content, tool calls, or thinking."""
        if self.content is None and not self.tool_calls and self.thinking is None:
            raise ValueError("assistant message needs content, tool_calls, or thinking")
        return self


class ToolMessage(BaseModel):
    """A tool result addressed to a previous tool call."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["tool"] = "tool"
    content: str
    tool_call_id: str
    name: str | None = None

    @model_validator(mode="after")
    def call_id_present(self) -> Self:
        """Reject an empty tool-call id."""
        if self.tool_call_id == "":
            raise ValueError("tool_call_id must not be empty")
        return self


Message = Annotated[
    SystemMessage | UserMessage | AssistantMessage | ToolMessage,
    Field(discriminator="role"),
]
_MESSAGE_ADAPTER = TypeAdapter(Message)


def message_payload(message: Message) -> dict[str, object]:
    """Serialize one message, omitting empty tool-call lists and null optionals."""
    payload = message.model_dump(mode="json", exclude_none=True)
    if payload.get("tool_calls") == []:
        del payload["tool_calls"]
    return payload


def dump_json(value: object) -> str:
    """Encode a JSON value with stable separators."""
    return json.dumps(value, ensure_ascii=False, separators=_JSON_SEPARATORS, allow_nan=False)


def encode_conversation(messages: list[Message]) -> str:
    """Encode a conversation as a JSON array."""
    return dump_json([message_payload(message) for message in messages])


def encode_expected_output(value: JsonValue | None) -> str | None:
    """Encode gold output. None stays a null column, not the JSON text null."""
    if value is None:
        return None
    return dump_json(value)


def encode_extras(value: dict[str, JsonValue]) -> str:
    """Encode judge-context extras as a JSON object."""
    return dump_json(value)


def decode_message(payload: object) -> Message:
    """Parse one stored message object."""
    return _MESSAGE_ADAPTER.validate_python(payload)


class ProcessedExample(BaseModel):
    """One evaluation row after the processor runs."""

    model_config = ConfigDict(extra="forbid")

    conversation: list[Message] = Field(min_length=1)
    expected_output: JsonValue | None = None
    tools: list[ToolDefinition] = Field(default_factory=list)
    extras: dict[str, JsonValue] = Field(default_factory=dict)
    segments: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def reject_nonfinite_json(cls, value: object) -> object:
        """Reject non-finite numbers in gold output and extras before coercion."""
        if not isinstance(value, dict):
            return value
        if "expected_output" in value:
            parse_json_value(value["expected_output"])
        if "extras" in value and value["extras"] is not None:
            parse_json_value(value["extras"])
        return value

    @field_validator("tools")
    @classmethod
    def unique_tools(cls, tools: list[ToolDefinition]) -> list[ToolDefinition]:
        """Require unique function names within the example's ordered tool list."""
        names = [tool.function.name for tool in tools]
        if len(set(names)) != len(names):
            raise ValueError("tool definition names must be unique")
        return tools

    @model_validator(mode="after")
    def normalize(self) -> Self:
        """Check segment names."""
        for key in self.segments:
            validate_segment_key(key)
        return self
