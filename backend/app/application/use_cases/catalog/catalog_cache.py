"""Claves y serialización de la caché del catálogo.

Reúne en un solo sitio todo lo que los casos de uso del catálogo necesitan saber sobre cómo se
guardan sus resultados en la caché: cómo se construye cada clave y cómo se convierten las
entidades a texto y de vuelta.

Vive en la capa de aplicación, no en `infrastructure/`, porque los casos de uso lo consumen y
el dominio no puede depender hacia fuera. El puerto `CacheService` solo entiende de cadenas;
qué se mete dentro de esas cadenas se decide aquí.

**La versión en la clave no es decorativa.** Cada clave lleva un `v1`. El día que se añada un
campo a `CourseOffering` o cambie la forma del JSON, subir ese número deja obsoletas todas las
entradas antiguas de golpe. Sin él, durante los segundos de vida del TTL convivirían entradas
con el formato viejo y código que espera el nuevo, y el resultado sería un `KeyError` en
producción imposible de reproducir en local con la caché vacía.
"""

from __future__ import annotations

import json
from datetime import time
from typing import Any
from uuid import UUID

from app.domain.entities.course import Course
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.professor import Professor
from app.domain.entities.space import Space
from app.domain.exceptions.invalid_value import InvalidValueError
from app.domain.value_objects.course_code import CourseCode
from app.domain.value_objects.schedule_block import ScheduleBlock
from app.domain.value_objects.space_type import SpaceType

# v2 desde la iteracion 7.1: el aula dejo de ser un texto dentro de la franja y paso a ser una
# entidad `Space` con codigo, tipo, aforo, sede y bloque. Es exactamente el caso que este numero
# existe para cubrir: sin subirlo, durante los segundos de vida del TTL convivirian entradas con
# el formato viejo y codigo que espera el nuevo.
_VERSION = "v2"


# ---------------------------------------------------------------------------
# Claves
# ---------------------------------------------------------------------------


def clave_materia(course_id: UUID) -> str:
    """Clave de la caché del detalle de una materia."""
    return f"catalog:{_VERSION}:course:{course_id}"


def clave_listado(
    *,
    page: int,
    size: int,
    program_id: UUID | None,
    semester: int | None,
    search: str | None,
) -> str:
    """Clave de la caché de una página del listado de materias.

    Cada combinación de filtros es una entrada distinta, así que la clave los incluye todos.
    Omitir uno solo haría que dos búsquedas diferentes compartieran resultado, que es la forma
    más silenciosa de servir datos equivocados.

    El texto de búsqueda se normaliza igual que en el repositorio —sin espacios extremos y en
    minúsculas— para que `"Cálculo"` y `" cálculo "` no ocupen dos entradas distintas con
    idéntico contenido.
    """
    texto = (search or "").strip().lower()
    return (
        f"catalog:{_VERSION}:courses"
        f":p={page}:s={size}"
        f":prog={program_id or '-'}"
        f":sem={semester if semester is not None else '-'}"
        f":q={texto or '-'}"
    )


def clave_grupo(offering_id: UUID) -> str:
    """Clave de la caché de la parte estática de un grupo.

    Solo la parte estática: `enrolled_count` viaja en el JSON por comodidad de mapeo, pero el
    caso de uso lo sobrescribe siempre con una lectura fresca de PostgreSQL antes de responder.
    """
    return f"catalog:{_VERSION}:offering:{offering_id}"


# ---------------------------------------------------------------------------
# Serialización
# ---------------------------------------------------------------------------


def materia_a_json(course: Course) -> str:
    """Serializa una materia."""
    return json.dumps(_materia_a_dict(course))


def materia_desde_json(payload: str) -> Course | None:
    """Reconstruye una materia. Devuelve `None` si la entrada no es utilizable."""
    datos = _cargar(payload)

    if datos is None:
        return None

    try:
        return _materia_desde_dict(datos)
    except (KeyError, TypeError, ValueError, InvalidValueError):
        return None


def materias_a_json(courses: list[Course], total: int) -> str:
    """Serializa una página del listado junto con su total."""
    return json.dumps({"total": total, "items": [_materia_a_dict(c) for c in courses]})


def materias_desde_json(payload: str) -> tuple[list[Course], int] | None:
    """Reconstruye una página del listado. Devuelve `None` si la entrada no es utilizable."""
    datos = _cargar(payload)

    if datos is None:
        return None

    try:
        materias = [_materia_desde_dict(item) for item in datos["items"]]
        return materias, int(datos["total"])
    except (KeyError, TypeError, ValueError, InvalidValueError):
        return None


