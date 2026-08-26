"""Schemas de los endpoints de administración académica.

Siguen los ejemplos de `API.md` sección 6.
"""

from __future__ import annotations

from datetime import datetime
from datetime import time as _time
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.value_objects.requirement_type import RequirementType
from app.domain.value_objects.space_type import SpaceType


class CreateEnrollmentPeriodSchema(BaseModel):
    """Cuerpo de `POST /admin/enrollment-periods`.

    No incluye `is_active`: una ventana nace siempre cerrada y se abre con el endpoint de
    activación. Aceptarlo aquí permitiría crear una ventana ya abierta saltándose la
    desactivación de la anterior, que es lo que hace atómico el cambio de semestre.
    """

    code: str = Field(
        min_length=1,
        max_length=20,
        description="Código único de la ventana",
        examples=["2026-1-V1"],
    )
    academic_period: str = Field(
        min_length=1,
        max_length=20,
        description="Semestre al que pertenece",
        examples=["2026-1"],
    )
    name: str = Field(
        min_length=1,
        max_length=150,
        description="Nombre legible para el estudiante",
        examples=["Matrícula 2026-1 primera vuelta"],
    )
    starts_at: datetime = Field(description="Instante de apertura, en UTC")
    ends_at: datetime = Field(description="Instante de cierre, en UTC")


class EnrollmentPeriodSchema(BaseModel):
    """Una ventana de matrícula tal como la ve la administración."""

    id: UUID
    code: str
    academic_period: str
    name: str
    starts_at: datetime
    ends_at: datetime
    is_active: bool


class CreateCourseSchema(BaseModel):
    """Cuerpo de `POST /admin/courses`.

    El formato del código no se valida aquí sino en el value object `CourseCode`: la regla es
    del dominio, y duplicarla en el schema haría que dos sitios tuvieran que cambiarse a la vez
    el día que la institución la cambie.
    """

    code: str = Field(
        min_length=1,
        max_length=20,
        description="Código institucional de la materia",
        examples=["MAT101"],
    )
    name: str = Field(min_length=1, max_length=150, examples=["Cálculo I"])
    credits: int = Field(gt=0, description="Créditos académicos que otorga", examples=[4])
    description: str | None = Field(default=None, description="Descripción del contenido")


class CreateOfferingSchema(BaseModel):
    """Cuerpo de `POST /admin/offerings`.

    No incluye el período: el grupo se abre siempre en la ventana activa. Tampoco incluye
    `enrolled_count`, que nace en cero y solo lo mueve la inscripción.
    """

    course_id: UUID = Field(description="Materia que se dicta")
    professor_id: UUID | None = Field(default=None, description="Docente asignado, si ya se conoce")
    group_number: str = Field(
        min_length=1,
        max_length=10,
        description="Número de grupo dentro de la materia",
        examples=["02"],
    )
    total_capacity: int = Field(gt=0, description="Cupos totales del grupo", examples=[40])
    schedule: list[NewScheduleBlockSchema] = Field(
        default_factory=list, description="Franjas semanales en las que se dicta"
    )


class SpaceSchema(BaseModel):
    """Un espacio físico del inventario.

    `capacity` puede venir en `null`, y no es un hueco que rellenar: los espacios que nacieron
    del traslado de textos de la iteración 7.1 no traían aforo, y una capacidad inventada es
    peor que una ausente porque nadie vuelve a revisarla. Quien consulta la disponibilidad ve
    el `null` y decide.
    """

    id: UUID
    code: str
    name: str | None = None
    space_type: str
    capacity: int | None = None
    campus: str | None = None
    building: str | None = None


class AvailableSpacesSchema(BaseModel):
    """Respuesta de `GET /admin/spaces/available`.

    Devuelve la franja consultada además de los espacios. Sin ella, una lista suelta no dice a
    qué pregunta responde, y quien la lee más tarde —o la copia a un informe— no puede saber si
    era el martes de 10 a 12 o el jueves de 14 a 16.
    """

    day_of_week: int
    start_time: _time
    end_time: _time
    items: list[SpaceSchema] = Field(default_factory=list)
    total: int


class CreateSpaceSchema(BaseModel):
    """Cuerpo de `POST /admin/spaces`.

    `capacity` es opcional a propósito, y no un campo que se olvidó marcar obligatorio: un aula
    cuyo aforo nadie ha medido es un dato legítimo. Forzar un número inventaría la cifra contra
    la que la iteración 7.2 valida que un grupo quepa, y esos números no los revisa nadie.
    """

    code: str = Field(
        min_length=1,
        max_length=20,
        description="Código institucional. Se guarda en mayúsculas y sin espacios",
        examples=["A-201"],
    )
    space_type: SpaceType = Field(description="Aula, laboratorio o auditorio")
    name: str | None = Field(default=None, max_length=150, examples=["Laboratorio de Redes"])
    capacity: int | None = Field(
        default=None, gt=0, description="Aforo. Puede quedar sin registrar"
    )
    campus: str | None = Field(default=None, max_length=100, examples=["Sede Principal"])
    building: str | None = Field(default=None, max_length=50, examples=["A"])


