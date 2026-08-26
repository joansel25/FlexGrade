"""Endpoints del docente (Fase 9).

Todos cuelgan de `/professors/me` y resuelven el perfil desde el TOKEN. No hay ninguna ruta con
un identificador de docente dentro: si la hubiera, cualquier docente podría pedir la carga —y en
la 9.2, las notas— de otro, y la única defensa sería recordar comprobarlo en cada endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.interfaces.api.dependencies.auth import CurrentProfessorDep
from app.interfaces.api.dependencies.di import ListProfessorOfferingsUseCaseDep
from app.interfaces.api.schemas.catalog_schemas import ScheduleBlockSchema
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema
from app.interfaces.api.schemas.teaching_schemas import (
    ProfessorOfferingSchema,
    ProfessorOfferingsSchema,
)

router = APIRouter(prefix="/professors", tags=["Docentes"])


@router.get(
    "/me/offerings",
    response_model=ProfessorOfferingsSchema,
    status_code=status.HTTP_200_OK,
    summary="Mis grupos del período activo",
    responses={
        403: {"model": ErrorResponseSchema, "description": "La cuenta no tiene rol de docente"},
        404: {"model": ErrorResponseSchema, "description": "La cuenta no tiene perfil docente"},
    },
)
def my_offerings(
    docente: CurrentProfessorDep,
    use_case: ListProfessorOfferingsUseCaseDep,
) -> ProfessorOfferingsSchema:
    """Devuelve los grupos que dicta quien hace la petición, en la ventana activa.

    Sin período activo responde 200 con la lista vacía y `period_code` en `null`, no un 404:
    entre semestres no hay ventana abierta y eso es normal, mientras que un 404 diría que algo
    está roto.
    """
    carga = use_case.execute(docente.id)

    return ProfessorOfferingsSchema(
        period_code=carga.period_code,
        academic_period=carga.academic_period,
        total=len(carga.offerings),
        items=[
            ProfessorOfferingSchema(
                offering_id=entrada.offering.id,
                course_id=entrada.course.id,
                course_code=entrada.course.code.value,
                course_name=entrada.course.name,
                credits=entrada.course.credits,
                group_number=entrada.offering.group_number,
                enrolled_count=entrada.offering.enrolled_count,
                total_capacity=entrada.offering.total_capacity,
                schedule=[
                    ScheduleBlockSchema(
                        day_of_week=franja.day_of_week,
                        start_time=franja.start_time,
                        end_time=franja.end_time,
                        classroom=franja.classroom,
                    )
                    for franja in entrada.offering.schedule
                ],
            )
            for entrada in carga.offerings
        ],
    )