def grupo_a_json(offering: CourseOffering) -> str:
    """Serializa un grupo con su docente y su horario."""
    return json.dumps(
        {
            "id": str(offering.id),
            "enrollment_period_id": str(offering.enrollment_period_id),
            "course_id": str(offering.course_id),
            "group_number": offering.group_number,
            "total_capacity": offering.total_capacity,
            "enrolled_count": offering.enrolled_count,
            "version": offering.version,
            "professor": (
                None
                if offering.professor is None
                else {
                    "id": str(offering.professor.id),
                    "full_name": offering.professor.full_name,
                    "email": offering.professor.email,
                }
            ),
            "schedule": [
                {
                    "day_of_week": f.day_of_week,
                    "start_time": f.start_time.isoformat(),
                    "end_time": f.end_time.isoformat(),
                    "space": (
                        None
                        if f.space is None
                        else {
                            "id": str(f.space.id),
                            "code": f.space.code,
                            "name": f.space.name,
                            "space_type": f.space.space_type.value,
                            "capacity": f.space.capacity,
                            "campus": f.space.campus,
                            "building": f.space.building,
                        }
                    ),
                }
                for f in offering.schedule
            ],
        }
    )


def grupo_desde_json(payload: str) -> CourseOffering | None:
    """Reconstruye un grupo. Devuelve `None` si la entrada no es utilizable."""
    datos = _cargar(payload)

    if datos is None:
        return None

    try:
        docente = datos["professor"]

        return CourseOffering(
            id=UUID(datos["id"]),
            enrollment_period_id=UUID(datos["enrollment_period_id"]),
            course_id=UUID(datos["course_id"]),
            group_number=datos["group_number"],
            total_capacity=int(datos["total_capacity"]),
            enrolled_count=int(datos["enrolled_count"]),
            version=int(datos["version"]),
            professor=(
                None
                if docente is None
                else Professor(
                    id=UUID(docente["id"]),
                    full_name=docente["full_name"],
                    email=docente["email"],
                )
            ),
            schedule=tuple(
                ScheduleBlock(
                    day_of_week=int(f["day_of_week"]),
                    start_time=time.fromisoformat(f["start_time"]),
                    end_time=time.fromisoformat(f["end_time"]),
                    space=_espacio_desde_json(f["space"]),
                )
                for f in datos["schedule"]
            ),
        )
    except (KeyError, TypeError, ValueError, InvalidValueError):
        return None


# ---------------------------------------------------------------------------
# Interno
# ---------------------------------------------------------------------------


def _espacio_desde_json(datos: dict[str, Any] | None) -> Space | None:
    """Reconstruye el espacio de una franja, o `None` si no tenía aula asignada.

    Se guarda el espacio ENTERO y no solo su código. Con el código habría que inventar un
    identificador al reconstruirlo, y una entidad con identidad falsa es peor que no tenerla:
    parece utilizable y no lo es. Guardar los siete campos cuesta unos bytes en una entrada que
    vive treinta segundos.
    """
    if datos is None:
        return None

    return Space(
        id=UUID(datos["id"]),
        code=datos["code"],
        name=datos["name"],
        space_type=SpaceType(datos["space_type"]),
        capacity=datos["capacity"],
        campus=datos["campus"],
        building=datos["building"],
    )


def _cargar(payload: str) -> dict[str, Any] | None:
    """Interpreta el JSON de una entrada de caché.

    Una entrada ilegible se trata como si no existiera, igual que un fallo de conexión: la
    caché es una optimización y jamás debe hacer fallar la petición. Puede pasar si alguien
    escribe a mano en Redis, si una versión anterior dejó un formato distinto, o si la entrada
    llegó truncada.
    """
    try:
        datos = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None

    return datos if isinstance(datos, dict) else None


def _materia_a_dict(course: Course) -> dict[str, Any]:
    return {
        "id": str(course.id),
        "code": course.code.value,
        "name": course.name,
        "credits": course.credits,
        "description": course.description,
    }


def _materia_desde_dict(datos: dict[str, Any]) -> Course:
    return Course(
        id=UUID(datos["id"]),
        code=CourseCode(datos["code"]),
        name=datos["name"],
        credits=int(datos["credits"]),
        description=datos["description"],
    )
