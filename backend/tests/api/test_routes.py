import pytest

pytestmark = pytest.mark.integration


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_explain_ingredient_endpoint(client):
    response = client.post("/explain-ingredient", json={"ingredient_name": "casein"})
    assert response.status_code == 200
    body = response.json()
    assert body["ingredient_name"] == "casein"
    assert len(body["explanation"]) > 0


def test_explain_ingredient_rejects_empty_name(client):
    response = client.post("/explain-ingredient", json={"ingredient_name": ""})
    assert response.status_code == 422


def test_explain_swap_scan_flow(client):
    response = client.post("/explain-swap", json={
        "original_food": "Potato Chips",
        "recommended_food": "Roasted Makhana",
        "entry_point": "scan",
    })
    assert response.status_code == 200


def test_explain_swap_craving_flow(client):
    response = client.post("/explain-swap", json={
        "craving_query": "something crunchy and salty",
        "recommended_food": "Roasted Makhana",
        "entry_point": "craving",
    })
    assert response.status_code == 200


def test_explain_swap_mismatched_entry_point_rejected(client):
    # entry_point='craving' but original_food given instead of craving_query
    response = client.post("/explain-swap", json={
        "original_food": "Potato Chips",
        "recommended_food": "Roasted Makhana",
        "entry_point": "craving",
    })
    assert response.status_code == 422