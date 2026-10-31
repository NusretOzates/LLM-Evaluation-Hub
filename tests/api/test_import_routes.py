"""HTTP source, preview, attestation and real durable-import integration tests."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_evaluation_hub.api import create_app
from llm_evaluation_hub.core.datasets.processing import process_rows
from llm_evaluation_hub.core.datasets.records import JsonValue, ProcessedExample
from llm_evaluation_hub.imports.contracts import SampleRequest, SourceSpec
from llm_evaluation_hub.imports.jobs import ImportSupervisor
from llm_evaluation_hub.imports.previews import PreviewService
from llm_evaluation_hub.imports.runtime import RUNTIME_VERSION, ProcessorError
from llm_evaluation_hub.imports.worker import validated_spec

CODE = """def process(row):
    return {"conversation": [{"role": "user", "content": row["text"]}],
            "tools": row["tools"], "segments": {"language": "tr"}}
"""


@pytest.mark.parametrize("kind", ["text", "json_object", "json_schema"])
def test_import_output_format_is_published_with_dataset(tmp_path: Path, kind: str) -> None:
    app = create_app(tmp_path)
    supervisor: ImportSupervisor = app.state.import_supervisor
    supervisor.store.put_preview(
        "preview",
        {
            "source": {"repo_id": "org/data"},
            "row_limit": 1,
            "resolved_sha": "b" * 40,
            "source_code": CODE,
            "source_hash": sha256(CODE.encode()).hexdigest(),
            "segment_keys": [],
            "processor_contract_version": "2",
            "runtime_policy_version": "1",
            "runtime_version": RUNTIME_VERSION,
        },
        datetime.now(UTC) + timedelta(hours=1),
    )
    schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    output = {"kind": kind, "schema": schema if kind == "json_schema" else None, "strict": True}
    body = {
        "preview_id": "preview",
        "name": "output test",
        "idempotency_key": "once",
        "output_format": output,
    }
    # No runner is started: this checks admission and publication without executing a processor.
    client = TestClient(app)
    submitted = client.post("/dataset-imports", json=body)
    assert submitted.status_code == 202, submitted.text
    assert submitted.json()["spec"]["output_format"] == output
    assert client.post("/dataset-imports", json=body).json()["id"] == submitted.json()["id"]
    job = supervisor.store.get_job(submitted.json()["id"])
    spec = validated_spec(job["spec"])
    supervisor.store.update_job(str(job["id"]), state="running", phase="publishing")

    def processor(row: dict[str, object]) -> ProcessedExample:
        return ProcessedExample(conversation=[{"role": "user", "content": str(row["text"])}])

    result = process_rows([{"text": "A question"}], processor, [])
    with supervisor.store.decision_lock():
        supervisor._publish(job, spec, result)
    record = supervisor.repository.get("output test")
    assert client.get(f"/dataset-ids/{record.id}/output-format").json() == output
    assert client.get(f"/dataset-imports/{job['id']}").json()["state"] == "succeeded"
    invalid = {**output, "kind": "json_schema", "schema": {**schema, "required": []}}
    rejected = client.post(
        "/dataset-imports", json={**body, "idempotency_key": "invalid", "output_format": invalid}
    )
    assert rejected.status_code == 422
    assert len(supervisor.store.list_jobs()) == 1


def tool(name: str) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "parameters": {
                "type": "object",
                "properties": {"nested": {"type": "array", "items": {"type": "string"}}},
            },
        },
    }


class HttpSource:
    def resolve(self, source: SourceSpec) -> str:
        return "b" * 40

    def rows(
        self, source: SourceSpec, resolved_sha: str, limit: int
    ) -> Iterator[dict[str, object]]:
        assert resolved_sha == "b" * 40
        for index, tools in enumerate([[tool("lookup_order")], [tool("search_catalog")], []]):
            if index >= limit:
                break
            yield {"text": f"Türkçe {index}", "tools": tools}


@pytest.fixture
def application(tmp_path: Path) -> FastAPI:
    return create_app(tmp_path / "catalog", source_adapter=HttpSource())


@pytest.fixture
def import_client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(application) as client:
        yield client


def attested(client: TestClient) -> str:
    sampled = client.post(
        "/dataset-source-samples", json={"source": {"repo_id": "org/data"}, "row_limit": 3}
    )
    assert sampled.status_code == 200, sampled.text
    response = client.post(
        "/dataset-previews",
        json={"sample_id": sampled.json()["id"], "source_code": CODE},
    )
    assert response.status_code == 200, response.text
    assert response.json()["valid"]
    assert [row["example"]["tools"] for row in response.json()["rows"]] == [
        [tool("lookup_order")],
        [tool("search_catalog")],
        [],
    ]
    return response.json()["id"]


def test_real_http_monty_import_tools_provenance_and_replay(import_client: TestClient) -> None:
    client = import_client
    assert client.get("/dataset-sources").json()["limits"]["max_rows"] == 10000
    assert client.post("/tags", json={"evaluation": {}}).status_code == 201
    preview_id = attested(client)
    assert client.get("/datasets").json() == []
    body = {
        "preview_id": preview_id,
        "name": "row tools",
        "tags": ["evaluation"],
        "idempotency_key": "same",
    }
    submitted = client.post("/dataset-imports", json=body)
    assert submitted.status_code == 202, submitted.text
    job = submitted.json()
    assert "candidate_dataset_id" not in job and "idempotency_key" not in job
    deadline = monotonic() + 15
    while job["state"] not in {"succeeded", "failed", "interrupted"} and monotonic() < deadline:
        sleep(0.05)
        job = client.get(f"/dataset-imports/{job['id']}").json()
    assert job["state"] == "succeeded", job
    assert client.post("/dataset-imports", json=body).json()["id"] == job["id"]
    conflict = client.post("/dataset-imports", json={**body, "idempotency_key": "another"})
    assert conflict.status_code == 409
    key_conflict = client.post("/dataset-imports", json={**body, "name": "changed"})
    assert key_conflict.status_code == 409
    assert len(client.get("/dataset-imports").json()["jobs"]) == 1
    examples = client.get(f"/dataset-ids/{job['dataset_id']}/examples").json()["examples"]
    assert [row["tools"] for row in examples] == [
        [tool("lookup_order")],
        [tool("search_catalog")],
        [],
    ]
    assert [row["segments"] for row in examples] == [{"language": "tr"}] * 3
    metadata = client.get(f"/dataset-ids/{job['dataset_id']}").json()
    assert metadata["tags"] == ["evaluation"]
    provenance = client.get(f"/dataset-ids/{job['dataset_id']}/processor").json()["provenance"]
    assert provenance["source_code"] == CODE and provenance["resolved_sha"] == "b" * 40
    assert client.post(f"/dataset-imports/{job['id']}/cancel").json()["state"] == "succeeded"


@pytest.mark.parametrize("endpoint", ["/dataset-previews", "/dataset-imports"])
def test_unknown_and_expired_ids_have_distinct_statuses(
    import_client: TestClient, application: FastAPI, endpoint: str
) -> None:
    service = application.state.preview_service
    supervisor = application.state.import_supervisor
    assert isinstance(service, PreviewService) and isinstance(supervisor, ImportSupervisor)
    if endpoint == "/dataset-previews":
        body = {"sample_id": "missing", "source_code": CODE}
        assert import_client.post(endpoint, json=body).status_code == 404
        sample = service.sample(SampleRequest(source=SourceSpec(repo_id="org/data")))
        sample.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        body["sample_id"] = sample.id
    else:
        body = {"preview_id": "missing", "name": "new", "idempotency_key": "x"}
        assert import_client.post(endpoint, json=body).status_code == 404
        identifier = attested(import_client)
        attestation = supervisor.store.get_preview(identifier)
        assert attestation is not None
        spec = attestation["spec"]
        assert isinstance(spec, dict)
        supervisor.store.put_preview("expired", spec, datetime.now(UTC) - timedelta(seconds=1))
        body["preview_id"] = "expired"
    assert import_client.post(endpoint, json=body).status_code == 410


def test_current_jobs_remain_readable(import_client: TestClient, application: FastAPI) -> None:
    identifier = attested(import_client)
    supervisor = application.state.import_supervisor
    assert isinstance(supervisor, ImportSupervisor)
    preview = supervisor.store.get_preview(identifier)
    assert preview is not None
    spec = preview["spec"]
    assert isinstance(spec, dict)
    spec = {**spec, "tags": []}
    current = supervisor.store.create_job("current", spec, "current")
    supervisor.store.update_job(str(current["id"]), state="failed", phase="failed")

    response = import_client.get("/dataset-imports")
    assert response.status_code == 200, response.text
    jobs = {job["id"]: job for job in response.json()["jobs"]}
    detail = import_client.get(f"/dataset-imports/{current['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["spec"] == spec
    assert jobs[current["id"]]["spec"] == spec


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_hash", "tampered"),
        ("runtime_version", "old"),
        ("processor_contract_version", "1"),
        ("runtime_policy_version", "0"),
        ("processor_contract_version", "99"),
        ("runtime_policy_version", "99"),
    ],
)
def test_incompatible_attestation_requires_new_preview(
    import_client: TestClient, application: FastAPI, field: str, value: str
) -> None:
    identifier = attested(import_client)
    supervisor = application.state.import_supervisor
    assert isinstance(supervisor, ImportSupervisor)
    stored = supervisor.store.get_preview(identifier)
    assert stored is not None
    spec = stored["spec"]
    assert isinstance(spec, dict)
    spec[field] = value
    supervisor.store.put_preview("bad", spec, datetime.now(UTC) + timedelta(hours=1))
    response = import_client.post(
        "/dataset-imports", json={"preview_id": "bad", "name": "bad", "idempotency_key": "bad"}
    )
    assert response.status_code == 422
    assert import_client.get("/dataset-imports").json() == {"jobs": []}


@pytest.mark.parametrize(
    "category,code", [("busy", 429), ("unavailable", 503), ("timeout", 422), ("interrupted", 503)]
)
def test_operation_status_mapping(
    import_client: TestClient, monkeypatch: pytest.MonkeyPatch, category: str, code: int
) -> None:
    def failing(self: PreviewService, request: object) -> None:
        raise ProcessorError(category, "Safe operation failure.")

    monkeypatch.setattr(PreviewService, "sample", failing)
    response = import_client.post(
        "/dataset-source-samples", json={"source": {"repo_id": "org/data"}}
    )
    assert response.status_code == code
    assert response.json()["detail"]["category"] == category


def test_request_and_unexpected_errors_do_not_leak_secrets(
    import_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "private-token-and-source-code"
    response = import_client.post(
        "/dataset-previews", json={"sample_id": "x", "source_code": {"secret": secret}}
    )
    assert response.status_code == 422 and secret not in response.text
    assert '"input"' not in response.text and '"ctx"' not in response.text
    response = import_client.post(
        "/dataset-source-samples", json={"source": {"repo_id": f"https://host/{secret}"}}
    )
    assert response.status_code == 422 and secret not in response.text

    def failing(self: PreviewService, request: object) -> None:
        raise RuntimeError(secret + " /home/private")

    monkeypatch.setattr(PreviewService, "sample", failing)
    response = import_client.post(
        "/dataset-source-samples", json={"source": {"repo_id": "org/data"}}
    )
    assert (
        response.status_code == 503 and secret not in response.text and "/home" not in response.text
    )
    # Default validation for the established catalog API retains the input field.
    invalid_page = import_client.get("/dataset-ids/missing/examples?limit=0")
    assert invalid_page.status_code == 422 and "input" in invalid_page.json()["detail"][0]


def test_unknown_jobs_and_unavailable_services(
    import_client: TestClient, application: FastAPI
) -> None:
    assert import_client.get("/dataset-imports/missing").status_code == 404
    assert import_client.post("/dataset-imports/missing/cancel").status_code == 404
    application.state.preview_service = None
    assert (
        import_client.post(
            "/dataset-source-samples", json={"source": {"repo_id": "org/data"}}
        ).status_code
        == 503
    )


def test_expired_preview_replays_only_an_accepted_immutable_submission(
    import_client: TestClient, application: FastAPI
) -> None:
    preview_id = attested(import_client)
    body = {"preview_id": preview_id, "name": "expiry replay", "idempotency_key": "expiry-key"}
    accepted = import_client.post("/dataset-imports", json=body)
    assert accepted.status_code == 202, accepted.text
    supervisor = application.state.import_supervisor
    assert isinstance(supervisor, ImportSupervisor)
    stored = supervisor.store.get_preview(preview_id)
    assert stored is not None and isinstance(stored["spec"], dict)
    supervisor.store.put_preview(
        "expired-replay", stored["spec"], datetime.now(UTC) - timedelta(seconds=1)
    )
    replay_body = {**body, "preview_id": "expired-replay"}
    replay = import_client.post("/dataset-imports", json=replay_body)
    assert replay.status_code == 202, replay.text
    assert replay.json()["id"] == accepted.json()["id"]
    changed = import_client.post("/dataset-imports", json={**replay_body, "name": "changed"})
    assert changed.status_code == 409
    fresh = import_client.post(
        "/dataset-imports", json={**replay_body, "idempotency_key": "new-expired-key"}
    )
    assert fresh.status_code == 410
    assert len(import_client.get("/dataset-imports").json()["jobs"]) == 1
