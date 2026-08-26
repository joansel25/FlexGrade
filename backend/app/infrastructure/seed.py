"""Carga de datos de ejemplo, idempotente.

    python -m app.infrastructure.seed        (o `make seed`)

Siembra lo que describe `docs/DATA_MODEL.md` sección 4: 3 programas, 10 profesores, 16
materias con sus requisitos, 1 período de matrícula activo, 21 grupos con horario y cupos, y 50
estudiantes de prueba, mas el inventario de 9 espacios fisicos que la iteracion 7.1 convirtio
en entidad.

La materia número 16 y su grupo llegaron con la iteración 6.2: el laboratorio de Física existe
para que haya en la base un par de CORREQUISITOS MUTUOS de verdad. Sin él, el único camino del
validador que quedaría sin poder probarse a mano es justo el que resuelve el bloqueo circular,
que es el más difícil de razonar sobre el papel. Las materias de ese bloque llevan horario
escrito a mano (`HORARIOS_DEL_BLOQUE`) en vez de la rotación general: sin eso el bloque sería
inscribible en teoría e imposible en la práctica, porque la rotación choca antes.

Siembra además **historial académico** para una parte de los estudiantes. No lo pedía el
documento, pero sin él la validación de prerrequisitos de la Fase 3 no se puede probar a mano:
todo el mundo tendría el expediente vacío y `MAT102` sería inaccesible para cualquiera. Con este
reparto hay estudiantes en los dos lados de cada regla, que es lo que hace útil un juego de
datos de ejemplo.

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
from decimal import Decimal
from typing import TypeVar
from uuid import UUID
from uuid import UUID as uuid_type
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.value_objects.requirement_type import RequirementType
from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.academic_history import AcademicHistoryModel
from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.base import Base
from app.infrastructure.persistence.sqlalchemy.models.course import CourseModel
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.enrollment import EnrollmentModel
from app.infrastructure.persistence.sqlalchemy.models.enrollment_period import EnrollmentPeriodModel
from app.infrastructure.persistence.sqlalchemy.models.professor import ProfessorModel
from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
from app.infrastructure.persistence.sqlalchemy.models.program_course import ProgramCourseModel
from app.infrastructure.persistence.sqlalchemy.models.program_course_requirement import (
    ProgramCourseRequirementModel,
)
from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel
from app.infrastructure.persistence.sqlalchemy.models.space import SpaceModel
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

# El historial académico solo se siembra a los estudiantes de INGENIERÍA, porque la cadena
# MAT101 -> MAT102 -> MAT201 pertenece a ese plan de estudios. Dar Cálculo I a alguien de
# Derecho produciría datos que se contradicen: tendría la materia aprobada y aun así no podría
# inscribir Cálculo II, por no estar en su plan.
#
# Los de Ingeniería se reparten en cuatro grupos, para dejar gente en los dos lados de cada
# regla y que probar a mano no exija preparar datos antes:
#
#   1er cuarto  sin historial     -> NO pueden MAT102 (les falta MAT101)
#   2do cuarto  MAT101 aprobada   -> SÍ pueden MAT102, no MAT201
#   3er cuarto  MAT101 y MAT102   -> SÍ pueden MAT201, la cadena completa
#   4to cuarto  MAT101 PERDIDA    -> NO pueden MAT102: comprueba que solo APPROVED habilita
PROGRAMA_CON_CADENA = "ISIS"
PERIODO_HISTORICO = "2025-1"

T = TypeVar("T", bound=Base)


# ---------------------------------------------------------------------------
# Catálogo declarado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MateriaSembrada:
    """Una materia del catálogo, con su lugar en el plan de estudios y lo que exige en él.

    Los requisitos se declaran con el CÓDIGO de la otra materia y no con su identificador
    porque los UUID los genera PostgreSQL: son distintos en cada base y no se pueden escribir
    aquí. El código es la clave natural y se resuelve al sembrar.
    """

    code: str
    name: str
    credits: int
    description: str
    programa: str
    semestre: int
    #: Materia que hay que haber APROBADO antes.
    requiere: str | None = None
    #: Materias que hay que cursar EN EL MISMO período. Es una tupla y no un solo código
    #: porque una materia puede exigir varias a la vez, y porque el correquisito mutuo obliga
    #: a declarar la vuelta: `FIS101` exige `MAT101` y además `FIS102`, que a su vez la exige
    #: a ella.
    junto_a: tuple[str, ...] = ()


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

# 16 materias repartidas entre los tres programas, con una cadena de prerrequisitos en
# Ingeniería (MAT101 -> MAT102 -> MAT201) que permite probar la validación de la Fase 3.
#
# Los correquisitos de la iteración 6.2 cubren los dos casos que se validan distinto:
#
#   FIS101 -> MAT101   correquisito SIMPLE: para ver Física I hay que estar cursando Cálculo I,
#                      o haberlo aprobado ya. MAT101 no exige nada a cambio, así que a quien no
#                      lo tenga aprobado se le pedirá inscribirlo también.
#   FIS101 <-> FIS102  correquisito MUTUO: la teoría y su laboratorio se cursan juntos. Es el
#                      caso que produciría un bloqueo circular si cada una exigiera que la otra
#                      estuviera inscrita ANTES, y el que obliga a validar el bloque entero en
#                      vez de la materia suelta.
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
    MateriaSembrada(
        "FIS101",
        "Física I",
        3,
        "Mecánica clásica",
        "ISIS",
        2,
        junto_a=("MAT101", "FIS102"),
    ),
    MateriaSembrada(
        "FIS102",
        "Laboratorio de Física I",
        1,
        "Prácticas de mecánica",
        "ISIS",
        2,
        junto_a=("FIS101",),
    ),
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

# No toda materia se dicta cada semestre, y el catálogo tiene que poder decirlo. Esta queda sin
# grupo a propósito: es lo que permite comprobar que `GET /courses/{id}/offerings` responde 200
# con una lista vacía —un resultado legítimo— en vez de un 404.
#
# `MAT201` SÍ se ofrece, aunque sea de tercer semestre: es el último eslabón de la cadena
# MAT101 -> MAT102 -> MAT201, y sin grupo no habría forma de probar a mano la validación de
# prerrequisitos en más de un salto.
MATERIAS_SIN_GRUPO = ("RED301",)

# Las materias de primeros semestres, que son las de mayor demanda, tienen dos grupos.
# 15 materias con oferta + 6 grupos adicionales = 21. Eran 20 hasta la iteración 6.2, que
# añadió el laboratorio de Física para poder probar los correquisitos mutuos.
MATERIAS_CON_DOS_GRUPOS = (
    "MAT101",
    "MAT102",
    "PRG101",
    "ADM101",
    "CON101",
    "DER101",
)

# Inventario de espacios (iteracion 7.1). Antes el aula era el texto `f"A-{201 + indice}"`
# generado al vuelo dentro del bucle de grupos: no existia como fila, asi que no se podia
# preguntar que habia reservado en ella ni impedir que dos grupos la ocuparan a la vez.
#
# Se declaran con AFORO, y no por adorno: es el dato contra el que la iteracion 7.2 comprobara
# que un grupo de cuarenta no acabe en un salon de veinticinco. Los aforos van variados a
# proposito, incluido alguno por debajo del cupo de los grupos grandes, para que ese caso se
# pueda probar a mano en vez de tener que fabricarlo.
ESPACIOS: tuple[tuple[str, str, str, int, str], ...] = (
    # codigo, nombre, tipo, aforo, bloque
    ("A-201", "", "CLASSROOM", 45, "A"),
    ("A-202", "", "CLASSROOM", 40, "A"),
    ("A-203", "", "CLASSROOM", 35, "A"),
    ("B-101", "", "CLASSROOM", 50, "B"),
    ("B-102", "", "CLASSROOM", 30, "B"),
    # Mas pequeno que el cupo de los grupos de 40: es el caso que hace util la comprobacion.
    ("B-103", "", "CLASSROOM", 25, "B"),
    ("LAB-01", "Laboratorio de Redes", "LABORATORY", 24, "C"),
    ("LAB-02", "Laboratorio de Fisica", "LABORATORY", 20, "C"),
    ("AUD-01", "Auditorio Principal", "AUDITORIUM", 200, "D"),
)

SEDE = "Sede Principal"

# Horarios base, rotados por grupo para que existan choques reales que la Fase 3 pueda detectar.
FRANJAS: tuple[tuple[int, time, time], ...] = (
    (1, time(6, 0), time(8, 0)),
    (2, time(8, 0), time(10, 0)),
    (3, time(10, 0), time(12, 0)),
    (4, time(14, 0), time(16, 0)),
    (5, time(16, 0), time(18, 0)),
)

# Horarios ESCRITOS A MANO para las materias del bloque de correquisitos.
#
# La rotación de arriba está pensada para producir choques, y con cinco franjas lo consigue
# demasiado bien: cada grupo ocupa las posiciones `i` e `i+2`, y con esa regla NO EXISTEN tres
# grupos compatibles entre sí, se coloquen donde se coloquen las materias en la lista. Da igual
# el orden: es una propiedad de la fórmula, no de los datos.
#
# Eso convertiría los correquisitos en una regla imposible de probar a mano. Para inscribir
# `FIS101` hay que cursar `MAT101` a la vez y además `FIS102`, que son tres materias, y la
# rotación garantiza que al menos dos de las tres se solapen. La persona recibiría un choque de
# horario justo al intentar cumplir el correquisito que el sistema le acaba de exigir.
#
# Estas tres franjas se eligieron para no cruzarse entre sí ni con el grupo 01 de `MAT101`
# —lunes 6-8 y miércoles 10-12, que la rotación le asigna por ser la primera materia—. El grupo
# 02 de `MAT101` sí choca con `FIS101`, y se deja así a propósito: que UNA de las dos
# combinaciones falle es información útil, que fallen las dos sería un dato roto.
HORARIOS_DEL_BLOQUE: dict[str, tuple[tuple[int, time, time], ...]] = {
    "FIS101": ((2, time(8, 0), time(10, 0)), (4, time(14, 0), time(16, 0))),
    "FIS102": ((5, time(16, 0), time(18, 0)),),
}


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


def sembrar(session: Session) -> tuple[dict[str, int], dict[str, list[str]]]:
    """Siembra los datos de ejemplo y devuelve cuántas filas hay de cada tipo.

    Args:
        session: sesión activa. El `commit` lo hace quien llama, para que un test pueda
            revertir todo lo sembrado.

    Returns:
        El recuento por tabla y el reparto del historial académico, para poder informar de lo
        que quedó y de con qué cuenta probar cada regla.
    """
    hasher = JWTAuthService(get_settings())
    password_hash = hasher.hash(PASSWORD_DE_EJEMPLO)

    programas = {
        code: _obtener_o_crear(
            session, ProgramModel, {"code": code}, name=name, total_semesters=semestres
        )
        for code, name, semestres in PROGRAMAS
    }

    # Cada docente con su cuenta: desde la Fase 9 es un actor que entra, no solo un nombre en
    # el catálogo. Se crea la cuenta primero porque `professors.user_id` la apunta.
    profesores = []
    for indice, nombre in enumerate(PROFESORES):
        correo = f"docente{indice + 1:02d}@tdea.edu.co"
        cuenta = _obtener_o_crear(
            session,
            UserModel,
            {"email": correo},
            password_hash=password_hash,
            role="PROFESSOR",
            is_active=True,
        )
        docente = _obtener_o_crear(
            session,
            ProfessorModel,
            {"email": correo},
            full_name=nombre,
            user_id=cuenta.id,
        )

        # `_obtener_o_crear` no toca las filas que ya existen, y los diez docentes se sembraron
        # antes de que tuvieran cuenta. Enlazarlos aquí es lo que hace que un seed repetido
        # sobre una base anterior a la Fase 9 los deje utilizables en vez de sin acceso.
        if docente.user_id is None:
            docente.user_id = cuenta.id

        profesores.append(docente)

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

    # Los requisitos van después de crear TODAS las materias Y TODOS los planes de estudio.
    # Antes bastaba con que las materias existieran; desde la iteración 6.2 la clave foránea es
    # compuesta contra `program_courses`, así que las dos materias tienen que estar ya en el
    # plan o PostgreSQL rechaza la fila. Esa restricción es justamente lo que impide declarar
    # un requisito sobre una materia ajena a la carrera.
    for definicion in MATERIAS:
        programa_id = programas[definicion.programa].id

        if definicion.requiere is not None:
            _sembrar_requisito(
                session,
                program_id=programa_id,
                course_id=materias[definicion.code].id,
                required_course_id=materias[definicion.requiere].id,
                tipo=RequirementType.PREREQUISITE,
            )

        for codigo in definicion.junto_a:
            _sembrar_requisito(
                session,
                program_id=programa_id,
                course_id=materias[definicion.code].id,
                required_course_id=materias[codigo].id,
                tipo=RequirementType.COREQUISITE,
            )

    espacios = _sembrar_espacios(session)
    periodo = _sembrar_periodo(session)
    grupos = _sembrar_grupos(session, periodo, materias, profesores, espacios)
    estudiantes = _sembrar_cuentas(session, programas, password_hash)
    inscripciones = _sembrar_inscripciones(session, periodo, grupos, estudiantes)
    reparto = _sembrar_historial(session, programas, materias)

    return {
        "programas": len(programas),
        "profesores": len(profesores),
        "inscripciones": inscripciones,
        "materias": len(materias),
        "espacios": len(espacios),
        "grupos": len(grupos),
        "estudiantes": session.query(StudentModel).count(),
        "historial": session.query(AcademicHistoryModel).count(),
    }, reparto


def _sembrar_espacios(session: Session) -> list[SpaceModel]:
    """Crea el inventario de espacios fisicos."""
    return [
        _obtener_o_crear(
            session,
            SpaceModel,
            {"code": codigo},
            # El nombre vacio se guarda como NULL: la mayoria de las aulas no se llaman de
            # ninguna manera, solo se numeran, y un nombre en blanco no es lo mismo que no
            # tener nombre.
            name=nombre or None,
            space_type=tipo,
            capacity=aforo,
            campus=SEDE,
            building=bloque,
        )
        for codigo, nombre, tipo, aforo, bloque in ESPACIOS
    ]


def _sembrar_requisito(
    session: Session,
    *,
    program_id: UUID,
    course_id: UUID,
    required_course_id: UUID,
    tipo: RequirementType,
) -> None:
    """Declara un requisito dentro de un plan de estudios, si no estaba ya.

    El tipo NO forma parte de la clave que se busca, igual que no forma parte de la clave
    primaria de la tabla: la misma pareja no puede ser prerrequisito y correquisito a la vez
    sin contradecirse. Buscando solo por la pareja, volver a ejecutar el seed después de
    cambiar un tipo conserva el valor antiguo en vez de fallar por clave duplicada, que es lo
    que promete el resto del script: lo que ya existe no se pisa.
    """
    _obtener_o_crear(
        session,
        ProgramCourseRequirementModel,
        {
            "program_id": program_id,
            "course_id": course_id,
            "required_course_id": required_course_id,
        },
        requirement_type=tipo.value,
    )


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


def _aula_libre(
    ocupacion: dict[tuple[int, time], set[uuid_type]],
    espacios: list[SpaceModel],
    dia: int,
    inicio: time,
) -> uuid_type | None:
    """Devuelve la primera aula libre en ese dia y esa hora, y la marca como ocupada.

    Desde la iteracion 7.2 el reparto NO puede ser una rueda ciega sobre el inventario: la
    restriccion de exclusion de la migracion `0010` rechaza dos franjas que se solapen en el
    mismo espacio, asi que un seed que asignara aulas al azar fallaria al insertar. Se lleva la
    cuenta de lo ya ocupado y se toma la primera libre.

    Devuelve `None` cuando no queda ninguna, en vez de forzar una colision. Una franja sin aula
    es un estado legitimo —el horario se publica antes de repartir espacios— y es preferible a
    un seed que no se puede ejecutar.
    """
    tomadas = ocupacion.setdefault((dia, inicio), set())

    for espacio in espacios:
        if espacio.id not in tomadas:
            tomadas.add(espacio.id)
            return espacio.id

    return None


def _sembrar_grupos(
    session: Session,
    periodo: EnrollmentPeriodModel,
    materias: dict[str, CourseModel],
    profesores: list[ProfessorModel],
    espacios: list[SpaceModel],
) -> list[CourseOfferingModel]:
    """Crea los grupos con su horario y su ocupación inicial."""
    grupos: list[CourseOfferingModel] = []
    indice = 0
    # Que aulas estan tomadas en cada (dia, hora). Ver `_aula_libre`.
    ocupacion: dict[tuple[int, time], set[uuid_type]] = {}

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
            # Las materias del bloque de correquisitos llevan horario propio, porque la
            # rotación no puede dejar tres grupos compatibles entre sí.
            franjas = HORARIOS_DEL_BLOQUE.get(
                definicion.code,
                tuple(FRANJAS[(indice + d) % len(FRANJAS)] for d in (0, 2)),
            )

            for dia, inicio, fin in franjas:
                _obtener_o_crear(
                    session,
                    ScheduleBlockModel,
                    {
                        "course_offering_id": grupo.id,
                        "day_of_week": dia,
                        "start_time": inicio,
                    },
                    end_time=fin,
                    enrollment_period_id=periodo.id,
                    space_id=_aula_libre(ocupacion, espacios, dia, inicio),
                )

            indice += 1

    return grupos


def _sembrar_inscripciones(
    session: Session,
    periodo: EnrollmentPeriodModel,
    grupos: list[CourseOfferingModel],
    estudiantes: list[StudentModel],
) -> int:
    """Crea inscripciones REALES que cuadren con `enrolled_count`.

    Hasta la Fase 9 el seed ponía el contador a mano y no creaba ninguna fila en `enrollments`.
    Los reportes de ocupación cuadraban, pero la lista del docente salía vacía y la
    consolidación no tenía nada que consolidar: se podía cerrar un semestre entero sin escribir
    una sola línea de expediente, y nada avisaba.

    **Solo se inscribe a estudiantes del programa al que pertenece la materia.** Inscribir a
    cualquiera crearía datos que el propio sistema rechaza —`CourseNotInProgramError`— y que
    aparecerían en el expediente de alguien como una materia de otra carrera.

    **La mitad se deja SIN CALIFICAR a propósito.** Es lo que permite probar a mano el rechazo
    del cierre: un seed con todo calificado dejaría ese camino sin ejercitar nunca.

    Returns:
        Cuántas inscripciones quedaron creadas.
    """
    # Qué estudiantes hay en cada programa. La materia pertenece a un plan, así que se cruza por
    # ahí y no por el índice, que mezclaría carreras.
    por_programa: dict[uuid_type, list[StudentModel]] = {}
    for estudiante in estudiantes:
        por_programa.setdefault(estudiante.program_id, []).append(estudiante)

    planes = {(fila.program_id, fila.course_id) for fila in session.query(ProgramCourseModel).all()}
    creadas = 0
    # Quién está ya inscrito en cada MATERIA. Sin esto, alguien acabaría en los dos grupos de
    # Cálculo I: cada grupo elegiría a los primeros candidatos por su cuenta. Es un dato que el
    # propio sistema rechaza al inscribir —no se puede estar en dos grupos de la misma materia—
    # y que al consolidar rompía el `UNIQUE` del historial.
    ya_en_la_materia: dict[uuid_type, set[uuid_type]] = {}

    for indice, grupo in enumerate(grupos):
        inscritos_en_la_materia = ya_en_la_materia.setdefault(grupo.course_id, set())
        candidatos = [
            estudiante
            for programa_id, alumnos in por_programa.items()
            if (programa_id, grupo.course_id) in planes
            for estudiante in alumnos
            if estudiante.id not in inscritos_en_la_materia
        ]

        if not candidatos:
            continue

        # Se inscribe a tantos como diga el contador, hasta donde alcancen los candidatos, y el
        # contador se ajusta a lo que de verdad hay: dejarlo por encima haría que los reportes
        # de ocupación mintieran, que es peor que un número más bajo.
        cuantos = min(grupo.enrolled_count, len(candidatos))
        elegidos = candidatos[:cuantos]

        for posicion, estudiante in enumerate(elegidos):
            # Una de cada dos se queda sin nota, alternando por grupo para que haya grupos
            # completos y grupos a medias.
            califica = (indice + posicion) % 2 == 0
            nota = Decimal("4.10") if (indice + posicion) % 4 == 0 else Decimal("2.70")

            existente = (
                session.query(EnrollmentModel)
                .filter_by(
                    student_id=estudiante.id,
                    course_offering_id=grupo.id,
                    enrollment_period_id=periodo.id,
                )
                .one_or_none()
            )

            if existente is not None:
                creadas += 1
                continue

            session.add(
                EnrollmentModel(
                    id=uuid4(),
                    student_id=estudiante.id,
                    course_offering_id=grupo.id,
                    enrollment_period_id=periodo.id,
                    status="ENROLLED",
                    final_grade=nota if califica else None,
                    graded_at=datetime.now(UTC) if califica else None,
                )
            )
            creadas += 1

        inscritos_en_la_materia.update(e.id for e in elegidos)
        grupo.enrolled_count = cuantos

    session.flush()

    return creadas


def _sembrar_cuentas(
    session: Session, programas: dict[str, ProgramModel], password_hash: str
) -> list[StudentModel]:
    """Crea la cuenta de administración y los 50 estudiantes de prueba.

    Devuelve los estudiantes porque `_sembrar_inscripciones` los necesita: hasta la Fase 9 el
    seed simulaba la ocupación con un contador y sin filas en `enrollments`, y con eso la lista
    del docente salía vacía y la consolidación no tenía nada que consolidar.
    """
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
    estudiantes: list[StudentModel] = []

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

        estudiantes.append(
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
        )

    return estudiantes


def _sembrar_historial(
    session: Session, programas: dict[str, ProgramModel], materias: dict[str, CourseModel]
) -> dict[str, list[str]]:
    """Da expediente académico a los estudiantes de Ingeniería.

    Returns:
        Qué códigos de estudiante quedaron en cada grupo, para poder informarlos al terminar.
        Sin esa lista, probar los prerrequisitos a mano obligaría a consultar la base primero.
    """
    de_ingenieria = list(
        session.execute(
            select(StudentModel)
            .where(StudentModel.program_id == programas[PROGRAMA_CON_CADENA].id)
            .order_by(StudentModel.student_code)
        ).scalars()
    )

    if not de_ingenieria:
        return {}

    # Cuatro grupos de tamaño parecido. `max(1, ...)` evita que un grupo quede vacío si algún
    # día se siembran menos estudiantes.
    tamano = max(1, len(de_ingenieria) // 4)
    cuartos = [
        de_ingenieria[:tamano],
        de_ingenieria[tamano : tamano * 2],
        de_ingenieria[tamano * 2 : tamano * 3],
        de_ingenieria[tamano * 3 :],
    ]

    cursadas_por_cuarto: tuple[list[tuple[str, str, Decimal]], ...] = (
        [],
        [("MAT101", "APPROVED", Decimal("4.10"))],
        [
            ("MAT101", "APPROVED", Decimal("4.30")),
            ("MAT102", "APPROVED", Decimal("3.80")),
        ],
        # Perdida, no aprobada: es lo que comprueba que la validación distingue ambos estados
        # en vez de contar cualquier fila del historial.
        [("MAT101", "FAILED", Decimal("2.40"))],
    )

    reparto: dict[str, list[str]] = {}
    etiquetas = ("sin_historial", "mat101_aprobada", "cadena_completa", "mat101_perdida")

    for etiqueta, estudiantes, cursadas in zip(
        etiquetas, cuartos, cursadas_por_cuarto, strict=True
    ):
        reparto[etiqueta] = [e.student_code for e in estudiantes]

        for estudiante in estudiantes:
            for codigo, estado, nota in cursadas:
                _obtener_o_crear(
                    session,
                    AcademicHistoryModel,
                    {
                        "student_id": estudiante.id,
                        "course_id": materias[codigo].id,
                        "academic_period": PERIODO_HISTORICO,
                    },
                    final_grade=nota,
                    status=estado,
                )

    return reparto


def main() -> None:
    """Punto de entrada del script."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    session = get_session_factory()()
    try:
        recuento, reparto = sembrar(session)
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
    logger.info("  docentes     docente01@tdea.edu.co … docente10@tdea.edu.co")
    logger.info("  estudiante   estudiante01@tdea.edu.co  ... estudiante50@tdea.edu.co")
    logger.info("")
    logger.info("Historial academico (solo Ingenieria), para probar los prerrequisitos:")
    for etiqueta, descripcion in (
        ("sin_historial", "sin historial   -> NO pueden MAT102"),
        ("mat101_aprobada", "MAT101 aprobada -> SI pueden MAT102"),
        ("cadena_completa", "MAT101+MAT102   -> SI pueden MAT201"),
        ("mat101_perdida", "MAT101 PERDIDA  -> NO pueden MAT102"),
    ):
        codigos = reparto.get(etiqueta, [])
        if codigos:
            logger.info("  %-16s %s", ", ".join(codigos[:3]) + "...", descripcion)


if __name__ == "__main__":
    main()
