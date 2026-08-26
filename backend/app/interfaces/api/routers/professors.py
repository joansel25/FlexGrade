"""Endpoints del docente (Fase 9).

Todos cuelgan de `/professors/me` y resuelven el perfil desde el TOKEN. No hay ninguna ruta con
un identificador de docente dentro: si la hubiera, cualquier docente podría pedir la carga —y en
la 9.2, las notas— de otro, y la única defensa sería recordar comprobarlo en cada endpoint.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response, status

from app.domain.value_objects.grade import Grade
from app.interfaces.api.dependencies.auth import CurrentProfessorDep
from app.interfaces.api.dependencies.di import (
    GetOfferingRosterUseCaseDep,
    ListProfessorOfferingsUseCaseDep,
    SetGradeUseCaseDep,
)
from app.interfaces.api.schemas.catalog_schemas import ScheduleBlockSchema
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema
from app.interfaces.api.schemas.teaching_schemas import (
    GradeEntrySchema,
    OfferingRosterSchema,
    ProfessorOfferingSchema,
    ProfessorOfferingsSchema,
    SetGradeSchema,
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


@router.get(
    "/me/offerings/{offering_id}/roster",
    response_model=OfferingRosterSchema,
    status_code=status.HTTP_200_OK,
    summary="La lista de un grupo, con las notas que ya tiene",
    responses={
        403: {"model": ErrorResponseSchema, "description": "Ese grupo lo dicta otra persona"},
        404: {"model": ErrorResponseSchema, "description": "El grupo no existe"},
        409: {"model": ErrorResponseSchema, "description": "El grupo es de un periodo cerrado"},
    },
)
def offering_roster(
    offering_id: UUID,
    docente: CurrentProfessorDep,
    use_case: GetOfferingRosterUseCaseDep,
) -> OfferingRosterSchema:
    """Devuelve quién está inscrito en el grupo y qué nota lleva cada uno.

    Solo salen las inscripciones VIVAS. Quien canceló no cursó la materia, y ofrecerla en la
    lista invitaría a calificar una fila que el servidor va a rechazar.

    `final_grade` en `null` es «todavía sin calificar», que NO es lo mismo que `0.00`: son
    estados opuestos y con un cero por defecto se verían igual.
    """
    lista = use_case.execute(offering_id=offering_id, professor_id=docente.id)

    return OfferingRosterSchema(
        offering_id=lista.offering.id,
        course_code=lista.course.code.value,
        course_name=lista.course.name,
        group_number=lista.offering.group_number,
        total=len(lista.entries),
        pending=lista.pending,
        entries=[
            GradeEntrySchema(
                student_id=entrada.student.id,
                student_code=entrada.student.student_code.value,
                full_name=entrada.student.full_name,
                final_grade=(
                    None
                    if entrada.enrollment.final_grade is None
                    else entrada.enrollment.final_grade.value
                ),
                graded_at=entrada.enrollment.graded_at,
            )
            for entrada in lista.entries
        ],
    )


@router.put(
    "/me/offerings/{offering_id}/grades/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Registrar o corregir la nota de un estudiante",
    responses={
        403: {"model": ErrorResponseSchema, "description": "Ese grupo lo dicta otra persona"},
        404: {
            "model": ErrorResponseSchema,
            "description": "El grupo no existe, o el estudiante no está inscrito en él",
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "El período está cerrado, o la inscripción fue cancelada",
        },
    },
)
def set_grade(
    offering_id: UUID,
    student_id: UUID,
    payload: SetGradeSchema,
    docente: CurrentProfessorDep,
    use_case: SetGradeUseCaseDep,
) -> Response:
    """Deja la nota registrada. **Response 204.**

    `PUT` porque es idempotente: volver a poner la misma nota deja el mismo estado. Por eso
    corregir una nota mal tecleada es esta misma llamada y no una operación aparte que quien
    califica tenga que recordar.

    **La nota se guarda en la inscripción, no en el historial académico.** El historial es un
    registro consolidado: lo que hay ahí decide prerrequisitos y aparece en el expediente.
    Escribir cada tecleo directamente allí haría irreversible una corrección tan normal como
    equivocarse de fila. La consolidación es una operación aparte, de Registro Académico.
    """
    use_case.execute(
        offering_id=offering_id,
        professor_id=docente.id,
        student_id=student_id,
        grade=Grade(payload.final_grade),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
