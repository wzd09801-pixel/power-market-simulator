from __future__ import annotations

from fastapi.testclient import TestClient


def test_system_status_includes_data_modes(client: TestClient) -> None:
    response = client.get("/v1/system/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["no_auto_trading"] is True
    assert "scenario_simulated" in payload["data_modes"]
