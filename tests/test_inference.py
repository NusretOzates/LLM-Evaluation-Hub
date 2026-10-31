"""Inference request compilation and durable metadata tests."""

import json
from pathlib import Path

import polars as pl
import pytest
from tests.datasets.catalog.memory import MemorySource

from llm_evaluation_hub.core.datasets import DatasetRepository, ProcessedExample
from llm_evaluation_hub.inference.compiler import compile_request
from llm_evaluation_hub.inference.contracts import (
    ConnectionProfile,
    Generation,
    OutputFormat,
    RunSpec,
)
from llm_evaluation_hub.inference.store import InferenceStore


def test_compilation_protects_data_and_controls() -> None:
    profile = ConnectionProfile(
        name="local",
        base_url="http://localhost:8000/v1",
        model="m",
        reasoning_mode="effort",
        effort_levels=["high"],
        effort_path="reason.effort",
        thinking_path="reason.enabled",
    )
    example = ProcessedExample.model_validate(
        {
            "conversation": [
                {"role": "user", "content": "hello"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c",
                            "type": "function",
                            "function": {"name": "f", "arguments": {"x": 1}},
                        }
                    ],
                },
            ],
            "expected_output": "secret",
            "extras": {"gold": "secret"},
        }
    )
    body = compile_request(
        profile,
        Generation(effort="high", advanced={"reason": {"enabled": False}}),
        OutputFormat(),
        example,
    )
    assert body["reason"] == {"effort": "high", "enabled": False}
    assert body["messages"][1]["tool_calls"][0]["function"]["arguments"] == '{"x":1}'
    assert "secret" not in json.dumps(body)
    thinking_profile = profile.model_copy(update={"reasoning_mode": "thinking"})
    thinking_body = compile_request(
        thinking_profile, Generation(thinking=False), OutputFormat(), example
    )
    assert thinking_body["reason"] == {"enabled": False}
    for settings in (Generation(), Generation(effort="high")):
        assert "enabled" not in compile_request(profile, settings, OutputFormat(), example).get(
            "reason", {}
        )
    with pytest.raises(ValueError, match="thinking control"):
        compile_request(profile, Generation(thinking=True), OutputFormat(), example)
    with pytest.raises(ValueError, match="effort"):
        compile_request(thinking_profile, Generation(effort="high"), OutputFormat(), example)
    with pytest.raises(ValueError, match="conflict"):
        compile_request(
            profile, Generation(advanced={"model": "override"}), OutputFormat(), example
        )
    with pytest.raises(ValueError, match="thinking"):
        compile_request(
            profile,
            Generation(),
            OutputFormat(),
            ProcessedExample.model_validate(
                {"conversation": [{"role": "assistant", "thinking": "private"}]}
            ),
        )


def test_run_freezes_metadata_and_blocks_purge(tmp_path: Path) -> None:
    repo = DatasetRepository(tmp_path)
    record = repo.register(
        "data",
        MemorySource(pl.DataFrame({"x": [1, 2]})),
        lambda row: ProcessedExample.model_validate(
            {"conversation": [{"role": "user", "content": str(row["x"])}]}
        ),
        processor_id="p",
    )
    store = InferenceStore(tmp_path)
    profile = store.save_profile(
        ConnectionProfile(name="local", base_url="http://localhost:1/v1", model="m")
    )
    run = store.create(RunSpec(dataset_ids=[record.id], profile_id=profile.id))
    assert run.total == 2
    repo.trash(record.id)
    with pytest.raises(ValueError, match="unfinished inference"):
        repo.purge(record.id)
    assert store.catalog.inference_rows(record.id)[0][1] == 0


