"""Construcción del cliente de Redis.

Es el único módulo que abre la conexión a Redis. La URL sale de `Settings.redis_url`, que a su
vez la lee de la variable de entorno `REDIS_URL`: el código no contiene ninguna credencial.
"""

from __future__ import annotations

from functools import lru_cache

from redis import Redis

from app.infrastructure.config.settings import get_settings

# Tiempos de espera cortos y explícitos. Es la otra mitad de la degradación elegante: sin
# ellos, un Redis que no responde dejaría cada petición esperando el timeout por defecto del
# sistema operativo, y una caché lenta acabaría siendo más dañina que no tener caché. Con este
# tope, un Redis caído cuesta como mucho un segundo por petición antes de ir a PostgreSQL.
_TIMEOUT_SEGUNDOS = 1.0


@lru_cache
def get_redis_client() -> Redis:
    """Devuelve el cliente de Redis, creado una sola vez por proceso.

    El cliente de `redis-py` mantiene su propio pool de conexiones y es seguro compartirlo
    entre peticiones, así que crear uno por petición solo añadiría trabajo de conexión.

    `decode_responses=True` hace que las lecturas devuelvan `str` en vez de `bytes`, que es lo
    que espera el puerto `CacheService`.

    Returns:
        El cliente compartido por toda la aplicación.
    """
    settings = get_settings()
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=_TIMEOUT_SEGUNDOS,
        socket_connect_timeout=_TIMEOUT_SEGUNDOS,
    )
