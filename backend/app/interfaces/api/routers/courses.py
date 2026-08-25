"""Router del catálogo de materias.

Los handlers son delgados: traducen los parámetros de la petición, invocan el caso de uso y
mapean el resultado al schema. Ni una regla de negocio, ni una consulta, ni una decisión sobre
la caché viven aquí.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.application.dtos.catalog_dto import CourseOfferingsDTO
from app.application.dtos.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.domain.entities.course import Course
from app.domain.entities.course_offering import CourseOffering
from app.interfaces.api.dependencies.di import (
    GetCourseDetailUseCaseDep,
    GetCourseOfferingsUseCaseDep,
    ListCoursesUseCaseDep,
)
from app.interfaces.api.schemas.catalog_schemas import (
    CourseDetailSchema,
    CourseOfferingsSchema,
    CourseSchema,
    OfferingSchema,
    PageSchema,
    ScheduleBlockSchema,
)
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema

router = APIRouter(prefix="/courses", tags=["catalogo"])


def a_schema_de_materia(course: Course) -> CourseSchema:
    """Traduce la entidad `Course` a su representación pública."""
    return CourseSchema(
        id=course.id,
        code=course.code.value,
        name=course.name,
        credits=course.credits,
        description=course.description,
    )


def a_schema_de_grupo(offering: CourseOffering) -> OfferingSchema:
    """Traduce la entidad `CourseOffering` a su representación pública."""
    return OfferingSchema(
        id=offering.id,
        group_number=offering.group_number,
        professor=offering.professor.full_name if offering.professor is not None else None,
        total_capacity=offering.total_capacity,
        enrolled_count=offering.enrolled_count,
        available_slots=offering.available_slots(),
        schedule=[
            ScheduleBlockSchema(
                day_of_week=f.day_of_week,
                start_time=f.start_time,
                end_time=f.end_time,
                classroom=f.classroom,
            )
            for f in offering.schedule
        ],
    )


@router.get(
    "",
    response_model=PageSchema[CourseSchema],
    status_code=status.HTTP_200_OK,
    summary="Listar materias del catálogo",
)
def list_courses(
    use_case: ListCoursesUseCaseDep,
    page: Annotated[int, Query(ge=1, description="Número de página")] = 1,
    size: Annotated[
        int, Query(ge=1, le=MAX_PAGE_SIZE, description="Materias por página")
    ] = DEFAULT_PAGE_SIZE,
    program_id: Annotated[UUID | None, Query(description="Filtra por programa")] = None,
    semester: Annotated[int | None, Query(ge=1, description="Filtra por semestre sugerido")] = None,
    search: Annotated[
        str | None, Query(description="Busca en el nombre o el código", max_length=100)
    ] = None,
) -> PageSchema[CourseSchema]:
    """Lista las materias del catálogo con filtros opcionales y acumulativos."""
    resultado = use_case.execute(
        page=page, size=size, program_id=program_id, semester=semester, search=search
    )

    return PageSchema[CourseSchema](
        items=[a_schema_de_materia(c) for c in resultado.items],
        total=resultado.total,
        page=resultado.page,
        size=resultado.size,
    )


@router.get(
    "/{course_id}",
    response_model=CourseDetailSchema,
    status_code=status.HTTP_200_OK,
    summary="Detalle de una materia",
    responses={404: {"model": ErrorResponseSchema, "description": "La materia no existe"}},
)
def get_course(
    course_id: UUID,
    use_case: GetCourseDetailUseCaseDep,
    program_id: Annotated[
        UUID | None,
        Query(description="Plan de estudios sobre el que resolver prerrequisitos y correquisitos"),
    ] = None,
) -> CourseDetailSchema:
    """Devuelve una materia y, si se indica un plan, lo que exige dentro de él.

    `program_id` es opcional pero no accesorio: sin él las listas de requisitos vuelven
    vacías. Un prerrequisito no une dos materias sino dos materias dentro de una carrera, así
    que «qué exige MAT102» no tiene una respuesta única. Devolver la unión de todos los planes
    sería peor que no devolver nada: no es cierta en ninguna carrera concreta, y a un
    estudiante de Derecho le mostraría los requisitos de Ingeniería como si fueran suyos.
    """
    detalle = use_case.execute(course_id, program_id)
    materia = a_schema_de_materia(detalle.course)

    return CourseDetailSchema(
        **materia.model_dump(),
        program_id=detalle.program_id,
        prerequisites=[a_schema_de_materia(p) for p in detalle.prerequisites],
        corequisites=[a_schema_de_materia(c) for c in detalle.corequisites],
    )


@router.get(
    "/{course_id}/offerings",
    response_model=CourseOfferingsSchema,
    status_code=status.HTTP_200_OK,
    summary="Grupos de una materia en el período activo",
    responses={
        404: {
            "model": ErrorResponseSchema,
            "description": "La materia no existe, o no hay período activo",
        }
    },
)
def get_course_offerings(
    course_id: UUID, use_case: GetCourseOfferingsUseCaseDep
) -> CourseOfferingsSchema:
    """Devuelve los grupos abiertos de una materia en la ventana de matrícula vigente.

    El período no se puede elegir desde la petición: es siempre el activo.
    """
    resultado: CourseOfferingsDTO = use_case.execute(course_id)

    return CourseOfferingsSchema(
        course_id=resultado.course.id,
        course_code=resultado.course.code.value,
        period_code=resultado.period.code,
        offerings=[a_schema_de_grupo(g) for g in resultado.offerings],
    )
