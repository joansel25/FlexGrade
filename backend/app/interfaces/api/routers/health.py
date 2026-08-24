"""Router de los endpoints de salud del servicio.

Se registran en la raíz, fuera de `API_V1_PREFIX`, porque no forman parte del contrato de
negocio versionado: los consumen el `HEALTHCHECK` de Docker y el health check del balanceador
(ALB) de Elastic Beanstalk, que apuntan a una ruta fija e independiente de la versión de la API.

**Son dos rutas y la distinción importa en la nube.**

- `/health` (*liveness*) responde si el proceso está vivo. Es la que debe mirar el ALB para
  decidir si retira una instancia del balanceo.
- `/health/ready` (*readiness*) comprueba además que PostgreSQL y Redis respondan. Es la que se
  consulta después de un despliegue, a mano o desde el pipeline, para saber si la instancia
  quedó bien configurada.

Poner las dependencias en `/health` sería un error caro: una caída momentánea de RDS haría que
el ALB retirase instancias que están perfectamente sanas, el autoescalado las reemplazaría por
otras que fallarían igual, y una incidencia de base de datos se convertiría en una caída total
del servicio.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.cache.client import get_redis_client
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.persistence.sqlalchemy.session import get_engine

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness check del servicio")
async def get_health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    """Reporta que el proceso está vivo y atendiendo peticiones.

    Es un *liveness check* puro: no consulta PostgreSQL ni Redis a propósito, por la razón que
    explica el encabezado del módulo.

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


@router.get(
    "/health/ready",
    summary="Readiness check: comprueba las dependencias",
    responses={503: {"description": "Alguna dependencia no responde"}},
)
async def get_readiness(response: Response) -> dict[str, object]:
    """Comprueba que la instancia puede hacer su trabajo, no solo que arrancó.

    Responde `200` si PostgreSQL y Redis contestan, y `503` si alguno falla, indicando cuál.
    Es lo que convierte un despliegue mal configurado —una `DATABASE_URL` apuntando al RDS
    equivocado, un grupo de seguridad que no deja salir a ElastiCache— en un error inmediato y
    con nombre, en vez de en un 500 que aparece cuando el primer estudiante intenta matricular.

    Redis se reporta aparte y **no** hace fallar la comprobación: la aplicación degrada a
    PostgreSQL cuando la caché no está, así que una instancia sin Redis sirve peticiones
    correctas, solo más lentas. Marcarla como no lista la sacaría de servicio sin motivo.

    Args:
        response: la respuesta HTTP, para poder fijar el código sin lanzar una excepción.

    Returns:
        El estado de cada dependencia.
    """
    postgres_ok = _postgres_responde()
    redis_ok = _redis_responde()

    if not postgres_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if postgres_ok else "not_ready",
        "dependencies": {
            "postgres": "ok" if postgres_ok else "error",
            # `degraded` y no `error`: la aplicación sigue respondiendo sin caché.
            "redis": "ok" if redis_ok else "degraded",
        },
    }


def _postgres_responde() -> bool:
    """Ejecuta la consulta más barata posible contra PostgreSQL.

    `SELECT 1` no toca ninguna tabla: comprueba que hay conexión y que el servidor responde,
    que es justo lo que interesa saber, sin cargar la base de datos con trabajo real cada vez
    que el pipeline pregunta.
    """
    try:
        with get_engine().connect() as conexion:
            conexion.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False

    return True


def _redis_responde() -> bool:
    """Hace `PING` a Redis."""
    try:
        return bool(get_redis_client().ping())
    except (RedisError, OSError):
        return False
