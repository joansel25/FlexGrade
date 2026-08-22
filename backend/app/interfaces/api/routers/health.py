"""Router del endpoint de salud del servicio.

`GET /health` se registra en la raíz, fuera de `API_V1_PREFIX`, porque no forma parte del
contrato de negocio versionado: lo consumen el `HEALTHCHECK` de Docker y el health check del
balanceador (ALB) de Elastic Beanstalk, que apuntan a una ruta fija e independiente de la
versión de la API.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.infrastructure.config.settings import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness check del servicio")
async def get_health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    """Reporta que el proceso está vivo y atendiendo peticiones.

    Es un *liveness check* puro: no consulta PostgreSQL ni Redis a propósito. Si dependiera de
    ellos, una caída momentánea de la base de datos haría que el balanceador retirara instancias
    sanas y amplificara el incidente. El *readiness check* con verificación de dependencias
    (`/health/ready`) se añadirá cuando existan esas dependencias, en una fase posterior.

    Args:
        settings: configuración de la aplicación, inyectada por FastAPI.

    Returns:
        dict[str, str]: cuerpo con `status` fijo en `"ok"`, el ambiente de ejecución y la
        versión desplegada. Los dos últimos permiten verificar de un vistazo qué build está
        corriendo en cada ambiente.
    """
    return {
        "status": "ok",
        "environment": settings.environment,
        "version": settings.app_version,
    }
