"""Adaptador de `CacheService` con Redis.

DECISIÓN CENTRAL DE ESTE ADAPTADOR: **la caché nunca puede tumbar una petición.**

Redis es una optimización, no una fuente de verdad. Si el servidor está caído, saturado o
tarda demasiado, la respuesta correcta es comportarse como si la clave no estuviera en caché y
dejar que la petición siga contra PostgreSQL: más lenta, pero correcta. Propagar el error
convertiría una degradación de rendimiento en una caída total del catálogo, y lo haría
precisamente durante el pico de matrícula, que es cuando Azure Cache for Redis tiene más
probabilidades de ir justo.

Por eso todos los métodos capturan `RedisError` y siguen adelante dejando rastro en el log. No
es tragarse errores a ciegas: se captura la excepción de Redis, no `Exception`, así que un
defecto de programación —un tipo equivocado, un argumento mal pasado— sigue estallando y se
detecta en los tests en vez de esconderse detrás de un `except` demasiado ancho.
"""

from __future__ import annotations

import logging
import time

from redis import Redis
from redis.exceptions import RedisError

from app.application.ports.cache_service import CacheService

logger = logging.getLogger(__name__)

# Fallos consecutivos tras los cuales se deja de intentar durante un rato.
_FALLOS_PARA_ABRIR = 3

# Cuánto se deja de intentar. Suficiente para no castigar cada petición durante una caída, y
# lo bastante corto para recuperar la caché enseguida cuando Redis vuelva.
_ESPERA_SEGUNDOS = 10.0


class RedisCacheService(CacheService):
    """Implementación del puerto de caché sobre Redis 7, con cortacircuitos.

    **Por qué hay un cortacircuitos y no solo un `try/except`.** Capturar el error basta para
    que la petición no falle, pero no para que sea rápida: con Redis inalcanzable, cada
    operación se queda esperando el `socket_connect_timeout` de un segundo. Una consulta de
    grupo hace dos operaciones, así que serían dos segundos añadidos a cada petición. Con
    5.000 estudiantes concurrentes durante la ventana de matrícula, eso agota el pool de
    conexiones y convierte una caché caída en una aplicación caída.

    Con el cortacircuitos, la caída cuesta tres intentos fallidos y a partir de ahí las
    peticiones van directas a PostgreSQL sin pagar ni un milisegundo de espera. Pasados diez
    segundos se prueba de nuevo: si Redis volvió, la caché se reactiva sola.

    El estado es por proceso, que es donde está el problema: cada worker aprende por su cuenta
    que Redis no responde. Compartirlo entre procesos exigiría un coordinador externo —otra
    dependencia que también podría caerse— para resolver algo que cuesta tres peticiones.
    """

    def __init__(self, client: Redis) -> None:
        """Construye el adaptador.

        Args:
            client: cliente de Redis ya configurado. Se recibe por constructor y no se crea
                aquí para que los tests puedan sustituirlo y para que la configuración de la
                conexión —tiempos de espera, pool— viva en un solo sitio.
        """
        self._client = client
        self._fallos = 0
        self._reintentar_a_partir_de = 0.0

    def get(self, key: str) -> str | None:
        if self._circuito_abierto():
            return None

        try:
            valor = self._client.get(key)
        except RedisError:
            self._anotar_fallo("leer", key)
            return None

        self._anotar_exito()

        if valor is None:
            return None

        # El cliente se construye con `decode_responses=True`, así que devuelve `str`. El
        # `isinstance` cubre el caso de que alguien inyecte un cliente configurado de otra
        # forma: es preferible ignorar la entrada a devolver un `bytes` donde se espera texto.
        return valor if isinstance(valor, str) else None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if self._circuito_abierto():
            return

        try:
            self._client.set(key, value, ex=ttl_seconds)
        except RedisError:
            self._anotar_fallo("escribir en", key)
            return

        self._anotar_exito()

    def delete(self, key: str) -> None:
        if self._circuito_abierto():
            return

        try:
            self._client.delete(key)
        except RedisError:
            self._anotar_fallo("invalidar en", key)
            return

        self._anotar_exito()

    # ------------------------------------------------------------- cortacircuitos

    def _circuito_abierto(self) -> bool:
        """Indica si hay que saltarse Redis por completo en este momento."""
        if self._fallos < _FALLOS_PARA_ABRIR:
            return False

        # `monotonic` y no `time()`: un ajuste del reloj del sistema no puede dejar el
        # circuito abierto para siempre ni cerrarlo antes de tiempo.
        if time.monotonic() >= self._reintentar_a_partir_de:
            # Se acabó la espera: se deja pasar esta operación como sonda. Si funciona,
            # `_anotar_exito` cierra el circuito; si no, `_anotar_fallo` reinicia la espera.
            return False

        return True

    def _anotar_fallo(self, operacion: str, key: str) -> None:
        self._fallos += 1
        self._reintentar_a_partir_de = time.monotonic() + _ESPERA_SEGUNDOS

        if self._fallos == _FALLOS_PARA_ABRIR:
            logger.warning(
                "Cache desactivada tras %d fallos consecutivos; se reintentara en %.0f s. "
                "Las consultas van directas a PostgreSQL.",
                _FALLOS_PARA_ABRIR,
                _ESPERA_SEGUNDOS,
            )
        elif self._fallos < _FALLOS_PARA_ABRIR:
            logger.warning(
                "Fallo al %s la cache la clave '%s'; se continua sin ella", operacion, key
            )

    def _anotar_exito(self) -> None:
        if self._fallos >= _FALLOS_PARA_ABRIR:
            logger.info("Cache restablecida; se vuelve a usar Redis")

        self._fallos = 0