def test_runner_sends_real_local_http_and_persists(tmp_path: Path) -> None:
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from llm_evaluation_hub.inference.runner import Runner

    seen = []
    authorizations = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            authorizations.append(self.headers.get("Authorization"))
            if len(seen) == 1:
                self.send_response(429)
                self.send_header("Retry-After", "0")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            data = json.dumps(
                {
                    "id": "x",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "m",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "ok"},
                        }
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    repo = DatasetRepository(tmp_path)
    record = repo.register(
        "data",
        MemorySource(pl.DataFrame({"x": [1]})),
        lambda row: ProcessedExample.model_validate(
            {"conversation": [{"role": "user", "content": str(row["x"])}]}
        ),
        processor_id="p",
    )
    store = InferenceStore(tmp_path)
    profile = store.save_profile(
        ConnectionProfile(
            name="local", base_url=f"http://127.0.0.1:{server.server_port}/v1", model="m"
        )
    )
    runner = Runner(store)
    runner.start()
    run = store.create(
        RunSpec(
            dataset_ids=[record.id],
            profile_id=profile.id,
            generation=Generation(advanced={"custom": {"flag": True}}),
        )
    )
    try:
        for _ in range(100):
            if store.run(run.id).state == "completed":
                break
            time.sleep(0.05)
        assert store.run(run.id).state == "completed"
        assert seen[0]["custom"] == {"flag": True}
        assert authorizations == [None, None]
        result = store.results(run.id, 0, 10).results[0]
        assert result.content == "ok"
        assert result.attempts == 2
        assert result.error is None
        runner.stop()
        from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection

        with catalog_connection(tmp_path) as db:
            db.execute("UPDATE inference_runs SET state = 'running' WHERE id = ?", (run.id,))
        runner = Runner(store)
        runner.start()
        assert store.run(run.id).state == "interrupted"
        runner.resume(run.id)
        for _ in range(100):
            if store.run(run.id).state == "completed":
                break
            time.sleep(0.05)
        assert store.run(run.id).state == "completed"
        assert len(seen) == 2
        from scripts.catalog_backup import backup_catalog

        store.save_output(record.id, OutputFormat(kind="json_object"))
        assert store.run(run.id).datasets[0].output.kind == "text"
        backup = tmp_path.parent / f"{tmp_path.name}-backup"
        backup_catalog(tmp_path, backup)
        restored = InferenceStore(backup)
        assert restored.profile(profile.id).model == "m"
        assert restored.output(record.id).kind == "json_object"
        assert restored.results(run.id, 0, 10).results[0].content == "ok"
        repo.trash(record.id)
        repo.purge(record.id)
        assert store.run(run.id).datasets[0].input_available is False
        assert store.results(run.id, 0, 10).results[0].content == "ok"
    finally:
        runner.stop()
        server.shutdown()
        server.server_close()


def test_schema_validation_and_reasoning_paths() -> None:
    from llm_evaluation_hub.inference.compiler import validate_format

    valid = OutputFormat.model_validate(
        {
            "kind": "json_schema",
            "schema": {
                "type": "object",
                "properties": {
                    "child": {
                        "type": ["object", "null"],
                        "properties": {"x": {"type": "string"}},
                        "required": ["x"],
                        "additionalProperties": False,
                    }
                },
                "required": ["child"],
                "additionalProperties": False,
            },
        }
    )
    validate_format(valid)
    invalid = valid.model_copy(deep=True)
    assert invalid.schema_ is not None
    properties = invalid.schema_["properties"]
    assert isinstance(properties, dict)
    child = properties["child"]
    assert isinstance(child, dict)
    child.pop("additionalProperties")
    with pytest.raises(ValueError, match="additionalProperties"):
        validate_format(invalid)
    remote = OutputFormat.model_validate(
        {
            "kind": "json_schema",
            "strict": False,
            "schema": {
                "type": "object",
                "definitions": {"x": {"$ref": "https://example.invalid/schema"}},
            },
        }
    )
    with pytest.raises(ValueError, match="remote"):
        validate_format(remote)
    with pytest.raises(ValueError, match="protected"):
        ConnectionProfile(
            name="x",
            base_url="http://localhost/v1",
            model="x",
            reasoning_mode="thinking",
            thinking_path="messages.foo",
        )
    profile = ConnectionProfile(
        name="x",
        base_url="http://localhost/v1",
        model="x",
        reasoning_mode="effort",
        thinking_path="messages.foo",
    )
    example = ProcessedExample.model_validate({"conversation": [{"role": "user", "content": "x"}]})
    compile_request(profile, Generation(), OutputFormat(), example)
    with pytest.raises(ValueError):
        Generation(temperature=float("nan"))


