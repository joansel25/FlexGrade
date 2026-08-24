"""Router del perfil y el horario del estudiante."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.domain.exceptions.authentication import StudentProfileNotFoundError
from app.interfaces.api.dependencies.auth import CurrentStudentDep, CurrentUserDep
from app.interfaces.api.dependencies.di import (
    GetStudentScheduleUseCaseDep,
    ProgramRepositoryDep,
    StudentRepositoryDep,
    UserRepositoryDep,
)
from app.interfaces.api.schemas.enrollment_schemas import ScheduleBlockSchema, StudentScheduleSchema
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema
from app.interfaces.api.schemas.student_schemas import ProgramSummarySchema, StudentProfileSchema

router = APIRouter(prefix="/students", tags=["students"])


@router.get(
    "/me",
    response_model=StudentProfileSchema,
    status_code=status.HTTP_200_OK,
    summary="Perfil del estudiante autenticado",
    responses={
        401: {"model": ErrorResponseSchema, "description": "Token ausente o inválido"},
        404: {"model": ErrorResponseSchema, "description": "La cuenta no tiene perfil académico"},
    },
)
def get_my_profile(
    current_user: CurrentUserDep,
    student_repository: StudentRepositoryDep,
    user_repository: UserRepositoryDep,
    program_repository: ProgramRepositoryDep,
) -> StudentProfileSchema:
    """Devuelve el perfil académico de la cuenta autenticada.

    El identificador sale del token (`current_user.user_id`), nunca de la
    petición: así un estudiante no puede consultar el perfil de otro.
    """
    estudiante = student_repository.find_by_user_id(current_user.user_id)
    if estudiante is None:
        raise StudentProfileNotFoundError()

    usuario = user_repository.find_by_id(current_user.user_id)
    if usuario is None:
        raise StudentProfileNotFoundError("La cuenta asociada al perfil ya no existe")

    # `students.program_id` es una clave foránea obligatoria, así que el programa existe
    # salvo que la base de datos esté corrupta. Aun así se comprueba: devolver un 500 por un
    # `None` inesperado sería peor que un 404 con un mensaje que dice qué pasó.
    programa = program_repository.find_by_id(estudiante.program_id)
    if programa is None:
        raise StudentProfileNotFoundError("El programa asociado al perfil ya no existe")

    return StudentProfileSchema(
        id=estudiante.id,
        student_code=estudiante.student_code.value,
        full_name=estudiante.full_name,
        email=usuario.email.value,
        program=ProgramSummarySchema(id=programa.id, code=programa.code, name=programa.name),
        current_semester=estudiante.current_semester,
        enrollment_date=estudiante.enrollment_date,
    )


@router.get(
    "/me/schedule",
    response_model=StudentScheduleSchema,
    status_code=status.HTTP_200_OK,
    summary="Horario del estudiante en el período activo",
    responses={
        401: {"model": ErrorResponseSchema, "description": "Token ausente o inválido"},
        404: {
            "model": ErrorResponseSchema,
            "description": "La cuenta no tiene perfil académico, o no hay período activo",
        },
    },
)
def get_my_schedule(
    estudiante: CurrentStudentDep,
    use_case: GetStudentScheduleUseCaseDep,
) -> StudentScheduleSchema:
    """Devuelve el horario armado con las inscripciones activas del período vigente.

    Las franjas llegan ordenadas por día y hora, que es como se lee un horario. Si el
    estudiante no tiene nada inscrito, la lista va vacía: es un resultado legítimo, no un error.
    """
    horario = use_case.execute(estudiante.id)

    return StudentScheduleSchema(
        period=horario.academic_period,
        blocks=[
            ScheduleBlockSchema(
                course_code=b.course_code,
                course_name=b.course_name,
                group_number=b.group_number,
                professor=b.professor,
                day_of_week=b.day_of_week,
                start_time=b.start_time,
                end_time=b.end_time,
                classroom=b.classroom,
            )
            for b in horario.blocks
        ],
    )
