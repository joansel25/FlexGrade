"""Router del perfil del estudiante."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.domain.exceptions.authentication import StudentProfileNotFoundError
from app.interfaces.api.dependencies.auth import CurrentUserDep
from app.interfaces.api.dependencies.di import StudentRepositoryDep, UserRepositoryDep
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema
from app.interfaces.api.schemas.student_schemas import StudentProfileSchema

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

    return StudentProfileSchema(
        id=estudiante.id,
        student_code=estudiante.student_code.value,
        full_name=estudiante.full_name,
        email=usuario.email.value,
        program_id=estudiante.program_id,
        current_semester=estudiante.current_semester,
        enrollment_date=estudiante.enrollment_date,
    )
