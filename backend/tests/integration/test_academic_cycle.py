"""El ciclo académico completo, de punta a punta (iteración 9.3).

**Es la única prueba que demuestra que el sistema funciona más de un semestre.** Cada iteración
de la Fase 9 se valida sola; ninguna valida la cadena, y la cadena es justamente lo que estaba
roto: `academic_history` solo la escribía el seed, así que en producción habría quedado vacía
para siempre, `find_approved_course_ids` habría devuelto vacío y NADIE habría cumplido ningún
prerrequisito a partir del segundo semestre.

El recorrido es el real: matricular Cálculo I → calificar → cerrar el semestre → comprobar que
ahora sí se puede matricular Cálculo II, que exige la primera como prerrequisito.

Va contra PostgreSQL de verdad y no con dobles porque lo que se comprueba depende de piezas que
un doble no tiene: la transacción del cierre, el `UNIQUE` del historial y el `CHECK` que impide
dejar un período consolidado y activo a la vez.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.professor import ProfessorModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from tests.integration.conftest import CatalogoDePrueba

PASSWORD = "SecurePass123"


def _token(client: TestClient, email: str) -> str:
    respuesta = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert respuesta.status_code == 200, respuesta.text

    return str(respuesta.json()["access_token"])


def _cuenta_admin(db_session: Session) -> str:
    correo = f"admin.ciclo.{uuid4().hex[:8]}@tdea.edu.co"
    hasher = JWTAuthService(get_settings())
    usuario = UserModel(
        id=uuid4(),
        email=correo,
        password_hash=hasher.hash(PASSWORD),
        role="ADMIN",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()
    db_session.add(
        AdministratorModel(
            id=uuid4(), user_id=usuario.id, full_name="Registro", department="Registro"
        )
    )
    db_session.commit()

    return correo


def _cuenta_estudiante(db_session: Session, catalogo: CatalogoDePrueba) -> tuple[str, UUID]:
    """Crea un estudiante del programa de Ingeniería, sin historial académico.

    Sin historial a propósito: es la condición de partida de la prueba —no ha aprobado nada— y
    lo que hace que el paso 2 tenga que fallar.
    """
    correo = f"estudiante.ciclo.{uuid4().hex[:8]}@tdea.edu.co"
    hasher = JWTAuthService(get_settings())
    usuario = UserModel(
        id=uuid4(),
        email=correo,
        password_hash=hasher.hash(PASSWORD),
        role="STUDENT",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()

    estudiante = StudentModel(
        id=uuid4(),
        user_id=usuario.id,
        student_code=f"9{uuid4().int % 1_000_000_000:09d}",
        program_id=catalogo.program_id,
        current_semester=1,
        full_name="Estudiante Del Ciclo",
        enrollment_date=date(2022, 1, 15),
    )
    db_session.add(estudiante)
    db_session.commit()

    return correo, estudiante.id


def _abrir_grupo(client: TestClient, admin: str, course_id, group_number: str, dia: int) -> str:
    """Abre un grupo en el período activo y devuelve su identificador."""
    respuesta = client.post(
        "/api/v1/admin/offerings",
        json={
            "course_id": str(course_id),
            "group_number": group_number,
            "total_capacity": 10,
            "schedule": [
                {"day_of_week": dia, "start_time": "14:00", "end_time": "16:00"},
            ],
        },
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert respuesta.status_code == 201, respuesta.text

    return str(respuesta.json()["id"])


def _da_cuenta_al_docente(db_session: Session, professor_id) -> str:
    """Enlaza una cuenta con el docente que ya dicta los grupos de la fixture."""
    correo = f"docente.ciclo.{uuid4().hex[:8]}@tdea.edu.co"
    hasher = JWTAuthService(get_settings())
    usuario = UserModel(
        id=uuid4(),
        email=correo,
        password_hash=hasher.hash(PASSWORD),
        role="PROFESSOR",
        is_active=True,
    )
    db_session.add(usuario)
    db_session.flush()

    docente = db_session.get(ProfessorModel, professor_id)
    assert docente is not None, "la fixture debería traer un docente"
    docente.user_id = usuario.id
    db_session.commit()

    return correo


@pytest.mark.integration
def test_el_ciclo_completo_desbloquea_el_prerrequisito(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    """Matricular → calificar → cerrar → y solo entonces poder matricular la siguiente.

    El punto de la prueba está en las DOS peticiones a `POST /enrollments` sobre Cálculo II: la
    primera tiene que fallar y la segunda funcionar, y entre las dos no cambia nada más que el
    cierre del semestre.
    """
    admin = _token(client, _cuenta_admin(db_session))
    docente = _token(client, _da_cuenta_al_docente(db_session, catalogo.professor_id))
    correo_estudiante, student_id = _cuenta_estudiante(db_session, catalogo)
    estudiante = _token(client, correo_estudiante)
    cabecera = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

    # --- 1. Matricular Cálculo I -------------------------------------------------
    inscripcion = client.post(
        "/api/v1/enrollments",
        json={"course_offering_id": str(catalogo.offering_grupo_01_id)},
        headers=cabecera(estudiante),
    )
    assert inscripcion.status_code == 201, inscripcion.text

    # --- 2. Cálculo II está bloqueada: no ha aprobado el prerrequisito -----------
    calculo_ii = _abrir_grupo(client, admin, catalogo.calculo_ii_id, "07", 5)
    bloqueada = client.post(
        "/api/v1/enrollments",
        json={"course_offering_id": calculo_ii},
        headers=cabecera(estudiante),
    )
    assert bloqueada.status_code == 409
    assert bloqueada.json()["error"]["code"] == "PREREQUISITES_NOT_MET"

    # --- 3. El docente ve su lista y califica ------------------------------------
    lista = client.get(
        f"/api/v1/professors/me/offerings/{catalogo.offering_grupo_01_id}/roster",
        headers=cabecera(docente),
    )
    assert lista.status_code == 200, lista.text
    assert lista.json()["pending"] == 1

    nota = client.put(
        f"/api/v1/professors/me/offerings/{catalogo.offering_grupo_01_id}" f"/grades/{student_id}",
        json={"final_grade": "4.20"},
        headers=cabecera(docente),
    )
    assert nota.status_code == 204, nota.text

    # --- 4. Cerrar la ventana y consolidar ---------------------------------------
    # Se adelanta la fecha de fin en vez de desactivar el período: es como cierra una ventana en
    # la vida real, y es justo lo que `PERIOD_STILL_OPEN` comprueba.
    db_session.execute(
        text("UPDATE enrollment_periods SET ends_at = :fin WHERE id = :id"),
        {"fin": datetime.now(UTC) - timedelta(days=1), "id": catalogo.period_id},
    )
    db_session.commit()

    cierre = client.post(
        f"/api/v1/admin/enrollment-periods/{catalogo.period_id}/close",
        headers=cabecera(admin),
    )
    assert cierre.status_code == 200, cierre.text
    assert cierre.json()["records"] >= 1
    assert cierre.json()["approved"] >= 1

    # --- 5. El expediente existe y el prerrequisito quedó cumplido ---------------
    aprobadas = db_session.execute(
        text(
            "SELECT course_id FROM academic_history "
            "WHERE student_id = :sid AND status = 'APPROVED'"
        ),
        {"sid": student_id},
    ).scalars()
    assert catalogo.calculo_i_id in set(aprobadas)

    # --- 6. Con el semestre siguiente abierto, Cálculo II ya se puede ------------
    # Es el mismo estudiante y la misma materia que falló en el paso 2. Lo único que cambió es
    # que su expediente ahora existe.
    siguiente = _abrir_periodo_siguiente(client, admin, db_session, catalogo)

    ahora_si = client.post(
        "/api/v1/enrollments",
        json={"course_offering_id": str(siguiente)},
        headers=cabecera(estudiante),
    )
    assert ahora_si.status_code == 201, ahora_si.text


@pytest.mark.integration
def test_un_periodo_consolidado_no_admite_mas_notas(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    """Una vez escrito el expediente, las notas de ese semestre son historia.

    Cambiarlas movería prerrequisitos que ya se usaron para matricular, y alguien podría estar
    cursando ahora mismo una materia que dejaría de poder cursar.
    """
    admin = _token(client, _cuenta_admin(db_session))
    docente = _token(client, _da_cuenta_al_docente(db_session, catalogo.professor_id))
    correo_estudiante, student_id = _cuenta_estudiante(db_session, catalogo)
    estudiante = _token(client, correo_estudiante)
    cabecera = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

    client.post(
        "/api/v1/enrollments",
        json={"course_offering_id": str(catalogo.offering_grupo_01_id)},
        headers=cabecera(estudiante),
    )
    client.put(
        f"/api/v1/professors/me/offerings/{catalogo.offering_grupo_01_id}" f"/grades/{student_id}",
        json={"final_grade": "3.00"},
        headers=cabecera(docente),
    )

    db_session.execute(
        text("UPDATE enrollment_periods SET ends_at = :fin WHERE id = :id"),
        {"fin": datetime.now(UTC) - timedelta(days=1), "id": catalogo.period_id},
    )
    db_session.commit()

    assert (
        client.post(
            f"/api/v1/admin/enrollment-periods/{catalogo.period_id}/close",
            headers=cabecera(admin),
        ).status_code
        == 200
    )

    tarde = client.put(
        f"/api/v1/professors/me/offerings/{catalogo.offering_grupo_01_id}" f"/grades/{student_id}",
        json={"final_grade": "5.00"},
        headers=cabecera(docente),
    )

    assert tarde.status_code == 409
    assert tarde.json()["error"]["code"] == "GRADING_PERIOD_CLOSED"


@pytest.mark.integration
def test_el_cierre_no_escribe_nada_si_falta_una_nota(
    client: TestClient, catalogo: CatalogoDePrueba, db_session: Session
) -> None:
    """La transacción es todo o nada, y ese «nada» es lo que se comprueba aquí.

    Un cierre a medias dejaría estudiantes con medio expediente, y los prerrequisitos se
    cumplirían o no según la materia: el peor fallo posible, porque no se parece a un fallo.
    """
    admin = _token(client, _cuenta_admin(db_session))
    correo_estudiante, student_id = _cuenta_estudiante(db_session, catalogo)
    estudiante = _token(client, correo_estudiante)
    cabecera = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

    client.post(
        "/api/v1/enrollments",
        json={"course_offering_id": str(catalogo.offering_grupo_01_id)},
        headers=cabecera(estudiante),
    )
    db_session.execute(
        text("UPDATE enrollment_periods SET ends_at = :fin WHERE id = :id"),
        {"fin": datetime.now(UTC) - timedelta(days=1), "id": catalogo.period_id},
    )
    db_session.commit()

    rechazo = client.post(
        f"/api/v1/admin/enrollment-periods/{catalogo.period_id}/close",
        headers=cabecera(admin),
    )

    assert rechazo.status_code == 409
    assert rechazo.json()["error"]["code"] == "PERIOD_HAS_UNGRADED_ENROLLMENTS"
    assert rechazo.json()["error"]["details"]["pending"] >= 1

    filas = db_session.execute(
        text("SELECT count(*) FROM academic_history WHERE student_id = :sid"),
        {"sid": student_id},
    ).scalar()
    assert filas == 0

    consolidado = db_session.execute(
        text("SELECT consolidated_at FROM enrollment_periods WHERE id = :id"),
        {"id": catalogo.period_id},
    ).scalar()
    assert consolidado is None


def _abrir_periodo_siguiente(
    client: TestClient, admin: str, db_session: Session, catalogo: CatalogoDePrueba
):
    """Crea la ventana del semestre siguiente con un grupo de Cálculo II, y la activa."""
    cabecera = {"Authorization": f"Bearer {admin}"}
    ahora = datetime.now(UTC)

    creado = client.post(
        "/api/v1/admin/enrollment-periods",
        json={
            "code": f"2026-1-V1-{uuid4().hex[:6]}",
            "academic_period": "2026-1",
            "name": "Matrícula 2026-1",
            "starts_at": (ahora - timedelta(days=1)).isoformat(),
            "ends_at": (ahora + timedelta(days=30)).isoformat(),
        },
        headers=cabecera,
    )
    assert creado.status_code == 201, creado.text
    nuevo = creado.json()["id"]

    activado = client.put(f"/api/v1/admin/enrollment-periods/{nuevo}/activate", headers=cabecera)
    assert activado.status_code == 200, activado.text

    grupo = client.post(
        "/api/v1/admin/offerings",
        json={
            "course_id": str(catalogo.calculo_ii_id),
            "group_number": "09",
            "total_capacity": 10,
            "schedule": [
                {"day_of_week": 3, "start_time": "14:00", "end_time": "16:00"},
            ],
        },
        headers=cabecera,
    )
    assert grupo.status_code == 201, grupo.text

    return grupo.json()["id"]
