"""Pruebas de integración del catálogo y los cupos de administración (iteración 4.3).

Estos tres endpoints escriben en las tablas más restringidas del esquema, y casi todo lo que
protegen vive en PostgreSQL: la restricción `UNIQUE` de `courses.code`, la de
`(enrollment_period_id, course_id, group_number)` en `course_offerings` y el
`CHECK (enrolled_count <= total_capacity)`. Un doble en memoria no tiene ninguna de las tres,
así que solo aquí se puede comprobar que las comprobaciones del caso de uso y las de la base
dicen lo mismo.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from tests.integration.conftest import CatalogoDePrueba

RUTA_MATERIAS = "/api/v1/admin/courses"
RUTA_GRUPOS = "/api/v1/admin/offerings"
PASSWORD = "SecurePass123"


@pytest.fixture
def admin(client: TestClient, db_session: Session) -> dict[str, str]:
    """Devuelve la cabecera de autorización de una cuenta con rol ADMIN."""
    hasher = JWTAuthService(get_settings())

    usuario = UserModel(
        id=uuid4(),
        email="admin.catalogo@tdea.edu.co",
        password_hash=hasher.hash(PASSWORD),
        role="ADMIN",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.add(
        AdministratorModel(
            id=uuid4(), user_id=usuario.id, full_name="Admin Catálogo", department="Registro"
        )
    )
    db_session.commit()

    respuesta = client.post(
        "/api/v1/auth/login", json={"email": usuario.email, "password": PASSWORD}
    )
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


# ---------------------------------------------------------------------------
# POST /admin/courses
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_crear_materia_devuelve_201_y_queda_en_el_catalogo(
    client: TestClient, admin: dict[str, str], db_session: Session
) -> None:
    respuesta = client.post(
        RUTA_MATERIAS,
        json={"code": "qui101", "name": "Química General", "credits": 3},
        headers=admin,
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    # El código viaja normalizado: el value object lo pasa a mayúsculas antes de persistirlo.
    assert cuerpo["code"] == "QUI101"

    detalle = client.get(f"/api/v1/courses/{cuerpo['id']}")
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["name"] == "Química General"


@pytest.mark.integration
def test_crear_materia_con_codigo_repetido_devuelve_409(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """La restricción UNIQUE también lo impediría, pero con un mensaje que no dice qué hacer."""
    respuesta = client.post(
        RUTA_MATERIAS,
        json={"code": "MAT101", "name": "Cálculo I bis", "credits": 4},
        headers=admin,
    )

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["error"]["code"] == "DUPLICATE_COURSE_CODE"


@pytest.mark.integration
def test_crear_materia_con_codigo_mal_formado_devuelve_400(
    client: TestClient, admin: dict[str, str]
) -> None:
    respuesta = client.post(
        RUTA_MATERIAS, json={"code": "101", "name": "Sin área", "credits": 4}, headers=admin
    )

    assert respuesta.status_code == 400, respuesta.text


@pytest.mark.integration
def test_crear_materia_sin_token_devuelve_401(client: TestClient) -> None:
    respuesta = client.post(RUTA_MATERIAS, json={"code": "QUI102", "name": "Q", "credits": 1})

    assert respuesta.status_code == 401, respuesta.text


# ---------------------------------------------------------------------------
# POST /admin/offerings
# ---------------------------------------------------------------------------


def _cuerpo_de_grupo(catalogo: CatalogoDePrueba, group_number: str = "03") -> dict[str, object]:
    return {
        "course_id": str(catalogo.calculo_i_id),
        "professor_id": str(catalogo.professor_id),
        "group_number": group_number,
        "total_capacity": 40,
        "schedule": [
            {
                "day_of_week": 2,
                "start_time": "10:00",
                "end_time": "12:00",
                "space_code": "B-101",
            }
        ],
    }


@pytest.mark.integration
def test_crear_grupo_lo_publica_en_el_periodo_activo_con_su_horario(
    client: TestClient,
    admin: dict[str, str],
    catalogo: CatalogoDePrueba,
    db_session: Session,
) -> None:
    respuesta = client.post(RUTA_GRUPOS, json=_cuerpo_de_grupo(catalogo), headers=admin)

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["enrollment_period_id"] == str(catalogo.period_id)
    assert cuerpo["available_slots"] == 40
    # El docente viaja resuelto, igual que en `GET /offerings/{id}`.
    assert cuerpo["professor"] == "Ana Pérez"

    franjas = db_session.execute(
        select(func.count())
        .select_from(ScheduleBlockModel)
        .where(ScheduleBlockModel.course_offering_id == UUID(cuerpo["id"]))
    ).scalar_one()
    assert franjas == 1


@pytest.mark.integration
def test_el_grupo_creado_aparece_en_el_catalogo_publico(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """El recorrido completo: se abre el grupo y un estudiante ya lo ve con su cupo libre."""
    creado = client.post(RUTA_GRUPOS, json=_cuerpo_de_grupo(catalogo), headers=admin)
    assert creado.status_code == 201, creado.text

    grupos = client.get(f"/api/v1/courses/{catalogo.calculo_i_id}/offerings")
    assert grupos.status_code == 200, grupos.text
    numeros = [g["group_number"] for g in grupos.json()["offerings"]]
    assert "03" in numeros


@pytest.mark.integration
def test_crear_grupo_con_numero_repetido_devuelve_409(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """`01` ya existe para Cálculo I en el período activo."""
    respuesta = client.post(
        RUTA_GRUPOS, json=_cuerpo_de_grupo(catalogo, group_number="01"), headers=admin
    )

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["error"]["code"] == "DUPLICATE_OFFERING_GROUP"


@pytest.mark.integration
def test_crear_grupo_con_docente_inexistente_devuelve_404(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """Sin la comprobación previa, la clave foránea daría un 500 en vez de este 404."""
    cuerpo = _cuerpo_de_grupo(catalogo)
    cuerpo["professor_id"] = str(uuid4())

    respuesta = client.post(RUTA_GRUPOS, json=cuerpo, headers=admin)

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["error"]["code"] == "PROFESSOR_NOT_FOUND"


@pytest.mark.integration
def test_crear_grupo_con_materia_inexistente_devuelve_404(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    cuerpo = _cuerpo_de_grupo(catalogo)
    cuerpo["course_id"] = str(uuid4())

    respuesta = client.post(RUTA_GRUPOS, json=cuerpo, headers=admin)

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["error"]["code"] == "COURSE_NOT_FOUND"


@pytest.mark.integration
def test_crear_grupo_con_horario_solapado_devuelve_409(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    cuerpo = _cuerpo_de_grupo(catalogo)
    cuerpo["schedule"] = [
        {"day_of_week": 2, "start_time": "10:00", "end_time": "12:00", "space_code": "B-101"},
        {"day_of_week": 2, "start_time": "11:00", "end_time": "13:00", "space_code": "B-102"},
    ]

    respuesta = client.post(RUTA_GRUPOS, json=cuerpo, headers=admin)

    assert respuesta.status_code == 409, respuesta.text
    assert respuesta.json()["error"]["code"] == "OVERLAPPING_SCHEDULE"


@pytest.mark.integration
def test_crear_grupo_con_cupo_no_positivo_devuelve_422(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """Lo rechaza el schema antes de llegar al `CHECK (total_capacity > 0)` de PostgreSQL."""
    cuerpo = _cuerpo_de_grupo(catalogo)
    cuerpo["total_capacity"] = 0

    respuesta = client.post(RUTA_GRUPOS, json=cuerpo, headers=admin)

    assert respuesta.status_code == 422, respuesta.text


# ---------------------------------------------------------------------------
# PUT /admin/offerings/{id}/capacity
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ampliar_el_cupo_lo_persiste_y_refresca_el_catalogo(
    client: TestClient,
    admin: dict[str, str],
    catalogo: CatalogoDePrueba,
    db_session: Session,
) -> None:
    """Comprueba la invalidación de caché: se consulta ANTES de ajustar para poblarla.

    Sin el `delete` del caso de uso, la segunda consulta seguiría sirviendo el cupo viejo desde
    Redis durante todo el TTL, junto a un `enrolled_count` fresco: dos datos de momentos
    distintos en la misma respuesta.
    """
    ruta_publica = f"/api/v1/offerings/{catalogo.offering_grupo_01_id}"
    antes = client.get(ruta_publica)
    assert antes.status_code == 200, antes.text
    assert antes.json()["total_capacity"] == 40

    respuesta = client.put(
        f"{RUTA_GRUPOS}/{catalogo.offering_grupo_01_id}/capacity",
        json={"total_capacity": 60},
        headers=admin,
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["total_capacity"] == 60
    # 60 - 37 inscritos.
    assert respuesta.json()["available_slots"] == 23

    despues = client.get(ruta_publica)
    assert despues.json()["total_capacity"] == 60

    db_session.expire_all()
    fila = db_session.get(CourseOfferingModel, catalogo.offering_grupo_01_id)
    assert fila is not None
    assert fila.total_capacity == 60
    # La versión se mueve en cada modificación del cupo: es la marca del bloqueo optimista.
    assert fila.version == 1


@pytest.mark.integration
def test_reducir_el_cupo_por_debajo_de_los_inscritos_devuelve_409(
    client: TestClient,
    admin: dict[str, str],
    catalogo: CatalogoDePrueba,
    db_session: Session,
) -> None:
    """El grupo 01 tiene 37 inscritos: bajarlo a 10 dejaría fuera a 27 personas.

    Es la comprobación que evita chocar contra `CHECK (enrolled_count <= total_capacity)`, que
    abortaría la transacción con un error de restricción en vez de explicar el problema.
    """
    respuesta = client.put(
        f"{RUTA_GRUPOS}/{catalogo.offering_grupo_01_id}/capacity",
        json={"total_capacity": 10},
        headers=admin,
    )

    assert respuesta.status_code == 409, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["error"]["code"] == "CAPACITY_BELOW_ENROLLED"
    assert cuerpo["error"]["details"]["enrolled_count"] == 37

    db_session.expire_all()
    fila = db_session.get(CourseOfferingModel, catalogo.offering_grupo_01_id)
    assert fila is not None
    assert fila.total_capacity == 40


@pytest.mark.integration
def test_reducir_el_cupo_hasta_los_inscritos_deja_el_grupo_lleno(
    client: TestClient, admin: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """Cerrar el grupo en su ocupación exacta es válido: nadie queda expulsado."""
    respuesta = client.put(
        f"{RUTA_GRUPOS}/{catalogo.offering_grupo_01_id}/capacity",
        json={"total_capacity": 37},
        headers=admin,
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["available_slots"] == 0


@pytest.mark.integration
def test_ajustar_el_cupo_de_un_grupo_inexistente_devuelve_404(
    client: TestClient, admin: dict[str, str]
) -> None:
    respuesta = client.put(
        f"{RUTA_GRUPOS}/{uuid4()}/capacity", json={"total_capacity": 10}, headers=admin
    )

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["error"]["code"] == "OFFERING_NOT_FOUND"


@pytest.mark.integration
def test_un_estudiante_no_puede_tocar_el_catalogo(
    client: TestClient, estudiante_registrado: dict[str, str], catalogo: CatalogoDePrueba
) -> None:
    """La protección la declara el router entero, no cada endpoint."""
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": estudiante_registrado["email"],
            "password": estudiante_registrado["password"],
        },
    )
    assert login.status_code == 200, login.text
    cabecera = {"Authorization": f"Bearer {login.json()['access_token']}"}

    for respuesta in (
        client.post(
            RUTA_MATERIAS,
            json={"code": "QUI103", "name": "Química", "credits": 3},
            headers=cabecera,
        ),
        client.post(RUTA_GRUPOS, json=_cuerpo_de_grupo(catalogo), headers=cabecera),
        client.put(
            f"{RUTA_GRUPOS}/{catalogo.offering_grupo_01_id}/capacity",
            json={"total_capacity": 50},
            headers=cabecera,
        ),
    ):
        assert respuesta.status_code == 403, respuesta.text
        assert respuesta.json()["error"]["code"] == "ADMIN_REQUIRED"


@pytest.mark.integration
def test_abrir_un_grupo_con_un_aula_inexistente_devuelve_404(
    client: TestClient, catalogo: CatalogoDePrueba, admin: dict[str, str]
) -> None:
    """Antes cualquier cadena era un aula válida y se guardaba tal cual.

    Un texto que nadie reconoce no es un error visible: es un horario que dice que la clase es
    en un salón que no existe, y nadie se entera hasta que alguien va a buscarlo.
    """
    respuesta = client.post(
        "/api/v1/admin/offerings",
        json={
            "course_id": str(catalogo.calculo_i_id),
            "group_number": "77",
            "total_capacity": 30,
            "schedule": [
                {
                    "day_of_week": 4,
                    "start_time": "14:00",
                    "end_time": "16:00",
                    "space_code": "NO-EXISTE",
                }
            ],
        },
        headers=admin,
    )

    assert respuesta.status_code == 404, respuesta.text
    error = respuesta.json()["error"]
    assert error["code"] == "SPACE_NOT_FOUND"
    # Lleva el CÓDIGO que se envió, no un identificador que nadie escribió.
    assert error["details"]["code"] == "NO-EXISTE"


@pytest.mark.integration
def test_el_aula_del_grupo_creado_vuelve_en_la_respuesta(
    client: TestClient, catalogo: CatalogoDePrueba, admin: dict[str, str]
) -> None:
    # El contrato público no cambió al convertirse el aula en entidad: sigue siendo `classroom`
    # con el código del espacio, que es lo que quien lee un horario quiere leer.
    respuesta = client.post(
        "/api/v1/admin/offerings",
        json={
            "course_id": str(catalogo.calculo_i_id),
            "group_number": "78",
            "total_capacity": 30,
            "schedule": [
                {
                    "day_of_week": 4,
                    "start_time": "14:00",
                    "end_time": "16:00",
                    "space_code": "b-101",
                }
            ],
        },
        headers=admin,
    )

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["schedule"][0]["classroom"] == "B-101"


@pytest.mark.integration
def test_abrir_un_grupo_en_un_aula_ocupada_devuelve_409_con_quien_la_ocupa(
    client: TestClient, catalogo: CatalogoDePrueba, admin: dict[str, str]
) -> None:
    """La fixture ya tiene el grupo 01 en A-201 el lunes de 8 a 10.

    El rechazo tiene que decir con QUIÉN chocas: «el aula está ocupada» deja a quien programa
    buscando a ciegas, y con el grupo delante sabe con quién hablar.
    """
    respuesta = client.post(
        "/api/v1/admin/offerings",
        json={
            "course_id": str(catalogo.calculo_ii_id),
            "group_number": "60",
            "total_capacity": 30,
            "schedule": [
                {
                    "day_of_week": 1,
                    "start_time": "09:00",
                    "end_time": "11:00",
                    "space_code": "A-201",
                }
            ],
        },
        headers=admin,
    )

    assert respuesta.status_code == 409, respuesta.text
    error = respuesta.json()["error"]
    assert error["code"] == "SPACE_DOUBLE_BOOKED"
    assert error["details"]["space_code"] == "A-201"
    assert error["details"]["occupied_by"]["course_code"] == "MAT101"


@pytest.mark.integration
def test_una_clase_consecutiva_en_la_misma_aula_se_acepta(
    client: TestClient, catalogo: CatalogoDePrueba, admin: dict[str, str]
) -> None:
    # El grupo 01 ocupa A-201 hasta las 10:00. Empezar a las 10:00 es una clase seguida, no un
    # choque, y tanto la validación como el rango `[)` de la restricción tienen que coincidir.
    respuesta = client.post(
        "/api/v1/admin/offerings",
        json={
            "course_id": str(catalogo.calculo_ii_id),
            "group_number": "61",
            "total_capacity": 30,
            "schedule": [
                {
                    "day_of_week": 1,
                    "start_time": "10:00",
                    "end_time": "12:00",
                    "space_code": "A-201",
                }
            ],
        },
        headers=admin,
    )

    assert respuesta.status_code == 201, respuesta.text


@pytest.mark.integration
def test_un_grupo_que_no_cabe_en_el_aula_devuelve_409(
    client: TestClient, catalogo: CatalogoDePrueba, admin: dict[str, str]
) -> None:
    # B-102 tiene aforo para 30 en la fixture.
    respuesta = client.post(
        "/api/v1/admin/offerings",
        json={
            "course_id": str(catalogo.calculo_ii_id),
            "group_number": "62",
            "total_capacity": 45,
            "schedule": [
                {
                    "day_of_week": 6,
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "space_code": "B-102",
                }
            ],
        },
        headers=admin,
    )

    assert respuesta.status_code == 409, respuesta.text
    error = respuesta.json()["error"]
    assert error["code"] == "SPACE_CAPACITY_EXCEEDED"
    assert error["details"] == {"space_code": "B-102", "capacity": 30, "required": 45}


@pytest.mark.integration
def test_la_base_rechaza_la_doble_reserva_aunque_el_codigo_no_mire(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """LA RED FINAL, probada saltándose la aplicación entera.

    Es la razón de existir de la restricción de exclusión: dos peticiones simultáneas pueden
    comprobar a la vez que el aula está libre y reservarla las dos, y ninguna validación en la
    aplicación cierra esa carrera. Se inserta directamente con SQL, que es lo más parecido a
    «el código se equivocó» que se puede escribir en un test.
    """
    from sqlalchemy.exc import IntegrityError

    from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel

    ocupada = db_session.execute(
        select(ScheduleBlockModel).where(ScheduleBlockModel.space_id.is_not(None)).limit(1)
    ).scalar_one()

    db_session.add(
        ScheduleBlockModel(
            course_offering_id=ocupada.course_offering_id,
            enrollment_period_id=ocupada.enrollment_period_id,
            day_of_week=ocupada.day_of_week,
            # Solapada a medias: empieza dentro de la que ya existe.
            start_time=time(ocupada.start_time.hour, 30),
            end_time=time(ocupada.end_time.hour + 1, 0),
            space_id=ocupada.space_id,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


@pytest.mark.integration
def test_la_misma_aula_a_la_misma_hora_en_otro_periodo_si_se_permite(
    db_session: Session, catalogo: CatalogoDePrueba
) -> None:
    """Reutilizar un aula el semestre siguiente es lo normal, no un conflicto.

    Es lo que obliga a llevar `enrollment_period_id` en la propia franja: sin esa columna la
    restricción no podría distinguir los dos casos y prohibiría el legítimo.
    """
    from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
    from app.infrastructure.persistence.sqlalchemy.models.enrollment_period import (
        EnrollmentPeriodModel,
    )
    from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel

    ocupada = db_session.execute(
        select(ScheduleBlockModel).where(ScheduleBlockModel.space_id.is_not(None)).limit(1)
    ).scalar_one()

    otro_periodo = EnrollmentPeriodModel(
        id=uuid4(),
        code="2026-1-V1",
        academic_period="2026-1",
        name="Matrícula 2026-1",
        starts_at=datetime.now(UTC) + timedelta(days=100),
        ends_at=datetime.now(UTC) + timedelta(days=130),
        is_active=False,
    )
    db_session.add(otro_periodo)
    db_session.flush()

    grupo = CourseOfferingModel(
        id=uuid4(),
        enrollment_period_id=otro_periodo.id,
        course_id=catalogo.calculo_i_id,
        group_number="01",
        total_capacity=30,
        enrolled_count=0,
    )
    db_session.add(grupo)
    db_session.flush()

    db_session.add(
        ScheduleBlockModel(
            course_offering_id=grupo.id,
            enrollment_period_id=otro_periodo.id,
            day_of_week=ocupada.day_of_week,
            start_time=ocupada.start_time,
            end_time=ocupada.end_time,
            space_id=ocupada.space_id,
        )
    )

    db_session.commit()  # no debe lanzar


# ---------------------------------------------------------------------------
# GET /admin/spaces/available (iteración 7.3)
# ---------------------------------------------------------------------------

RUTA_DISPONIBLES = "/api/v1/admin/spaces/available"


def _disponibles(client, admin, **params):
    respuesta = client.get(RUTA_DISPONIBLES, params=params, headers=admin)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


@pytest.mark.integration
def test_un_aula_ocupada_no_aparece_como_disponible(
    client: TestClient, catalogo: CatalogoDePrueba, admin: dict[str, str]
) -> None:
    # La fixture deja el grupo 01 en A-201 el lunes de 8 a 10.
    cuerpo = _disponibles(client, admin, day_of_week=1, start_time="08:00", end_time="10:00")

    codigos = {e["code"] for e in cuerpo["items"]}
    assert "A-201" not in codigos
    # Las demás sí: ocupar una no oculta el resto del inventario.
    assert "B-101" in codigos


@pytest.mark.integration
def test_la_misma_aula_en_otro_dia_si_esta_disponible(
    client: TestClient, catalogo: CatalogoDePrueba, admin: dict[str, str]
) -> None:
    cuerpo = _disponibles(client, admin, day_of_week=5, start_time="08:00", end_time="10:00")

    assert "A-201" in {e["code"] for e in cuerpo["items"]}


@pytest.mark.integration
def test_una_franja_consecutiva_deja_el_aula_disponible(
    client: TestClient, catalogo: CatalogoDePrueba, admin: dict[str, str]
) -> None:
    """La disponibilidad usa el MISMO criterio que el rechazo, y eso es lo que se prueba.

    A-201 está ocupada hasta las 10:00. Si esta consulta contara las 10:00 como ocupadas,
    ofrecería menos aulas de las que `POST /admin/offerings` acepta; si contara de más,
    ofrecería aulas que ese endpoint va a rechazar. Las dos versiones del error son igual de
    malas y las dos aparecen en cuanto los dos criterios divergen.
    """
    cuerpo = _disponibles(client, admin, day_of_week=1, start_time="10:00", end_time="12:00")

    assert "A-201" in {e["code"] for e in cuerpo["items"]}


@pytest.mark.integration
def test_el_aforo_minimo_descarta_las_aulas_pequenas(
    client: TestClient, catalogo: CatalogoDePrueba, admin: dict[str, str]
) -> None:
    # En la fixture: A-203 tiene 35 y B-101 tiene 50.
    cuerpo = _disponibles(
        client, admin, day_of_week=6, start_time="08:00", end_time="10:00", min_capacity=40
    )

    codigos = {e["code"] for e in cuerpo["items"]}
    assert "B-101" in codigos
    assert "A-203" not in codigos


@pytest.mark.integration
def test_un_aula_sin_aforo_registrado_sigue_apareciendo(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session, admin: dict[str, str]
) -> None:
    """Excluirla escondería un aula que probablemente sirve.

    Es la misma decisión que toma `Space.fits` al devolver `None` y que la 7.2 aplica al no
    bloquear por un aforo que nadie midió. Quien consulta ve `capacity: null` y decide.
    """
    from app.infrastructure.persistence.sqlalchemy.models.space import SpaceModel

    db_session.add(SpaceModel(id=uuid4(), code="SIN-AFORO", space_type="CLASSROOM", capacity=None))
    db_session.commit()

    cuerpo = _disponibles(
        client, admin, day_of_week=6, start_time="08:00", end_time="10:00", min_capacity=200
    )

    encontrada = next(e for e in cuerpo["items"] if e["code"] == "SIN-AFORO")
    assert encontrada["capacity"] is None


@pytest.mark.integration
def test_se_puede_filtrar_por_tipo_de_espacio(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session, admin: dict[str, str]
) -> None:
    from app.infrastructure.persistence.sqlalchemy.models.space import SpaceModel

    db_session.add(SpaceModel(id=uuid4(), code="LAB-99", space_type="LABORATORY", capacity=20))
    db_session.commit()

    cuerpo = _disponibles(
        client,
        admin,
        day_of_week=6,
        start_time="08:00",
        end_time="10:00",
        space_type="LABORATORY",
    )

    assert [e["code"] for e in cuerpo["items"]] == ["LAB-99"]


@pytest.mark.integration
def test_la_respuesta_dice_a_que_franja_responde(
    client: TestClient, catalogo: CatalogoDePrueba, admin: dict[str, str]
) -> None:
    # Una lista suelta no dice a qué pregunta contesta, y quien la lee más tarde no puede saber
    # si era el martes de 10 a 12 o el jueves de 14 a 16.
    cuerpo = _disponibles(client, admin, day_of_week=2, start_time="10:00", end_time="12:00")

    assert cuerpo["day_of_week"] == 2
    assert cuerpo["start_time"] == "10:00:00"
    assert cuerpo["total"] == len(cuerpo["items"])


@pytest.mark.integration
def test_una_franja_al_reves_se_rechaza(
    client: TestClient, catalogo: CatalogoDePrueba, admin: dict[str, str]
) -> None:
    """«De 12 a 10» no es una franja vacía, es una pregunta mal hecha.

    Devolver una lista vacía dejaría a quien pregunta creyendo que no hay aulas libres.
    """
    respuesta = client.get(
        RUTA_DISPONIBLES,
        params={"day_of_week": 1, "start_time": "12:00", "end_time": "10:00"},
        headers=admin,
    )

    assert respuesta.status_code == 400, respuesta.text


@pytest.mark.integration
def test_la_disponibilidad_exige_rol_de_administracion(
    client: TestClient, catalogo: CatalogoDePrueba
) -> None:
    assert (
        client.get(
            RUTA_DISPONIBLES, params={"day_of_week": 1, "start_time": "08:00", "end_time": "10:00"}
        ).status_code
        == 401
    )
