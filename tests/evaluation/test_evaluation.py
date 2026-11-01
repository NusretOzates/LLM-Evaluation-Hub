"""Focused contracts for evaluation and saved-source retention."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from llm_evaluation_hub.api.app import create_app
from llm_evaluation_hub.core.datasets.catalog import DatasetRepository
from llm_evaluation_hub.core.datasets.catalog.storage import catalog_connection
from llm_evaluation_hub.core.datasets.records import ProcessedExample
from llm_evaluation_hub.core.datasets.sources import SourceDescriptor
from llm_evaluation_hub.evaluation.contracts import Definition, MethodOutcome, Metric
from llm_evaluation_hub.evaluation.methods.exact_match import equal_json
from llm_evaluation_hub.evaluation.prompts import render_prompt
from llm_evaluation_hub.evaluation.registry import METHODS, MethodDefinition, register
from llm_evaluation_hub.evaluation.scoring import score, validate_scores
from llm_evaluation_hub.evaluation.store import EvaluationStore
from llm_evaluation_hub.inference.store import InferenceStore, now


class Source:
    def read(self, *, limit=None):
        frame = pl.DataFrame({"i": list(range(10))})
        return frame if limit is None else frame.head(limit)

    def describe(self):
        return SourceDescriptor(source_type="test")


def fixture(root: Path):
    repo = DatasetRepository(root)
    dataset = repo.register(
        "cases",
        Source(),
        lambda row: ProcessedExample(
            conversation=[{"role": "user", "content": "question"}],
            expected_output=str(row["i"]),
            segments={"group": "a" if row["i"] < 5 else "b"},
        ),
        processor_id="test",
        segments=["group"],
    )
    stamp = now()
    with catalog_connection(root) as db:
        db.execute(
            "INSERT INTO inference_runs VALUES (?, 'completed', ?, ?, '{}', 10, NULL)",
            ("source", stamp, stamp),
        )
        db.execute(
            "INSERT INTO inference_run_datasets VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "source",
                dataset.id,
                dataset.name,
                dataset.parquet_path,
                10,
                '{"kind":"text","schema":null,"strict":true}',
                dataset.snapshot_format_version,
            ),
        )
        for i in range(8):
            result = {
                "dataset_id": dataset.id,
                "ordinal": i,
                "source_index": i,
                "status": "ok",
                "content": str(i) if i < 7 else "wrong",
                "parsed": None,
                "tool_calls": None,
            }
            db.execute(
                "INSERT INTO inference_results VALUES (?, ?, ?, ?)",
                ("source", dataset.id, i, json.dumps(result)),
            )
    return repo, dataset


def definition():
    return Definition(
        name="test",
        method_id="exact_match",
        scoring_source='def score(result):\n    return {"correctness": int(result["matches"])}',
        metrics=[Metric(name="correctness", minimum=0, maximum=1)],
    )


def test_scoring_and_prompt_contracts():
    assert score({"matches": True}, definition().scoring_source) == {"correctness": 1}
    for value in ({"x": True}, {"x": float("nan")}, {"": 1}, {"x": "1"}):
        with pytest.raises(ValueError):
            validate_scores(value)
    with pytest.raises(ValueError):
        validate_scores({"other": 1}, definition().metrics)
    with pytest.raises(ValueError):
        validate_scores({"correctness": 2}, definition().metrics)
    assert equal_json({"a": [1, True]}, {"a": [1.0, True]})
    assert not equal_json(True, 1)
    assert render_prompt(r"{{x}} \alpha", {"x": "{{y}}"}, {"x"}) == r"{{y}} \alpha"
    with pytest.raises(ValueError):
        render_prompt("{{missing}}", {}, {"x"})


def test_source_readers_and_dependency_guards(tmp_path):
    repo, dataset = fixture(tmp_path)
    assert repo.evaluation_rows(dataset.id)[0][2].expected_output == "0"
    assert repo.inference_rows(dataset.id)[0][2].expected_output is None
    store = EvaluationStore(tmp_path)
    run = store.create("source", [dataset.id], definition())
    with pytest.raises(ValueError, match="unfinished evaluation"):
        InferenceStore(tmp_path).delete_run("source")
    repo.trash(dataset.id)
    with pytest.raises(Exception, match="unfinished evaluation"):
        repo.purge(dataset.id)
    with catalog_connection(tmp_path) as db:
        db.execute("UPDATE evaluation_runs SET state='completed' WHERE id=?", (run["id"],))
    InferenceStore(tmp_path).delete_run("source")
    repo.purge(dataset.id)
    assert store.run(run["id"])["total"] == 10


def test_real_api_runner_and_coverage(tmp_path):
    _, dataset = fixture(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        response = client.post(
            "/evaluations",
            json={
                "source_inference_run_id": "source",
                "dataset_ids": [dataset.id],
                "definition": definition().model_dump(mode="json"),
            },
        )
        assert response.status_code == 200, response.text
        identifier = response.json()["id"]
        import time

        for _ in range(100):
            run = client.get(f"/evaluations/{identifier}").json()
            if run["state"] == "completed":
                break
            time.sleep(0.05)
        assert run["state"] == "completed"
        group = client.get(f"/evaluations/{identifier}/summary").json()["groups"][0]
        assert (group["scored"], group["selected"], group["source_ineligible"]) == (8, 10, 2)
        assert group["means"]["correctness"] == 0.875
        assert group["coverage"] == 0.8
        fields = client.post(
            "/evaluations/fields",
            json={"source_inference_run_id": "source", "dataset_ids": [dataset.id]},
        ).json()
        assert "segments.group" in fields
        detail = client.get(f"/evaluations/{identifier}/inputs/{dataset.id}/0").json()
        assert detail["processed_response"] == "0"


def test_custom_method_lifecycle():
    events = []

    class Config(BaseModel):
        pass

    class Session:
        async def evaluate(self, context):
            events.append("evaluate")
            return MethodOutcome(result={"value": 3})

    @asynccontextmanager
    async def open_session(config, services):
        events.append("open")
        try:
            yield Session()
        finally:
            events.append("close")

    method = MethodDefinition(
        id="test_custom",
        version=1,
        label="test",
        config_model=Config,
        result_schema=lambda config: {"type": "object"},
        open=open_session,
        default_scoring="",
    )
    register(method)

    async def run():
        async with METHODS["test_custom"].open({}, None) as session:
            assert (await session.evaluate(None)).result == {"value": 3}

    try:
        asyncio.run(run())
        assert events == ["open", "evaluate", "close"]
    finally:
        del METHODS["test_custom"]


def test_judge_wire_and_invalid_result(tmp_path):
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from llm_evaluation_hub.inference.contracts import ConnectionProfile

    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            content = (
                '{"correct":false,"reason":"no"}'
                if len(requests) == 1
                else '{"correct":"invalid","reason":"no"}'
            )
            payload = json.dumps(
                {
                    "id": "fake",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "fake",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _, dataset = fixture(tmp_path)
        profile = InferenceStore(tmp_path).save_profile(
            ConnectionProfile(
                name="fake", base_url=f"http://127.0.0.1:{server.server_port}/v1", model="fake"
            )
        )
        judge = Definition(
            name="judge",
            method_id="llm_judge",
            method_config={
                "profile_id": profile.id,
                "prompt": "Question {{conversation}} Candidate {{processed_response}} Reference {{expected_output}}",
                "rpm": 1000,
            },
            scoring_source='def score(result):\n    return {"correctness": int(result["correct"])}',
            metrics=[Metric(name="correctness", minimum=0, maximum=1)],
        )
        with TestClient(create_app(tmp_path)) as client:
            response = client.post(
                "/evaluations",
                json={
                    "source_inference_run_id": "source",
                    "dataset_ids": [dataset.id],
                    "definition": judge.model_dump(mode="json"),
                },
            )
            assert response.status_code == 200, response.text
            identifier = response.json()["id"]
            for _ in range(200):
                run = client.get(f"/evaluations/{identifier}").json()
                if run["state"] == "completed":
                    break
                time.sleep(0.05)
            assert run["state"] == "completed", run
            rows = client.get(f"/evaluations/{identifier}/results").json()["results"]
            assert rows[0]["scores"] == {"correctness": 0}
            assert rows[1]["status"] == "failed" and rows[1]["evidence"] is not None
            assert requests[0]["response_format"]["type"] == "json_schema"
            assert requests[0]["messages"][0]["content"].endswith("Reference 0")
            assert "tools" not in requests[0]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_custom_method_through_runner_and_backup(tmp_path):
    import time
    from scripts.catalog_backup import backup_catalog

    events = []

    class Config(BaseModel):
        pass

    class Session:
        async def evaluate(self, context):
            events.append("evaluate")
            return MethodOutcome(result={"value": 3})

    @asynccontextmanager
    async def open_session(config, services):
        events.append("open")
        try:
            yield Session()
        finally:
            events.append("close")

    register(
        MethodDefinition(
            id="test_registered",
            version=1,
            label="test",
            config_model=Config,
            result_schema=lambda config: {"type": "object"},
            open=open_session,
            default_scoring="",
        )
    )
    try:
        repo, dataset = fixture(tmp_path / "source")
        custom = Definition(
            name="custom",
            method_id="test_registered",
            scoring_source='def score(result):\n    return {"value": result["value"]}',
            metrics=[Metric(name="value")],
        )
        with TestClient(create_app(tmp_path / "source")) as client:
            created = client.post(
                "/evaluations",
                json={
                    "source_inference_run_id": "source",
                    "dataset_ids": [dataset.id],
                    "definition": custom.model_dump(mode="json"),
                },
            )
            assert created.status_code == 200, created.text
            identifier = created.json()["id"]
            for _ in range(100):
                run = client.get(f"/evaluations/{identifier}").json()
                if run["state"] == "completed":
                    break
                time.sleep(0.05)
            assert run["state"] == "completed"
            assert events == ["open"] + ["evaluate"] * 8 + ["close"]
            backup_catalog(tmp_path / "source", tmp_path / "backup")
            assert EvaluationStore(tmp_path / "backup").run(identifier)["completed"] == 10
            InferenceStore(tmp_path / "source").delete_run("source")
            repo.trash(dataset.id)
            repo.purge(dataset.id)
            detail = client.get(f"/evaluations/{identifier}/inputs/{dataset.id}/0")
            assert detail.status_code == 200 and detail.json()["available"] is False
            assert client.get(f"/evaluations/{identifier}/summary").json()["groups"][0][
                "means"
            ] == {"value": 3}
    finally:
        del METHODS["test_registered"]


def test_cancel_cleanup_and_endpoint_admission(tmp_path):
    import threading
    import time
    from llm_evaluation_hub.inference.contracts import ConnectionProfile

    opened = threading.Event()
    closed = threading.Event()

    class Config(BaseModel):
        pass

    class Session:
        async def evaluate(self, context):
            opened.set()
            await asyncio.sleep(30)
            return MethodOutcome(result={"value": 1})

    @asynccontextmanager
    async def open_session(config, services):
        try:
            yield Session()
        finally:
            closed.set()

    register(
        MethodDefinition(
            id="slow_test",
            version=1,
            label="slow",
            config_model=Config,
            result_schema=lambda config: {"type": "object"},
            open=open_session,
            default_scoring="",
        )
    )
    try:
        _, dataset = fixture(tmp_path)
        store = InferenceStore(tmp_path)
        profile = store.save_profile(
            ConnectionProfile(name="fake", base_url="http://127.0.0.1:9/v1", model="fake")
        )
        app = create_app(tmp_path)
        with TestClient(app) as client:
            lock = app.state.inference_runner.admission
            assert lock.acquire(blocking=False)
            try:
                blocked = client.post(
                    "/evaluations/test-method",
                    json={
                        "source_inference_run_id": "source",
                        "dataset_id": dataset.id,
                        "ordinal": 0,
                        "method_id": "llm_judge",
                        "method_config": {"profile_id": profile.id},
                    },
                )
                assert blocked.status_code == 409
            finally:
                lock.release()
            slow = Definition(
                name="slow",
                method_id="slow_test",
                scoring_source='def score(result):\n    return {"value": result["value"]}',
                metrics=[Metric(name="value")],
            )
            created = client.post(
                "/evaluations",
                json={
                    "source_inference_run_id": "source",
                    "dataset_ids": [dataset.id],
                    "definition": slow.model_dump(mode="json"),
                },
            )
            identifier = created.json()["id"]
            assert opened.wait(5)
            assert client.post(f"/evaluations/{identifier}/cancel").status_code == 200
            assert closed.wait(5)
            for _ in range(100):
                state = client.get(f"/evaluations/{identifier}").json()["state"]
                if state == "canceled":
                    break
                time.sleep(0.02)
            assert state == "canceled"
    finally:
        del METHODS["slow_test"]


def test_scope_overlap_and_missing_segment(tmp_path):
    import time

    repo, dataset = fixture(tmp_path)
    repo.create_tag("A")
    repo.create_tag("B", parent="A")
    repo.add_tags("cases", ["A", "A/B"])
    with TestClient(create_app(tmp_path)) as client:
        created = client.post(
            "/evaluations",
            json={
                "source_inference_run_id": "source",
                "dataset_ids": [dataset.id],
                "definition": definition().model_dump(mode="json"),
            },
        ).json()
        identifier = created["id"]
        for _ in range(100):
            if client.get(f"/evaluations/{identifier}").json()["state"] == "completed":
                break
            time.sleep(0.05)
        with catalog_connection(tmp_path) as db:
            db.execute(
                "UPDATE evaluation_inputs SET segments='{}' WHERE run_id=? AND ordinal=0",
                (identifier,),
            )
        scoped = client.get(
            f"/evaluations/{identifier}/summary", params=[("tag_paths", "A"), ("tag_paths", "A/B")]
        ).json()
        assert scoped["groups"][0]["selected"] == 10
        grouped = client.get(
            f"/evaluations/{identifier}/summary", params={"group_by": "tag"}
        ).json()["groups"]
        assert {g["name"]: g["selected"] for g in grouped} == {"A": 10, "A/B": 10}
        segments = client.get(
            f"/evaluations/{identifier}/summary",
            params={"group_by": "segment", "segment_key": "group"},
        ).json()["groups"]
        assert next(g for g in segments if g["name"] is None)["selected"] == 1
        rows = client.get(
            f"/evaluations/{identifier}/results", params=[("tag_paths", "A"), ("tag_paths", "A/B")]
        ).json()
        assert rows["total"] == 10


def test_interrupted_resume_skips_committed_outcomes(tmp_path):
    import time

    calls = []

    class Config(BaseModel):
        pass

    class Session:
        async def evaluate(self, context):
            calls.append(context.ordinal)
            return MethodOutcome(result={"value": 1})

    @asynccontextmanager
    async def open_session(config, services):
        yield Session()

    register(
        MethodDefinition(
            id="resume_test",
            version=1,
            label="resume",
            config_model=Config,
            result_schema=lambda config: {"type": "object"},
            open=open_session,
            default_scoring="",
        )
    )
    try:
        _, dataset = fixture(tmp_path)
        saved = Definition(
            name="resume",
            method_id="resume_test",
            scoring_source='def score(result):\n    return {"value": result["value"]}',
            metrics=[Metric(name="value")],
        )
        with TestClient(create_app(tmp_path)) as client:
            identifier = client.post(
                "/evaluations",
                json={
                    "source_inference_run_id": "source",
                    "dataset_ids": [dataset.id],
                    "definition": saved.model_dump(mode="json"),
                },
            ).json()["id"]
            for _ in range(100):
                if client.get(f"/evaluations/{identifier}").json()["state"] == "completed":
                    break
                time.sleep(0.05)
            with catalog_connection(tmp_path) as db:
                db.execute(
                    "DELETE FROM evaluation_results WHERE run_id=? AND ordinal=0", (identifier,)
                )
                db.execute(
                    "UPDATE evaluation_runs SET state='interrupted' WHERE id=?", (identifier,)
                )
            assert client.post(f"/evaluations/{identifier}/resume").status_code == 200
            for _ in range(100):
                if client.get(f"/evaluations/{identifier}").json()["state"] == "completed":
                    break
                time.sleep(0.05)
            assert calls.count(0) == 2
            assert all(calls.count(i) == 1 for i in range(1, 8))
    finally:
        del METHODS["resume_test"]
