"""Router de administración académica.

TODOS los endpoints de este router exigen rol `ADMIN`, y esa exigencia se declara **una sola
vez**, en el `dependencies` del router. Repetirla endpoint por endpoint funcionaría igual hasta
el día en que alguien añada uno y se olvide: el endpoint quedaría abierto a cualquier
estudiante autenticado, y nada fallaría de forma visible. Declararla en el router hace que la
protección sea el comportamiento por defecto y no algo que haya que recordar.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.interfaces.api.dependencies.auth import require_admin
from app.interfaces.api.dependencies.di import CreateEnrollmentPeriodUseCaseDep
from app.interfaces.api.schemas.admin_schemas import (
    CreateEnrollmentPeriodSchema,
    EnrollmentPeriodSchema,
)
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema

router = APIRouter(
    prefix="/admin",
    tags=["administracion"],
    dependencies=[Depends(require_admin)],
    responses={
        401: {"model": ErrorResponseSchema, "description": "Token ausente o inválido"},
        403: {"model": ErrorResponseSchema, "description": "Se requiere rol de administrador"},
    },
)


@router.post(
    "/enrollment-periods",
    response_model=EnrollmentPeriodSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una ventana de matrícula",
    responses={
        409: {
            "model": ErrorResponseSchema,
            "description": "Ya existe una ventana con ese código, o el rango de fechas es inválido",
        }
    },
)
def create_enrollment_period(
    payload: CreateEnrollmentPeriodSchema,
    use_case: CreateEnrollmentPeriodUseCaseDep,
) -> EnrollmentPeriodSchema:
    """Registra una ventana de matrícula nueva, **desactivada**.

    Crear y activar son operaciones separadas: permite preparar la ventana con antelación y
    abrirla cuando corresponda, sin que se abra sola al llegar la fecha.
    """
    periodo = use_case.execute(
        code=payload.code,
        academic_period=payload.academic_period,
        name=payload.name,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )

    return EnrollmentPeriodSchema(
        id=periodo.id,
        code=periodo.code,
        academic_period=periodo.academic_period,
        name=periodo.name,
        starts_at=periodo.starts_at,
        ends_at=periodo.ends_at,
        is_active=periodo.is_active,
    )
