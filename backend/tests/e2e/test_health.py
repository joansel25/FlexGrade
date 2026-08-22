"""Pruebas end to end del endpoint de salud.

Es el contrato que consumen el `HEALTHCHECK` de Docker y el balanceador: si se rompe, el
despliegue deja de considerarse sano aunque la aplicación funcione. Por eso se prueba pieza por
pieza del cuerpo de la respuesta.
"""

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.config.settings import get_settings


@pytest.mark.e2e
def test_health_when_service_is_running_returns_200(client: TestClient) -> None:
    """El endpoint responde 200 sin requerir autenticación ni dependencias externas."""
    response = client.get("/health")

    assert response.status_code == 200


@pytest.mark.e2e
def test_health_when_service_is_running_reports_status_ok(client: TestClient) -> None:
    """El cuerpo reporta `status: ok`, el literal que verifica el health check del ALB."""
    response = client.get("/health")

    assert response.json()["status"] == "ok"


@pytest.mark.e2e
def test_health_when_environment_is_configured_reports_that_environment(
    client: TestClient,
) -> None:
    """El cuerpo refleja el ambiente configurado, no un valor fijo en el código."""
    response = client.get("/health")

    assert response.json()["environment"] == get_settings().environment
