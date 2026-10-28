"""Real Monty isolation, budget and processor-boundary regressions."""

import hashlib
import os
import signal
from pathlib import Path
from time import perf_counter

import pytest

from llm_evaluation_hub.imports.runtime import (
    ProcessorError,
    ProcessorRunner,
    validate_json_budget,
)

GOOD = """def process(row):
    return {"conversation": [{"role": "user", "content": row["text"]}],
            "expected_output": row.get("answer"), "tools": row.get("tools", [])}
"""
TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_order",
        "parameters": {
            "type": "object",
            "properties": {
                "order": {
                    "type": "object",
                    "properties": {"items": {"type": "array", "items": {"type": "string"}}},
                }
            },
        },
    },
}


def test_nested_tools_and_skips_are_validated() -> None:
    with ProcessorRunner(GOOD) as runner:
        example = runner.process(
            {"text": "Türkçe", "answer": {"nested": [1, None]}, "tools": [TOOL]}
        )
        assert example is not None
        assert example.tools[0].model_dump(exclude_none=True) == TOOL
        assert example.expected_output == {"nested": [1, None]}
        assert runner.runtime_version == "1.3.0"
        assert runner.source_hash == hashlib.sha256(GOOD.encode()).hexdigest()
    with ProcessorRunner("def process(row):\n    return None") as runner:
        assert runner.process({}) is None


@pytest.mark.parametrize(
    "statement",
    [
        'open("/etc/passwd").read()',
        'open("/tmp/monty-escape", "w")',
        "import os\n    os.environ",
        'import os\n    os.getenv("HOME")',
        "import socket",
        "import subprocess",
        "import requests",
        "host_callback()",
        '__import__("socket")',
    ],
)
def test_host_capabilities_are_denied_and_next_row_recovers(statement: str) -> None:
    code = "def process(row):\n    if row.get('attack'):\n        " + statement.replace(
        "\n    ", "\n        "
    )
    code += "\n    return {'conversation': [{'role': 'user', 'content': 'safe'}]}"
    with ProcessorRunner(code) as runner:
        with pytest.raises(ProcessorError):
            runner.process({"attack": True})
        assert runner.process({"attack": False}) is not None


@pytest.mark.parametrize(
    "statement",
    [
        "while True:\n            pass",
        "x = 'x' * 1000000000",
        "def recurse():\n            return recurse()\n        recurse()",
    ],
)
def test_resource_failures_are_bounded_and_recover(statement: str) -> None:
    code = 'def process(row):\n    if row.get("attack"):\n        ' + statement
    code += "\n    return {'conversation': [{'role': 'user', 'content': 'safe'}]}"
    with ProcessorRunner(code) as runner:
        start = perf_counter()
        with pytest.raises(ProcessorError) as failure:
            runner.process({"attack": True})
        assert failure.value.category == "resource_limit"
        assert perf_counter() - start < 3
        assert runner.process({}) is not None


def test_clock_random_sleep_prints_and_global_state_are_isolated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = """import random
import time
from datetime import datetime
state = []
def process(row):
    state.append(row["text"])
    time.sleep(999999)
    print("PRIVATE PRINT")
    return {"conversation": [{"role": "user", "content": "hello"}],
            "expected_output": [len(state), random.random(), time.time(), str(datetime.now())]}
"""
    with ProcessorRunner(code) as runner:
        first = runner.process({"text": "first"})
        second = runner.process({"text": "second"})
        assert first is not None and second is not None
        assert first.expected_output == second.expected_output
        assert isinstance(first.expected_output, list)
        assert first.expected_output[0] == 1
        assert first.expected_output[-1] == "2000-01-01 00:00:00"
    assert "PRIVATE PRINT" not in capsys.readouterr().out


def test_diagnostics_hide_user_payloads_and_include_locations() -> None:
    with ProcessorRunner('def process(row):\n    raise ValueError(row["secret"])') as runner:
        with pytest.raises(ProcessorError) as failure:
            runner.process({"secret": "PRIVATE"})
        assert failure.value.line == 2
        assert failure.value.column is not None
        assert "PRIVATE" not in str(failure.value)
    with ProcessorRunner("def process(:") as runner:
        with pytest.raises(ProcessorError) as failure:
            runner.process({})
        assert failure.value.category == "syntax"
        assert failure.value.line == 1


@pytest.mark.parametrize(
    "value",
    [
        True,
        [],
        7,
        {"conversation": []},
        {
            "conversation": [{"role": "user", "content": "x"}],
            "tools": None,
        },
    ],
)
def test_malformed_output_rejected_without_payloads(value: object) -> None:
    with ProcessorRunner(f"def process(row):\n    return {value!r}") as runner:
        with pytest.raises(ProcessorError) as failure:
            runner.process({})
        assert failure.value.category == "validation"


def test_tools_error_has_field_path() -> None:
    with ProcessorRunner(GOOD) as runner:
        with pytest.raises(ProcessorError) as failure:
            runner.process(
                {
                    "text": "x",
                    "tools": [
                        {"type": "function", "function": {"name": "lookup", "parameters": []}}
                    ],
                }
            )
        assert failure.value.field_path == "tools[0].function.parameters"


def test_json_depth_sizes_and_nonjson_values() -> None:
    with pytest.raises(ProcessorError):
        ProcessorRunner("#" * 65537)
    with ProcessorRunner(GOOD) as runner:
        invalid_rows: list[dict[str, object]] = [
            {"text": "x" * 1048576},
            {"text": float("nan")},
            {"text": {1, 2}},
        ]
        for row in invalid_rows:
            with pytest.raises(ProcessorError):
                runner.process(row)
        deep: object = None
        for _ in range(65):
            deep = [deep]
        with pytest.raises(ProcessorError):
            runner.process({"text": deep})
    with ProcessorRunner(
        "def process(row):\n    return {'extras': {'x': 'x' * 1048576}}"
    ) as runner:
        with pytest.raises(ProcessorError) as failure:
            runner.process({})
        assert failure.value.category == "resource_limit"


def test_binary_override_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONTY_BIN", "/does/not/exist")
    with ProcessorRunner(GOOD) as runner:
        assert runner.process({"text": "safe"}) is not None


def test_worker_death_is_replaced() -> None:
    from pydantic_monty import Monty

    from llm_evaluation_hub.imports.runtime import _bundled_binary

    with Monty(
        binary_path=_bundled_binary(), min_processes=1, max_processes=1, request_timeout=3
    ) as pool:
        with pool.checkout() as session:
            worker_pid = session.worker_pid
            assert worker_pid is not None
            os.kill(worker_pid, signal.SIGKILL)
        with pool.checkout() as session:
            assert session.feed_run("1 + 1") == 2
            assert session.worker_pid != worker_pid
    assert not Path(f"/proc/{worker_pid}").exists()


def test_json_budget_reports_compact_utf8_bytes() -> None:
    assert validate_json_budget({"text": "ğ"}, category="input") == 13
