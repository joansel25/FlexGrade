"""Adaptador de `RateLimiter` con Redis.

DECISIÓN CENTRAL DE ESTE ADAPTADOR: **si Redis no responde, la petición PASA.**

Es la misma elección que en la caché y por la misma razón, aunque aquí cueste más aceptarla:
el limitador es una protección, y dejarlo abierto durante una caída de Redis significa quedarse
sin ella. La alternativa es peor. Fallar cerrado convierte una caída de Azure Cache for Redis
—un servicio auxiliar— en el rechazo de TODAS las peticiones, es decir, en la caída completa de
la matrícula. El sistema existe para que 5.000 personas puedan inscribirse en una ventana de
horas; un limitador que las deja fuera a todas ha causado más daño del que evita.

Queda registrado en el log con nivel `warning`, para que en Log Analytics se vea que hubo un
periodo sin protección y no se confunda con «nadie llegó al límite».

**Ventana fija, y por qué basta.** Se cuenta por minuto natural: la clave lleva el número de
ventana dentro y vence sola. Tiene un defecto conocido —en el cambio de ventana caben hasta el
doble de peticiones, cinco al final de un minuto y cinco al principio del siguiente— y aun así
es la opción correcta aquí: cuesta una operación por petición, y el objetivo es frenar el abuso
sostenido y los reintentos automáticos, no repartir el tráfico con precisión de milisegundo.
Una ventana deslizante exige guardar la marca de tiempo de cada petición, y eso multiplica por
el límite la memoria que ocupa cada cliente en Redis, justo durante el pico.
"""

from __future__ import annotations

import logging

from redis import Redis
from redis.exceptions import RedisError

from app.application.ports.rate_limiter import RateLimiter, RateLimitResult

logger = logging.getLogger(__name__)

# Contar y preguntar el total en dos viajes deja una ventana en la que dos peticiones
# simultáneas leen el mismo número y las dos se creen la última permitida. El script se ejecuta
# entero dentro de Redis, sin que nada se cuele en medio.
#
# El `EXPIRE` va DENTRO y condicionado al primer incremento, no como una segunda llamada desde
# Python: si el proceso muriera entre `INCR` y `EXPIRE`, la clave se quedaría sin vencimiento y
# ese cliente estaría bloqueado para siempre, sin más síntoma que un 429 eterno que nadie sabría
# explicar.
_SCRIPT_CONTAR = """
local actual = redis.call('INCR', KEYS[1])
if actual == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {actual, redis.call('TTL', KEYS[1])}
"""


class RedisRateLimiter(RateLimiter):
    """Contador de ventana fija sobre Redis, compartido por todas las instancias.

    El script Lua se registra una vez y Redis lo cachea por su SHA: a partir de la primera
    llamada viaja el hash y no el cuerpo del script.
    """

    def __init__(self, cliente: Redis) -> None:
        self._cliente = cliente
        self._contar = cliente.register_script(_SCRIPT_CONTAR)

    def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        """Cuenta una petición y dice si cabe dentro del límite.

        Args:
            key: quién se está limitando, con su ámbito dentro.
            limit: peticiones permitidas en la ventana.
            window_seconds: duración de la ventana, en segundos.

        Returns:
            El veredicto. Si Redis falla, uno permisivo: ver la cabecera del módulo.
        """
        try:
            actual, ttl = self._contar(keys=[key], args=[window_seconds])
        except RedisError:
            logger.warning(
                "Redis no responde: la peticion pasa SIN limitar",
                extra={"rate_limit_key": key},
                exc_info=True,
            )
            return RateLimitResult(allowed=True, remaining=limit, retry_after_seconds=0)

        # `TTL` devuelve -1 en una clave sin vencimiento y -2 si ya no existe. Ninguno de los
        # dos deberia ocurrir con el script de arriba, pero un `Retry-After: -1` en una
        # respuesta es peor que redondear al alto: se lee como una cabecera rota.
        espera = ttl if ttl > 0 else window_seconds

        return RateLimitResult(
            allowed=actual <= limit,
            remaining=max(limit - actual, 0),
            retry_after_seconds=espera,
        )
