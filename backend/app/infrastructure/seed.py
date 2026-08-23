"""Carga de datos de ejemplo, idempotente.

    python -m app.infrastructure.seed        (o `make seed`)

Siembra lo que describe `docs/DATA_MODEL.md` sección 4: 3 programas, 10 profesores, 15
materias con sus prerrequisitos, 1 período de matrícula activo, 20 grupos con horario y cupos,
y 50 estudiantes de prueba.

**Idempotente de verdad, no "casi".** Cada fila se busca por su clave natural —el `code` de un
programa, el `student_code` de un estudiante— y solo se inserta si falta. Ejecutarlo diez
veces seguidas deja exactamente el mismo resultado que ejecutarlo una, y no lanza ningún error
por clave duplicada. Eso permite usarlo como paso rutinario tras levantar el entorno sin tener
que acordarse de si ya estaba sembrado.

Lo que ya existe **no se pisa**: si estabas probando algo y cambiaste el cupo de un grupo a
mano, volver a ejecutar el seed no lo revierte. La forma de partir de cero es `make clean`.

Vive en `infrastructure/` porque escribe directamente con los modelos ORM. No es un caso de
uso: no representa ninguna operación del negocio, es una herramienta de desarrollo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.base import Base
from app.infrastructure.persistence.sqlalchemy.models.course import CourseModel
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.course_prerequisite import (
    CoursePrerequisiteModel,
)
from app.infrastructure.persistence.sqlalchemy.models.enrollment_period import EnrollmentPeriodModel
from app.infrastructure.persistence.sqlalchemy.models.professor import ProfessorModel
from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
from app.infrastructure.persistence.sqlalchemy.models.program_course import ProgramCourseModel
from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from app.infrastructure.persistence.sqlalchemy.session import get_session_factory

logger = logging.getLogger(__name__)

# Contraseña común de todas las cuentas sembradas. Es de desarrollo y por eso está a la vista:
# la base que alimenta este script no está expuesta a internet y sus datos son inventados.
# En DEV, STAGING y PROD el seed no se ejecuta (CI_CD.md); las cuentas reales se crean por los
# endpoints de administración.
PASSWORD_DE_EJEMPLO = "SecurePass123"

CORREO_ADMIN = "admin@tdea.edu.co"

T = TypeVar("T", bound=Base)


# ---------------------------------------------------------------------------
# Catálogo declarado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MateriaSembrada:
    """Una materia del catálogo, con su lugar en el plan de estudios."""

    code: str
    name: str
    credits: int
    description: str
    programa: str
    semestre: int
    requiere: str | None = None


PROGRAMAS: tuple[tuple[str, str, int], ...] = (
    ("ISIS", "Ingeniería de Sistemas", 10),
    ("ADMI", "Administración de Empresas", 8),
    ("DERE", "Derecho", 10),
)

PROFESORES: tuple[str, ...] = (
    "Ana Pérez Gómez",
    "Carlos Ramírez Soto",
    "Diana Muñoz Vélez",
    "Eduardo Sánchez Rojas",
    "Fernanda Ospina Cano",
    "Gabriel Torres Mejía",
    "Helena Ruiz Duque",
    "Iván Castaño Ríos",
    "Julia Ortega Bedoya",
    "Kevin Álvarez Pineda",
)

# 15 materias repartidas entre los tres programas, con una cadena de prerrequisitos en
# Ingeniería (MAT101 -> MAT102 -> MAT201) que permite probar la validación de la Fase 3.
MATERIAS: tuple[MateriaSembrada, ...] = (
    MateriaSembrada("MAT101", "Cálculo I", 4, "Cálculo diferencial de una variable", "ISIS", 1),
    MateriaSembrada(
        "MAT102", "Cálculo II", 4, "Cálculo integral y series", "ISIS", 2, requiere="MAT101"
    ),
    MateriaSembrada(
        "MAT201",
        "Ecuaciones Diferenciales",
        4,
        "Ecuaciones de primer y segundo orden",
        "ISIS",
        3,
        requiere="MAT102",
    ),
    MateriaSembrada("PRG101", "Programación I", 4, "Fundamentos de programación", "ISIS", 1),
    MateriaSembrada(
        "PRG102", "Programación II", 4, "Estructuras de datos", "ISIS", 2, requiere="PRG101"
    ),
    MateriaSembrada(
        "BDD201", "Bases de Datos", 3, "Modelo relacional y SQL", "ISIS", 3, requiere="PRG102"
    ),
    MateriaSembrada("RED301", "Redes de Computadores", 3, "Modelo OSI y TCP/IP", "ISIS", 4),
    MateriaSembrada("FIS101", "Física I", 3, "Mecánica clásica", "ISIS", 2),
    MateriaSembrada(
        "ADM101", "Fundamentos de Administración", 3, "Teoría administrativa", "ADMI", 1
    ),
    MateriaSembrada("CON101", "Contabilidad General", 3, "Partida doble y estados", "ADMI", 1),
    MateriaSembrada(
        "FIN201",
        "Finanzas Corporativas",
        4,
        "Valoración y presupuesto",
        "ADMI",
        3,
        requiere="CON101",
    ),
    MateriaSembrada("MER201", "Mercadeo", 3, "Estrategia y segmentación", "ADMI", 2),
    MateriaSembrada(
        "DER101", "Introducción al Derecho", 4, "Teoría general del derecho", "DERE", 1
    ),
    MateriaSembrada("DER102", "Derecho Constitucional", 4, "Constitución y derechos", "DERE", 2),
    MateriaSembrada(
        "DER201",
        "Derecho Civil",
        4,
        "Personas, bienes y obligaciones",
        "DERE",
        3,
        requiere="DER101",
    ),
)

# No toda materia se dicta cada semestre, y el catálogo tiene que poder decirlo. Estas dos
# quedan sin grupo a propósito: es lo que permite comprobar que `GET /courses/{id}/offerings`
# responde 200 con una lista vacía —un resultado legítimo— en vez de un 404.
MATERIAS_SIN_GRUPO = ("MAT201", "RED301")

# Las materias de primeros semestres, que son las de mayor demanda, tienen dos grupos.
# 13 materias con oferta + 7 grupos adicionales = los 20 que fija DATA_MODEL.md.
MATERIAS_CON_DOS_GRUPOS = (
    "MAT101",
    "MAT102",
    "PRG101",
    "PRG102",
    "ADM101",
    "CON101",
    "DER101",
)

# Horarios base, rotados por grupo para que existan choques reales que la Fase 3 pueda detectar.
FRANJAS: tuple[tuple[int, time, time], ...] = (
    (1, time(6, 0), time(8, 0)),
    (2, time(8, 0), time(10, 0)),
    (3, time(10, 0), time(12, 0)),
    (4, time(14, 0), time(16, 0)),
    (5, time(16, 0), time(18, 0)),
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _obtener_o_crear(
    session: Session, modelo: type[T], filtro: dict[str, object], **datos: object
) -> T:
    """Devuelve la fila que cumple `filtro`, creándola con `datos` si no existe.

    Es la pieza que hace idempotente al seed. La búsqueda se hace por la clave natural —el
    código, el correo— y nunca por el identificador, porque los UUID los genera PostgreSQL y
    serían distintos en cada ejecución.

    Args:
        session: sesión activa.
        modelo: clase ORM sobre la que buscar.
        filtro: condiciones que identifican la fila de forma única.
        **datos: columnas con las que crearla si falta.

    Returns:
        La fila existente o la recién creada.
    """
    sentencia = select(modelo).filter_by(**filtro)
    existente = session.execute(sentencia).scalar_one_or_none()

    if existente is not None:
        return existente

    nueva = modelo(**filtro, **datos)
    session.add(nueva)
    session.flush()
    return nueva


# ---------------------------------------------------------------------------
# Siembra
# ---------------------------------------------------------------------------


def sembrar(session: Session) -> dict[str, int]:
    """Siembra los datos de ejemplo y devuelve cuántas filas hay de cada tipo.

    Args:
        session: sesión activa. El `commit` lo hace quien llama, para que un test pueda
            revertir todo lo sembrado.

    Returns:
        El recuento por tabla, para poder informar de lo que quedó.
    """
    hasher = JWTAuthService(get_settings())
    password_hash = hasher.hash(PASSWORD_DE_EJEMPLO)

    programas = {
        code: _obtener_o_crear(
            session, ProgramModel, {"code": code}, name=name, total_semesters=semestres
        )
        for code, name, semestres in PROGRAMAS
    }

    profesores = [
        _obtener_o_crear(
            session,
            ProfessorModel,
            {"email": f"docente{indice + 1:02d}@tdea.edu.co"},
            full_name=nombre,
        )
        for indice, nombre in enumerate(PROFESORES)
    ]

    materias = {}
    for definicion in MATERIAS:
        materia = _obtener_o_crear(
            session,
            CourseModel,
            {"code": definicion.code},
            name=definicion.name,
            credits=definicion.credits,
            description=definicion.description,
        )
        materias[definicion.code] = materia

        _obtener_o_crear(
            session,
            ProgramCourseModel,
            {"program_id": programas[definicion.programa].id, "course_id": materia.id},
            suggested_semester=definicion.semestre,
            is_mandatory=True,
        )

    # Los prerrequisitos van después de crear TODAS las materias: una materia no puede exigir
    # otra que aún no existe.
    for definicion in MATERIAS:
        if definicion.requiere is not None:
            _obtener_o_crear(
                session,
                CoursePrerequisiteModel,
                {
                    "course_id": materias[definicion.code].id,
                    "required_course_id": materias[definicion.requiere].id,
                },
            )

    periodo = _sembrar_periodo(session)
    grupos = _sembrar_grupos(session, periodo, materias, profesores)
    _sembrar_cuentas(session, programas, password_hash)

    return {
        "programas": len(programas),
        "profesores": len(profesores),
        "materias": len(materias),
        "grupos": len(grupos),
        "estudiantes": session.query(StudentModel).count(),
    }


def _sembrar_periodo(session: Session) -> EnrollmentPeriodModel:
    """Crea la ventana de matrícula activa, abierta ahora mismo.

    Las fechas se calculan alrededor del instante actual para que el período esté abierto
    cuando pruebes, en vez de fijar una fecha de 2025 que quedaría en el pasado.

    El índice único parcial impide que haya dos períodos activos, así que si ya existe uno
    —aunque sea otro— se reutiliza en vez de intentar crear un segundo.
    """
    activo = session.execute(
        select(EnrollmentPeriodModel).where(EnrollmentPeriodModel.is_active.is_(True))
    ).scalar_one_or_none()

    if activo is not None:
        return activo

    ahora = datetime.now(UTC)
    return _obtener_o_crear(
        session,
        EnrollmentPeriodModel,
        {"code": "2025-2-V1"},
        academic_period="2025-2",
        name="Matrícula 2025-2 primera vuelta",
        starts_at=ahora - timedelta(days=1),
        ends_at=ahora + timedelta(days=30),
        is_active=True,
    )


def _sembrar_grupos(
    session: Session,
    periodo: EnrollmentPeriodModel,
    materias: dict[str, CourseModel],
    profesores: list[ProfessorModel],
) -> list[CourseOfferingModel]:
    """Crea los grupos con su horario y su ocupación inicial."""
    grupos: list[CourseOfferingModel] = []
    indice = 0

    for definicion in MATERIAS:
        if definicion.code in MATERIAS_SIN_GRUPO:
            continue

        cuantos = 2 if definicion.code in MATERIAS_CON_DOS_GRUPOS else 1

        for numero in range(1, cuantos + 1):
            materia = materias[definicion.code]
            capacidad = 40 if numero == 1 else 30
            # Ocupación variada y determinista, para que el catálogo muestre grupos con
            # holgura, casi llenos y llenos del todo sin depender del azar.
            ocupados = min(capacidad, (indice * 7) % (capacidad + 5))

            grupo = _obtener_o_crear(
                session,
                CourseOfferingModel,
                {
                    "enrollment_period_id": periodo.id,
                    "course_id": materia.id,
                    "group_number": f"{numero:02d}",
                },
                professor_id=profesores[indice % len(profesores)].id,
                total_capacity=capacidad,
                enrolled_count=ocupados,
            )
            grupos.append(grupo)

            # Dos franjas por grupo, en días distintos, rotando para generar solapamientos.
            for desplazamiento in (0, 2):
                dia, inicio, fin = FRANJAS[(indice + desplazamiento) % len(FRANJAS)]
                _obtener_o_crear(
                    session,
                    ScheduleBlockModel,
                    {
                        "course_offering_id": grupo.id,
                        "day_of_week": dia,
                        "start_time": inicio,
                    },
                    end_time=fin,
                    classroom=f"{chr(65 + indice % 4)}-{201 + indice % 15}",
                )

            indice += 1

    return grupos


def _sembrar_cuentas(
    session: Session, programas: dict[str, ProgramModel], password_hash: str
) -> None:
    """Crea la cuenta de administración y los 50 estudiantes de prueba."""
    admin = _obtener_o_crear(
        session,
        UserModel,
        {"email": CORREO_ADMIN},
        password_hash=password_hash,
        role="ADMIN",
        is_active=True,
    )
    _obtener_o_crear(
        session,
        AdministratorModel,
        {"user_id": admin.id},
        full_name="Administración Académica",
        department="Registro y Control",
    )

    codigos_de_programa = [code for code, _, _ in PROGRAMAS]

    for numero in range(1, 51):
        codigo = f"20250{numero:04d}"
        correo = f"estudiante{numero:02d}@tdea.edu.co"

        cuenta = _obtener_o_crear(
            session,
            UserModel,
            {"email": correo},
            password_hash=password_hash,
            role="STUDENT",
            is_active=True,
        )

        programa = programas[codigos_de_programa[(numero - 1) % len(codigos_de_programa)]]

        _obtener_o_crear(
            session,
            StudentModel,
            {"student_code": codigo},
            user_id=cuenta.id,
            program_id=programa.id,
            current_semester=(numero % 8) + 1,
            full_name=f"Estudiante De Prueba {numero:02d}",
            enrollment_date=date(2022, 1, 15),
        )


def main() -> None:
    """Punto de entrada del script."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    session = get_session_factory()()
    try:
        recuento = sembrar(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    logger.info("Datos de ejemplo listos:")
    for etiqueta, cuantos in recuento.items():
        logger.info("  %-12s %3d", etiqueta, cuantos)
    logger.info("")
    logger.info("Cuentas de prueba (contrasena: %s):", PASSWORD_DE_EJEMPLO)
    logger.info("  admin        %s", CORREO_ADMIN)
    logger.info("  estudiante   estudiante01@tdea.edu.co  ... estudiante50@tdea.edu.co")


if __name__ == "__main__":
    main()