def test_api_profile_output_and_input_errors(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from llm_evaluation_hub.api import create_app

    repo = DatasetRepository(tmp_path)
    record = repo.register(
        "data",
        MemorySource(pl.DataFrame({"x": [1]})),
        lambda row: ProcessedExample.model_validate(
            {"conversation": [{"role": "user", "content": str(row["x"])}]}
        ),
        processor_id="p",
    )
    with TestClient(create_app(tmp_path)) as client:
        created = client.post(
            "/connections",
            json={"name": "local", "base_url": "http://localhost:1/v1", "model": "m"},
        )
        assert created.status_code == 200
        profile_id = created.json()["id"]
        assert client.get(f"/connections/{profile_id}").status_code == 200
        assert client.get(f"/dataset-ids/{record.id}/output-format").json()["kind"] == "text"
        invalid = client.post("/inference/runs", json={"profile_id": profile_id})
        assert invalid.status_code == 422
        assert client.get("/inference/runs/missing").status_code == 404
        preview = client.post(
            "/inference/preview", json={"profile_id": profile_id, "dataset_id": record.id}
        )
        assert preview.status_code == 200
        assert preview.json()["messages"][0]["content"] == "1"


def test_response_failures_are_retained() -> None:
    from llm_evaluation_hub.inference.contracts import RowResult
    from llm_evaluation_hub.inference.transport import interpret, retry_delay

    result = RowResult(dataset_id="d", ordinal=0, source_index=0, status="error")
    interpret({"choices": []}, result, OutputFormat())
    assert result.status == "invalid_response"
    assert result.raw_response == {"choices": []}
    interpret(
        {"choices": [{"message": {"content": '{"value": NaN}'}}]},
        result,
        OutputFormat(kind="json_object"),
    )
    assert result.status == "malformed_json"
    interpret(
        {"choices": [{"message": {"content": '{"value": 1e309}'}}]},
        result,
        OutputFormat(kind="json_object"),
    )
    assert result.status == "malformed_json"
    assert retry_delay("120", 0) == 120


def test_cancel_stops_active_request_and_releases_dataset(tmp_path: Path) -> None:
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from llm_evaluation_hub.inference.runner import Runner

    received = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            received.set()
            release.wait(timeout=5)
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    repo = DatasetRepository(tmp_path)
    record = repo.register(
        "data",
        MemorySource(pl.DataFrame({"x": [1]})),
        lambda row: ProcessedExample.model_validate(
            {"conversation": [{"role": "user", "content": str(row["x"])}]}
        ),
        processor_id="p",
    )
    store = InferenceStore(tmp_path)
    profile = store.save_profile(
        ConnectionProfile(
            name="local", base_url=f"http://127.0.0.1:{server.server_port}/v1", model="m"
        )
    )
    runner = Runner(store)
    runner.start()
    try:
        run = store.create(RunSpec(dataset_ids=[record.id], profile_id=profile.id))
        assert received.wait(timeout=5)
        repo.trash(record.id)
        with pytest.raises(ValueError, match="unfinished inference"):
            repo.purge(record.id)
        runner.cancel(run.id)
        for _ in range(100):
            if store.run(run.id).state == "canceled":
                break
            time.sleep(0.05)
        assert store.run(run.id).state == "canceled"
        assert store.results(run.id, 0, 10).results == []
        repo.purge(record.id)
        assert not store.run(run.id).datasets[0].input_available
    finally:
        runner.stop()
        release.set()
        server.shutdown()
        server.server_close()


def test_shared_limits_and_manual_recovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from llm_evaluation_hub.inference.runner import RateLimiter, Runner

    lock = threading.Lock()
    active = 0
    peak = 0
    seen = 0
    permits = 0
    original_acquire = RateLimiter.acquire

    async def count_permit(self: RateLimiter) -> None:
        nonlocal permits
        permits += 1
        await original_acquire(self)

    monkeypatch.setattr(RateLimiter, "acquire", count_permit)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            nonlocal active, peak, seen
            self.rfile.read(int(self.headers["Content-Length"]))
            with lock:
                active += 1
                peak = max(peak, active)
                seen += 1
                attempt = seen
            time.sleep(0.05)
            if attempt == 1:
                data = b""
                self.send_response(429)
                self.send_header("Retry-After", "0")
            else:
                data = json.dumps(
                    {
                        "id": "x",
                        "object": "chat.completion",
                        "created": 0,
                        "model": "m",
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "ok"},
                            }
                        ],
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            with lock:
                active -= 1

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    repo = DatasetRepository(tmp_path)

    def processor(row: dict) -> ProcessedExample:
        return ProcessedExample.model_validate(
            {"conversation": [{"role": "user", "content": str(row["x"])}]}
        )

    records = [
        repo.register(name, MemorySource(pl.DataFrame({"x": [1, 2]})), processor, processor_id="p")
        for name in ("one", "two")
    ]
    store = InferenceStore(tmp_path)
    profile = store.save_profile(
        ConnectionProfile(
            name="local", base_url=f"http://127.0.0.1:{server.server_port}/v1", model="m"
        )
    )
    run = store.create(
        RunSpec(dataset_ids=[r.id for r in records], profile_id=profile.id, concurrency=2)
    )
    runner = Runner(store)
    runner.start()
    try:
        assert store.run(run.id).state == "interrupted"
        assert seen == 0
        runner.resume(run.id)
        for _ in range(100):
            if store.run(run.id).state == "completed":
                break
            time.sleep(0.05)
        assert store.run(run.id).state == "completed"
        assert 1 < peak <= 2
        assert seen == permits == 5
        assert sum(result.attempts for result in store.results(run.id, 0, 10).results) == 5
        from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection

        with catalog_connection(tmp_path) as db:
            db.execute(
                "UPDATE inference_results SET payload = json_set(payload, '$.status', 'error') "
                "WHERE run_id = ? AND dataset_id = ? AND ordinal = 1",
                (run.id, records[0].id),
            )
        page = store.results(run.id, 0, 1, dataset_id=records[0].id)
        assert page.total == 2 and len(page.results) == 1
        errors = store.results(run.id, 0, 1, dataset_id=records[0].id, errors_only=True)
        assert errors.total == 1 and errors.results[0].ordinal == 1
    finally:
        runner.stop()
        server.shutdown()
        server.server_close()


