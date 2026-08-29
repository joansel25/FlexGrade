"""Router de los períodos de matrícula."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.interfaces.api.dependencies.di import GetCurrentPeriodUseCaseDep
from app.interfaces.api.dependencies.rate_limit import LimiteCatalogo
from app.interfaces.api.schemas.catalog_schemas import CurrentPeriodSchema
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema

router = APIRouter(
    prefix="/enrollment-periods",
    tags=["catalogo"],
    dependencies=[LimiteCatalogo],
    responses={
        429: {"model": ErrorResponseSchema, "description": "Límite de peticiones excedido"},
    },
)


@router.get(
    "/current",
    response_model=CurrentPeriodSchema,
    status_code=status.HTTP_200_OK,
    summary="Período de matrícula vigente",
    responses={404: {"model": ErrorResponseSchema, "description": "No hay un período activo"}},
)
def get_current_period(use_case: GetCurrentPeriodUseCaseDep) -> CurrentPeriodSchema:
    """Devuelve la ventana de matrícula activa y su estado en este instante.

    Distingue `is_active` de `is_open`: la primera dice que un administrador activó la
    ventana, la segunda que además admite inscripciones ahora mismo. Separarlas permite al
    frontend mostrar «la matrícula abre el martes» en vez de un escueto «no hay período».
    """
    resultado = use_case.execute()
    periodo = resultado.period

    return CurrentPeriodSchema(
        id=periodo.id,
        code=periodo.code,
        academic_period=periodo.academic_period,
        name=periodo.name,
        starts_at=periodo.starts_at,
        ends_at=periodo.ends_at,
        is_active=periodo.is_active,
        is_open=resultado.is_open,
        time_remaining_seconds=resultado.time_remaining_seconds,
    )
