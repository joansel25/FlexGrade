"""Router del detalle de un grupo."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.interfaces.api.dependencies.di import GetOfferingDetailUseCaseDep
from app.interfaces.api.routers.courses import a_schema_de_grupo
from app.interfaces.api.schemas.catalog_schemas import OfferingDetailSchema
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema

router = APIRouter(prefix="/offerings", tags=["catalogo"])


@router.get(
    "/{offering_id}",
    response_model=OfferingDetailSchema,
    status_code=status.HTTP_200_OK,
    summary="Detalle de un grupo",
    responses={404: {"model": ErrorResponseSchema, "description": "El grupo no existe"}},
)
def get_offering(offering_id: UUID, use_case: GetOfferingDetailUseCaseDep) -> OfferingDetailSchema:
    """Devuelve un grupo con su docente, su horario y su cupo.

    Es el endpoint más consultado durante la ventana de matrícula, así que su parte estática
    se sirve desde Redis. El cupo ocupado, en cambio, se lee siempre de PostgreSQL: el caso de
    uso lo refresca antes de responder, venga el grupo de la caché o de la base de datos.
    """
    grupo = use_case.execute(offering_id)
    base = a_schema_de_grupo(grupo)

    return OfferingDetailSchema(
        **base.model_dump(),
        course_id=grupo.course_id,
        enrollment_period_id=grupo.enrollment_period_id,
    )
