"""Pruebas de integración de los endpoints del catálogo.

Recorren las cuatro capas contra PostgreSQL y Redis reales: router -> caso de uso ->
repositorio -> base de datos, con la caché por medio.

El test que da sentido a todo el archivo es
`test_offering_detail_reflects_a_capacity_change_immediately`: demuestra, contra
infraestructura real, que un cambio de cupo se ve al instante aunque el resto del grupo venga
de la caché. Es el criterio de terminado de la Fase 2.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.integration.conftest import CatalogoDePrueba

RUTA_COURSES = "/api/v1/courses"
RUTA_OFFERINGS = "/api/v1/offerings"
RUTA_PERIODO = "/api/v1/enrollment-periods/current"

# ---------------------------------------------------------------------------
# GET /courses
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_list_courses_returns_the_paginated_envelope(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    respuesta = client.get(RUTA_COURSES)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"items", "total", "page", "size"}
    assert cuerpo["total"] == 3


@pytest.mark.integration
def test_list_courses_items_follow_the_documented_shape(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    materia = client.get(RUTA_COURSES).json()["items"][0]

    assert set(materia) == {"id", "code", "name", "credits", "description"}


@pytest.mark.integration
def test_list_courses_filters_by_program(client: TestClient, catalogo: CatalogoDePrueba) -> None:
    cuerpo = client.get(RUTA_COURSES, params={"program_id": str(catalogo.program_id)}).json()

    # Física no está en ningún plan de estudios.
    assert cuerpo["total"] == 2
    assert str(catalogo.fisica_id) not in {m["id"] for m in cuerpo["items"]}


@pytest.mark.integration
def test_list_courses_filters_by_search_text(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(RUTA_COURSES, params={"search": "cálculo"}).json()

    assert cuerpo["total"] == 2


@pytest.mark.integration
def test_list_courses_respects_the_page_size(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(RUTA_COURSES, params={"page": 1, "size": 2}).json()

    assert len(cuerpo["items"]) == 2
    assert cuerpo["total"] == 3


@pytest.mark.integration
def test_list_courses_rejects_a_size_over_the_limit(client: TestClient) -> None:
    # El techo se declara en el router, así que FastAPI lo rechaza antes de llegar al caso de
    # uso: `?size=100000` no puede convertirse en una consulta de cien mil filas.
    assert client.get(RUTA_COURSES, params={"size": 100_000}).status_code == 422


@pytest.mark.integration
def test_list_courses_rejects_a_non_positive_page(client: TestClient) -> None:
    assert client.get(RUTA_COURSES, params={"page": 0}).status_code == 422


# ---------------------------------------------------------------------------
# GET /courses/{id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_course_detail_includes_its_prerequisites(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(f"{RUTA_COURSES}/{catalogo.calculo_ii_id}").json()

    assert cuerpo["code"] == "MAT102"
    assert [p["code"] for p in cuerpo["prerequisites"]] == ["MAT101"]


@pytest.mark.integration
def test_course_detail_without_prerequisites_returns_an_empty_list(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    assert client.get(f"{RUTA_COURSES}/{catalogo.calculo_i_id}").json()["prerequisites"] == []


@pytest.mark.integration
def test_course_detail_when_missing_returns_404_with_the_error_code(client: TestClient) -> None:
    respuesta = client.get(f"{RUTA_COURSES}/{uuid4()}")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "COURSE_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /courses/{id}/offerings
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_course_offerings_returns_only_the_active_period(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    # La fixture crea un tercer grupo de la misma materia en un período cerrado.
    cuerpo = client.get(f"{RUTA_COURSES}/{catalogo.calculo_i_id}/offerings").json()

    assert cuerpo["period_code"] == "2025-2-V1"
    assert [g["group_number"] for g in cuerpo["offerings"]] == ["01", "02"]


@pytest.mark.integration
def test_course_offerings_include_professor_schedule_and_slots(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(f"{RUTA_COURSES}/{catalogo.calculo_i_id}/offerings").json()
    grupo_01 = next(g for g in cuerpo["offerings"] if g["group_number"] == "01")

    assert grupo_01["professor"] == "Ana Pérez"
    assert grupo_01["available_slots"] == 3
    assert [f["day_of_week"] for f in grupo_01["schedule"]] == [1, 3]


@pytest.mark.integration
def test_course_offerings_include_a_group_without_professor(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(f"{RUTA_COURSES}/{catalogo.calculo_i_id}/offerings").json()
    grupo_02 = next(g for g in cuerpo["offerings"] if g["group_number"] == "02")

    assert grupo_02["professor"] is None
    assert grupo_02["schedule"] == []


@pytest.mark.integration
def test_course_offerings_when_not_offered_returns_an_empty_list(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(f"{RUTA_COURSES}/{catalogo.fisica_id}/offerings").json()

    assert cuerpo["offerings"] == []


@pytest.mark.integration
def test_course_offerings_when_no_active_period_returns_404(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    db_session.execute(text("UPDATE enrollment_periods SET is_active = FALSE"))
    db_session.commit()

    respuesta = client.get(f"{RUTA_COURSES}/{catalogo.calculo_i_id}/offerings")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "NO_ACTIVE_PERIOD"


# ---------------------------------------------------------------------------
# GET /offerings/{id} — la regla crítica
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_offering_detail_returns_the_group(client: TestClient, catalogo: CatalogoDePrueba) -> None:
    cuerpo = client.get(f"{RUTA_OFFERINGS}/{catalogo.offering_grupo_01_id}").json()

    assert cuerpo["group_number"] == "01"
    assert cuerpo["professor"] == "Ana Pérez"
    assert cuerpo["available_slots"] == 3
    assert cuerpo["course_id"] == str(catalogo.calculo_i_id)


@pytest.mark.integration
def test_offering_detail_reflects_a_capacity_change_immediately(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    """El criterio de terminado de la Fase 2, contra Redis y PostgreSQL reales.

    Se consulta el grupo —lo que lo deja cacheado—, se ocupan dos cupos por debajo, y se
    vuelve a consultar dentro de la ventana del TTL de 30 segundos. La respuesta tiene que
    mostrar el cupo nuevo.

    Si este test falla, significa que la disponibilidad se está sirviendo desde la caché, y
    entonces el sistema puede decirle a un estudiante que hay plaza cuando ya no la hay: el
    fallo exacto que el proyecto entero existe para evitar.
    """
    ruta = f"{RUTA_OFFERINGS}/{catalogo.offering_grupo_01_id}"

    primera = client.get(ruta).json()
    assert primera["available_slots"] == 3

    db_session.execute(
        text(
            "UPDATE course_offerings SET enrolled_count = 39, version = version + 1 "
            "WHERE id = :id"
        ),
        {"id": catalogo.offering_grupo_01_id},
    )
    db_session.commit()

    segunda = client.get(ruta).json()

    assert segunda["available_slots"] == 1, "la disponibilidad se sirvió desde la caché"
    assert segunda["enrolled_count"] == 39
    # La parte estática sí se sirve cacheada, y sigue siendo correcta.
    assert segunda["professor"] == "Ana Pérez"
    assert len(segunda["schedule"]) == 2


@pytest.mark.integration
def test_offering_detail_shows_zero_slots_when_the_group_fills_up(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    ruta = f"{RUTA_OFFERINGS}/{catalogo.offering_grupo_01_id}"
    client.get(ruta)

    db_session.execute(
        text("UPDATE course_offerings SET enrolled_count = 40 WHERE id = :id"),
        {"id": catalogo.offering_grupo_01_id},
    )
    db_session.commit()

    assert client.get(ruta).json()["available_slots"] == 0


@pytest.mark.integration
def test_offering_detail_when_missing_returns_404_with_the_error_code(
    client: TestClient,
) -> None:
    respuesta = client.get(f"{RUTA_OFFERINGS}/{uuid4()}")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "OFFERING_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /enrollment-periods/current
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_current_period_returns_the_active_window_as_open(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    cuerpo = client.get(RUTA_PERIODO).json()

    assert cuerpo["code"] == "2025-2-V1"
    assert cuerpo["is_active"] is True
    assert cuerpo["is_open"] is True
    assert cuerpo["time_remaining_seconds"] > 0


@pytest.mark.integration
def test_current_period_when_activated_but_not_started_is_not_open(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    # La distinción que el frontend necesita: hay período, pero todavía no abre.
    db_session.execute(
        text(
            "UPDATE enrollment_periods "
            "SET starts_at = NOW() + INTERVAL '2 days', ends_at = NOW() + INTERVAL '4 days' "
            "WHERE is_active = TRUE"
        )
    )
    db_session.commit()

    cuerpo = client.get(RUTA_PERIODO).json()

    assert cuerpo["is_active"] is True
    assert cuerpo["is_open"] is False


@pytest.mark.integration
def test_current_period_when_none_is_active_returns_404(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    db_session.execute(text("UPDATE enrollment_periods SET is_active = FALSE"))
    db_session.commit()

    respuesta = client.get(RUTA_PERIODO)

    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["code"] == "NO_ACTIVE_PERIOD"