class SpacesSchema(BaseModel):
    """Respuesta de `GET /admin/spaces`.

    Sin paginar, al contrario que el catálogo de materias: una institución tiene decenas o pocos
    cientos de espacios, no miles, y quien va a asignar un aula necesita verlos todos.
    """

    items: list[SpaceSchema] = Field(default_factory=list)
    total: int


class ProgramSchema(BaseModel):
    """Un programa académico."""

    id: UUID
    code: str
    name: str
    total_semesters: int


class ProgramsSchema(BaseModel):
    """Respuesta de `GET /admin/programs`."""

    items: list[ProgramSchema] = Field(default_factory=list)
    total: int


class SetPlanCourseSchema(BaseModel):
    """Cuerpo de `PUT /admin/programs/{id}/plan/{course_id}`.

    Es un `PUT` y no un `POST` porque la operación es idempotente: deja la materia en el plan
    con esos datos, esté o no. La clave de `program_courses` es la pareja `(programa, materia)`,
    así que no hay diferencia entre añadir y editar que quien administra tenga que conocer de
    antemano.
    """

    suggested_semester: int = Field(
        ge=1, description="Semestre en que el plan la sugiere", examples=[1]
    )
    is_mandatory: bool = Field(default=True, description="Obligatoria para graduarse, o electiva")


class PlanRequirementSchema(BaseModel):
    """Un requisito tal como lo ve quien edita el plan.

    Lleva el código y el nombre además del identificador porque la pantalla los muestra, y
    pedirlos aparte obligaría a la interfaz a cruzar dos listas para pintar una línea de texto.
    """

    course_id: UUID
    code: str
    name: str
    requirement_type: str


class ProgramPlanEntrySchema(BaseModel):
    """Una materia del plan, vista desde administración.

    NO lleva los campos del semáforo —`status`, `missing_prerequisites`, `missing_corequisites`—
    aunque el DTO los tenga. Aquí no hay persona sobre la que calcularlos, así que saldrían
    siempre con su valor por defecto, y `status: "NOT_OFFERED"` en todas las materias se lee
    como un hecho sobre la oferta cuando en realidad solo significa «no se calculó». Un dato que
    miente es peor que un dato ausente.

    Lleva en cambio `requirements`, que el plan del estudiante no necesita y esta pantalla sí:
    es justo lo que se está editando.
    """

    id: UUID
    code: str
    name: str
    credits: int
    suggested_semester: int
    is_mandatory: bool
    requirements: list[PlanRequirementSchema] = Field(default_factory=list)


class ProgramPlanSchema(BaseModel):
    """Respuesta de `GET /admin/programs/{id}/plan`."""

    program_id: UUID
    program_code: str
    program_name: str
    total_semesters: int
    total_credits: int
    courses: list[ProgramPlanEntrySchema] = Field(default_factory=list)


class SetRequirementSchema(BaseModel):
    """Cuerpo de `PUT /admin/programs/{id}/plan/{course_id}/requirements/{required_id}`.

    Solo lleva el tipo. Las tres materias implicadas —el programa, la que exige y la exigida—
    van en la ruta, porque son las que identifican el requisito: la clave de
    `program_course_requirements` es esa terna, y el tipo es el único dato editable.
    """

    requirement_type: RequirementType = Field(
        description="PREREQUISITE (aprobada antes) o COREQUISITE (cursada a la vez)"
    )


class NewScheduleBlockSchema(BaseModel):
    """Una franja al ABRIR un grupo.

    Se declara aquí y no se reutiliza el `ScheduleBlockSchema` del catálogo, aunque hasta la
    iteración 7.1 fuera el mismo objeto para las dos cosas. Dejaron de coincidir en cuanto el
    aula pasó a ser una entidad: la salida lleva el NOMBRE del espacio (`classroom`) porque
    quien lee un horario quiere leerlo, y la entrada lleva su CÓDIGO (`space_code`) porque hay
    que buscarlo en el inventario y fallar si no existe. Compartir un schema entre lo que se
    recibe y lo que se devuelve funciona solo mientras son casualmente iguales.

    Attributes:
        day_of_week: día de la semana, de 1 (lunes) a 7 (domingo).
        start_time: hora de inicio.
        end_time: hora de fin.
        space_code: código del aula. Opcional: el horario se publica antes de repartir los
            espacios, así que una franja sin aula es un estado normal y no un dato incompleto.
    """

    day_of_week: int = Field(ge=1, le=7, description="1 = lunes … 7 = domingo (ISO 8601)")
    start_time: _time
    end_time: _time
    space_code: str | None = Field(
        default=None,
        max_length=20,
        description="Código del aula en el inventario de espacios",
        examples=["A-201"],
    )


class UpdateCapacitySchema(BaseModel):
    """Cuerpo de `PUT /admin/offerings/{id}/capacity`.

    `gt=0` lo impone también el `CHECK (total_capacity > 0)` de PostgreSQL. Declararlo aquí
    convierte un 500 por violación de restricción en un 422 con el campo señalado.
    """

    total_capacity: int = Field(gt=0, description="Cupo total que debe quedar", examples=[45])
