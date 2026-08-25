"""DTOs del plan de estudios de un programa.

El plan de estudios NO es una lista de materias: es una lista de materias **dentro de un
programa**, y esa distinción es la que justifica que exista este módulo. `suggested_semester` e
`is_mandatory` no son propiedades de la materia —Cálculo I puede ser de primer semestre y
obligatoria en Ingeniería, y de tercero y electiva en Administración— sino de la relación entre
la materia y el programa. Por eso la entidad `Course` no los lleva y aquí sí.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.domain.entities.course import Course
from app.domain.value_objects.course_status import CourseStatus


@dataclass(frozen=True)
class StudyPlanEntryDTO:
    """Una materia dentro del plan de estudios, con el punto en que está el estudiante.

    Attributes:
        course: la materia.
        suggested_semester: semestre en el que el plan sugiere cursarla.
        is_mandatory: si es obligatoria para graduarse o electiva.
        status: aprobada, cursándose, disponible, sin oferta o bloqueada. Se calcula en el
            servidor con los mismos servicios de dominio que deciden si una inscripción se
            acepta: una segunda versión de la regla en el cliente discreparía tarde o temprano.
        missing_prerequisites: qué le falta aprobar. Solo con `BLOCKED`.
        missing_corequisites: qué tendría que cursar a la vez y este período no puede. Solo con
            `BLOCKED`.
        corequisites: qué hay que inscribir junto a esta materia. Va siempre que existan,
            también cuando está disponible: es una instrucción, no un impedimento.
    """

    course: Course
    suggested_semester: int
    is_mandatory: bool
    status: CourseStatus = CourseStatus.NOT_OFFERED
    missing_prerequisites: list[str] = field(default_factory=list)
    missing_corequisites: list[str] = field(default_factory=list)
    corequisites: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StudyPlanDTO:
    """El plan de estudios completo de un programa.

    Va sin paginar a propósito, al contrario que el catálogo. Un plan de estudios tiene decenas
    de materias, no cientos, y su valor está en verse entero: la pregunta que responde es «qué
    me falta para graduarme», y esa no se contesta de veinte en veinte.

    Attributes:
        program_id: identificador del programa. Viaja a la respuesta porque el frontend lo
            necesita para preguntar por los requisitos de una materia: desde la iteración 6.2
            `GET /courses/{id}` los resuelve dentro de un plan, y sin este dato la ficha de la
            materia no podría decir qué exige.
        program_code: código del programa (por ejemplo `ISIS`).
        program_name: nombre del programa.
        total_semesters: duración del programa, para poder mostrar los semestres vacíos.
        entries: las materias del plan, ordenadas por semestre y luego por código.
        total_credits: créditos que suma el plan completo.
        approved_credits: créditos ya aprobados. Es la cifra que responde «cuánto llevo», y se
            suma aquí para que la pantalla no tenga que recorrer la lista ni decidir qué estado
            cuenta como avance.
    """

    program_id: UUID
    program_code: str
    program_name: str
    total_semesters: int
    entries: list[StudyPlanEntryDTO] = field(default_factory=list)
    total_credits: int = 0
    approved_credits: int = 0