def test_rate_limiter_counts_attempts_in_rolling_window(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    from types import SimpleNamespace

    import llm_evaluation_hub.inference.runner as runner_module

    current = 100.0
    waits = []

    async def advance(seconds: float) -> None:
        nonlocal current
        waits.append(seconds)
        current += seconds

    monkeypatch.setattr(runner_module, "time", SimpleNamespace(monotonic=lambda: current))
    monkeypatch.setattr(runner_module.asyncio, "sleep", advance)

    async def exercise() -> None:
        limiter = runner_module.RateLimiter(2)
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()

    asyncio.run(exercise())
    assert waits == [60.0]


def test_authentication_failure_stops_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from llm_evaluation_hub.inference.runner import Runner

    requests = []
    monkeypatch.setenv("TEST_INFERENCE_KEY", "example-test-key")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            requests.append(self.headers.get("Authorization"))
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    repo = DatasetRepository(tmp_path)
    record = repo.register(
        "data",
        MemorySource(pl.DataFrame({"x": [1, 2, 3]})),
        lambda row: ProcessedExample.model_validate(
            {"conversation": [{"role": "user", "content": str(row["x"])}]}
        ),
        processor_id="p",
    )
    store = InferenceStore(tmp_path)
    profile = store.save_profile(
        ConnectionProfile(
            name="local",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            model="m",
            api_key_env="TEST_INFERENCE_KEY",
        )
    )
    runner = Runner(store)
    runner.start()
    try:
        run = store.create(RunSpec(dataset_ids=[record.id], profile_id=profile.id, concurrency=1))
        for _ in range(100):
            if store.run(run.id).state == "interrupted":
                break
            time.sleep(0.05)
        view = store.run(run.id)
        assert view.state == "interrupted"
        assert view.error == "endpoint authentication failed"
        assert requests == ["Bearer example-test-key"]
        assert "example-test-key" not in view.model_dump_json()
        assert "example-test-key" not in profile.model_dump_json()
        assert view.completed == 0
    finally:
        runner.stop()
        server.shutdown()
        server.server_close()


def test_compiler_defaults_tokens_and_unsupported_media() -> None:
    profile = ConnectionProfile(
        name="x", base_url="http://localhost/v1", model="m", max_tokens_field="max_tokens"
    )
    text = ProcessedExample.model_validate(
        {"conversation": [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]}
    )
    body = compile_request(
        profile, Generation(max_tokens=10), OutputFormat(kind="json_object"), text
    )
    assert body == {
        "model": "m",
        "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}],
        "stream": False,
        "n": 1,
        "max_tokens": 10,
        "response_format": {"type": "json_object"},
    }
    media = ProcessedExample.model_validate(
        {
            "conversation": [
                {
                    "role": "user",
                    "content": [{"type": "image", "url": "https://example.invalid/image"}],
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="media"):
        compile_request(profile, Generation(), OutputFormat(), media)
    with pytest.raises(ValueError, match="conflict"):
        compile_request(profile, Generation(advanced={"response_format": {}}), OutputFormat(), text)
