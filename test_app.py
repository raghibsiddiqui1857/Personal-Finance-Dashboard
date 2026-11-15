import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "t.db"), "TESTING": True})
    return app.test_client()


def test_empty_dashboard(client):
    assert client.get("/").status_code == 200


def test_add_and_summary(client):
    client.post("/add", data=dict(date="2026-01-05", type="income", category="salary", amount="1000"))
    client.post("/add", data=dict(date="2026-01-06", type="expense", category="food", amount="300"))
    t = client.get("/api/summary").get_json()["totals"]
    assert t["savings"] == 700


def test_rejects_bad_input(client):
    client.post("/add", data=dict(date="x", type="expense", category="a", amount="-5"))
    assert client.get("/api/transactions").get_json() == []


def test_forecast_after_seed(client):
    client.post("/seed")
    assert client.get("/").status_code == 200
    f = client.get("/api/summary").get_json()["forecast"]
    assert f and f["months_used"] >= 3
