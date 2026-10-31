"""Shared Chat Completions transport and response interpretation."""

import asyncio
import json
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

from jsonschema import Draft202012Validator
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, omit
from pydantic import TypeAdapter
from referencing import Registry

from llm_evaluation_hub.core.datasets.records import JsonValue, parse_json_value
from llm_evaluation_hub.inference.contracts import OutputFormat, RowResult

_JSON_VALUE = TypeAdapter(JsonValue)


class AttemptLimiter(Protocol):
    """An asynchronous attempt admission gate."""

    async def acquire(self) -> None:
        """Wait until an attempt may start."""


class AuthenticationFailure(Exception):
    """The endpoint rejected credentials."""


def interpret(raw: dict[str, Any], result: RowResult, output: OutputFormat) -> None:
    """Preserve and classify provider output without retrying validation failures."""
    result.raw_response = raw
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        result.status = "invalid_response"
        result.error = "endpoint response has no completion choice"
        return
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        result.status = "invalid_response"
        result.error = "endpoint response has no assistant message"
        return
    content = message.get("content")
    calls = message.get("tool_calls")
    finish_reason = choice.get("finish_reason")
    if (
        (content is not None and not isinstance(content, str))
        or (calls is not None and not isinstance(calls, list))
        or (finish_reason is not None and not isinstance(finish_reason, str))
    ):
        result.status = "invalid_response"
        result.error = "endpoint response has invalid message fields"
        return
    result.content = content
    result.tool_calls = calls
    result.finish_reason = finish_reason
    result.usage = raw.get("usage")
    result.status = "ok"
    if message.get("refusal"):
        result.status = "refusal"
    elif result.finish_reason == "length":
        result.status = "truncated"
    elif result.tool_calls and not result.content:
        result.status = "tool_calls"
    elif output.kind != "text":
        try:
            parsed = json.loads(result.content or "", parse_constant=_reject_constant)
            result.parsed = _JSON_VALUE.validate_python(parse_json_value(parsed))
            if output.kind == "json_object" and not isinstance(result.parsed, dict):
                result.validation_errors = ["expected a JSON object"]
            elif output.kind == "json_schema":
                assert output.schema_ is not None
                result.validation_errors = [
                    error.message
                    for error in Draft202012Validator(
                        output.schema_, registry=Registry()
                    ).iter_errors(result.parsed)
                ]
            if result.validation_errors:
                result.status = "schema_mismatch"
        except ValueError:
            result.status = "malformed_json"
        except Exception:
            result.status = "schema_mismatch"
            result.validation_errors = ["schema reference could not be resolved"]


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def retry_delay(header: str | None, attempt: int) -> float:
    """Respect either Retry-After representation; bound only local backoff."""
    if header:
        try:
            seconds = float(header)
        except ValueError:
            try:
                date = parsedate_to_datetime(header)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=UTC)
                seconds = (date - datetime.now(UTC)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                seconds = float(2**attempt)
        return max(0.0, seconds)
    return min(2**attempt, 60)


async def send(  # noqa: PLR0913
    client: AsyncOpenAI,
    body: dict[str, Any],
    output: OutputFormat,
    result: RowResult,
    *,
    timeout: float,
    retries: int,
    limiter: AttemptLimiter,
    omit_auth: bool = False,
) -> RowResult:
    """Send counted attempts, retry transient errors, and classify the final response."""
    started = time.monotonic()
    fields = {
        "model",
        "messages",
        "tools",
        "response_format",
        "stream",
        "n",
        "max_tokens",
        "max_completion_tokens",
        "temperature",
        "top_p",
        "seed",
    }
    known = {key: value for key, value in body.items() if key in fields}
    extra = {key: value for key, value in body.items() if key not in fields}
    for attempt in range(retries + 1):
        await limiter.acquire()
        result.attempts = attempt + 1
        try:
            response = await asyncio.wait_for(
                client.chat.completions.with_raw_response.create(
                    **known,
                    extra_body=extra,
                    extra_headers={"Authorization": omit} if omit_auth else {},
                ),
                timeout=timeout,
            )
            result.error = None
            try:
                raw = _JSON_VALUE.validate_python(
                    parse_json_value(
                        json.loads(response.http_response.text, parse_constant=_reject_constant)
                    )
                )
            except ValueError:
                result.raw_response = response.http_response.text
                result.status = "invalid_response"
                result.error = "endpoint response is not valid JSON"
            else:
                if isinstance(raw, dict):
                    interpret(raw, result, output)
                else:
                    result.raw_response = raw
                    result.status = "invalid_response"
                    result.error = "endpoint response is not a JSON object"
            break
        except APIStatusError as exc:
            if exc.status_code in (401, 403):
                raise AuthenticationFailure from None
            result.error = f"endpoint returned HTTP {exc.status_code}"
            if exc.status_code != 429 and exc.status_code < 500:
                break
            delay = exc.response.headers.get("retry-after")
        except (APIConnectionError, APITimeoutError, TimeoutError):
            result.error = "connection or timeout failure"
            delay = None
        if attempt < retries:
            wait = retry_delay(delay, attempt)
            await asyncio.sleep(wait)
    result.latency_ms = (time.monotonic() - started) * 1000
    return result
