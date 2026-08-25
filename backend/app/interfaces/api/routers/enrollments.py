"""Router de inscripciones.

Los dos endpoints más sensibles del sistema. Los handlers son deliberadamente delgados: el
estudiante lo resuelve una dependencia, la lógica vive en los casos de uso, y las excepciones
de dominio las traduce a HTTP el manejador centralizado de `main.py`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.interfaces.api.dependencies.auth import CurrentStudentDep
from app.interfaces.api.dependencies.di import CancelEnrollmentUseCaseDep, EnrollStudentUseCaseDep
from app.interfaces.api.schemas.enrollment_schemas import (
    CancellationSchema,
    CancelledEnrollmentSchema,
    EnrollmentSchema,
    EnrollRequestSchema,
)
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema

router = APIRouter(prefix="/enrollments", tags=["inscripciones"])


@router.post(
    "",
    response_model=EnrollmentSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Inscribir al estudiante en un grupo",
    responses={
        401: {"model": ErrorResponseSchema, "description": "Token ausente o inválido"},
        403: {"model": ErrorResponseSchema, "description": "La materia no está en tu plan"},
        404: {"model": ErrorResponseSchema, "description": "El grupo no existe"},
        409: {
            "model": ErrorResponseSchema,
            "description": (
                "Cupo agotado, período cerrado, ya inscrito, prerrequisitos sin aprobar "
                "o choque de horario"
            ),
        },
    },
)
def enroll(
    payload: EnrollRequestSchema,
    estudiante: CurrentStudentDep,
    use_case: EnrollStudentUseCaseDep,
) -> EnrollmentSchema:
    """Inscribe al estudiante autenticado en el grupo indicado.

    El estudiante sale del token y no del cuerpo: no hay forma de inscribir a otra persona.
    """
    resultado = use_case.execute(
        student_id=estudiante.id, course_offering_id=payload.course_offering_id
    )

    return EnrollmentSchema(
        id=resultado.id,
        student_id=resultado.student_id,
        course_offering_id=resultado.course_offering_id,
        course_code=resultado.course_code,
        course_name=resultado.course_name,
        group_number=resultado.group_number,
        enrolled_at=resultado.enrolled_at,
        status=resultado.status.value,
    )


@router.delete(
    "/{enrollment_id}",
    response_model=CancellationSchema,
    status_code=status.HTTP_200_OK,
    summary="Cancelar una inscripción propia",
    responses={
        401: {"model": ErrorResponseSchema, "description": "Token ausente o inválido"},
        404: {"model": ErrorResponseSchema, "description": "La inscripción no existe"},
        409: {
            "model": ErrorResponseSchema,
            "description": "Ya estaba cancelada, u otra materia inscrita exige cursar esta",
        },
    },
)
def cancel(
    enrollment_id: UUID,
    estudiante: CurrentStudentDep,
    use_case: CancelEnrollmentUseCaseDep,
) -> CancellationSchema:
    """Cancela una inscripción del estudiante autenticado y libera su cupo.

    Responde `200` con lo que se canceló, y no `204`, porque la operación puede arrastrar más
    de una inscripción: las materias unidas por correquisitos mutuos se abandonan como un
    bloque. Con `204` desaparecerían dos materias de la pantalla tras pulsar «Cancelar» en una
    sola, sin nada que lo explicara.

    Cancelar una inscripción ajena responde 404, igual que si no existiera: distinguir ambos
    casos confirmaría qué identificadores corresponden a inscripciones reales.
    """
    resultado = use_case.execute(student_id=estudiante.id, enrollment_id=enrollment_id)

    return CancellationSchema(
        cancelled=[
            CancelledEnrollmentSchema(
                id=c.id,
                course_offering_id=c.course_offering_id,
                course_code=c.course_code,
                course_name=c.course_name,
                group_number=c.group_number,
            )
            for c in resultado.items
        ]
    )
