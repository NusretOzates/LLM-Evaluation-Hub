"""Tag forest routes."""

from fastapi.testclient import TestClient

_REVIEW = {
    "Trendyol Cases": {
        "children": {
            "Summarization": {"children": {"Review Summarization": {}}},
        }
    }
}

_REVIEW_TREE = {
    "Trendyol Cases": {
        "path": "Trendyol Cases",
        "children": {
            "Summarization": {
                "path": "Trendyol Cases/Summarization",
                "children": {
                    "Review Summarization": {
                        "path": "Trendyol Cases/Summarization/Review Summarization",
                        "children": {},
                    }
                },
            }
        },
    }
}


def test_empty_catalog_returns_an_empty_tag_forest(client: TestClient) -> None:
    response = client.get("/tags")

    assert response.status_code == 200
    assert response.json() == {}


def test_post_ensures_a_forest_and_get_returns_it(client: TestClient) -> None:
    created = client.post("/tags", json=_REVIEW)
    repeated = client.post("/tags", json=_REVIEW)
    sibling = client.post(
        "/tags",
        json={
            "Trendyol Cases": {
                "children": {
                    "Summarization": {"children": {"Chat Summarization": {}}},
                }
            }
        },
    )
    forest = client.get("/tags")

    assert created.status_code == 201
    assert created.json() == _REVIEW_TREE
    assert repeated.status_code == 200
    assert repeated.json() == _REVIEW_TREE
    assert sibling.status_code == 201
    assert forest.json() == {
        "Trendyol Cases": {
            "path": "Trendyol Cases",
            "children": {
                "Summarization": {
                    "path": "Trendyol Cases/Summarization",
                    "children": {
                        "Chat Summarization": {
                            "path": "Trendyol Cases/Summarization/Chat Summarization",
                            "children": {},
                        },
                        "Review Summarization": {
                            "path": "Trendyol Cases/Summarization/Review Summarization",
                            "children": {},
                        },
                    },
                }
            },
        }
    }


def test_post_strips_names_and_rejects_a_path_that_disagrees(client: TestClient) -> None:
    created = client.post(
        "/tags",
        json={"  Trendyol Cases  ": {"children": {"Summarization": {}}}},
    )
    mismatched = client.post(
        "/tags",
        json={"Trendyol Cases": {"path": "Other", "children": {}}},
    )

    assert created.status_code == 201
    assert created.json()["Trendyol Cases"]["children"]["Summarization"]["path"] == (
        "Trendyol Cases/Summarization"
    )
    assert mismatched.status_code == 422
    assert "Other" not in client.get("/tags").json()


def test_empty_tag_forest_inserts_nothing(client: TestClient) -> None:
    response = client.post("/tags", json={})

    assert response.status_code == 422
    assert client.get("/tags").json() == {}


def test_illegal_tag_name_inserts_nothing(client: TestClient) -> None:
    client.post("/tags", json={"Trendyol Cases": {}})

    rejected = client.post(
        "/tags",
        json={"Trendyol Cases": {"children": {"bad/name": {}}}},
    )

    assert rejected.status_code == 422
    assert client.get("/tags").json() == {
        "Trendyol Cases": {"path": "Trendyol Cases", "children": {}}
    }
