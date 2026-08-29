"""Pruebas de los puntos por los que la nube observa a la aplicación.

Son las tres cosas que el balanceador, CloudWatch y el navegador del estudiante consultan sin
que nadie del equipo esté mirando: el health check, el readiness y las cabeceras CORS. Van como
tests de integración porque el readiness solo demuestra algo si PostgreSQL y Redis están de
verdad al otro lado.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_el_liveness_no_toca_las_dependencias(client: TestClient) -> None:
    """El Application Gateway mira esta ruta: si dependiera de PostgreSQL, una caída retiraría
    instancias sanas.
    """
    respuesta = client.get("/health")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "ok"
    # Ambiente y versión permiten ver de un vistazo qué build corre en cada entorno.
    assert "environment" in cuerpo and "version" in cuerpo


@pytest.mark.integration
def test_el_readiness_confirma_postgres_y_redis(client: TestClient) -> None:
    """Es la comprobación posterior al despliegue: dice si la instancia quedó bien configurada."""
    respuesta = client.get("/health/ready")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "ready"
    assert cuerpo["dependencies"]["postgres"] == "ok"
    # Redis puede reportar `degraded` sin que la instancia deje de estar lista: la aplicación
    # degrada a PostgreSQL cuando no hay caché.
    assert cuerpo["dependencies"]["redis"] in {"ok", "degraded"}


@pytest.mark.integration
def test_cada_respuesta_lleva_su_identificador_de_peticion(client: TestClient) -> None:
    """Con autoescalado, ese identificador es lo único que permite encontrar una petición."""
    respuesta = client.get("/health")

    assert respuesta.headers.get("X-Request-ID")


@pytest.mark.integration
@pytest.mark.parametrize("cabecera", ["X-Azure-Ref", "traceparent"])
def test_el_identificador_de_peticion_reutiliza_la_traza_del_borde(
    client: TestClient, cabecera: str
) -> None:
    """Así la línea de la aplicación y la de Front Door hablan del mismo viaje."""
    traza = "20240301T101010Z-r1abc2de3f4g5h6i-BOG"

    respuesta = client.get("/health", headers={cabecera: traza})

    assert respuesta.headers["X-Request-ID"] == traza


@pytest.mark.integration
def test_x_azure_ref_gana_a_traceparent(client: TestClient) -> None:
    """El identificador se toma de FUERA hacia dentro.

    Front Door toca la petición antes que nadie y es el único valor que aparece en sus
    registros: si ganara `traceparent`, buscar allí por el identificador que reportó el
    estudiante no encontraría nada.
    """
    respuesta = client.get(
        "/health",
        headers={"X-Azure-Ref": "el-del-borde", "traceparent": "el-de-dentro"},
    )

    assert respuesta.headers["X-Request-ID"] == "el-del-borde"


@pytest.mark.integration
def test_la_api_autoriza_al_origen_declarado(client: TestClient) -> None:
    """En la nube el frontend vive en Front Door, otro dominio: sin esto el navegador bloquea."""
    respuesta = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert respuesta.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.integration
def test_la_api_no_autoriza_a_un_origen_desconocido(client: TestClient) -> None:
    """La lista es explícita: nunca `*`, y menos con credenciales."""
    respuesta = client.get("/health", headers={"Origin": "https://sitio-que-no-toca.example"})

    assert "access-control-allow-origin" not in respuesta.headers


@pytest.mark.integration
def test_el_preflight_declara_los_metodos_que_usa_el_frontend(client: TestClient) -> None:
    """El navegador pregunta antes de un DELETE; si la respuesta no lo lista, no lo envía."""
    respuesta = client.options(
        "/api/v1/enrollments/00000000-0000-0000-0000-000000000000",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert respuesta.status_code == 200, respuesta.text
    assert "DELETE" in respuesta.headers.get("access-control-allow-methods", "")
