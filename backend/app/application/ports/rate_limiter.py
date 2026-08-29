"""Puerto del limitador de peticiones.

**Por qué es un puerto y no una llamada directa a Redis.** El límite se aplica en el borde de
la API, pero el mecanismo que lo sostiene es infraestructura: hoy un contador en Redis, mañana
podría ser el WAF del Application Gateway. Con un puerto, cambiarlo es escribir otro adaptador;
sin él, la regla quedaría cosida al cliente de Redis dentro de una dependencia de FastAPI y no
habría forma de probarla sin levantar Redis.

**Por qué no puede ser un contador en memoria.** Con varias instancias detrás del Application
Gateway, cada proceso llevaría su propia cuenta y el límite real sería el declarado multiplicado
por el número de instancias —un número que además cambia solo con el autoescalado—. Un límite
que depende de a qué instancia te toque llegar no es un límite.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    """Lo que se sabe tras contar una petición.

    Se devuelve un resultado en vez de lanzar una excepción porque el puerto solo CUENTA;
    decidir qué hacer con el veredicto —rechazar, registrar, dejar pasar— es de quien llama.
    Un puerto que lanza excepciones de HTTP obligaría a que cualquier otro consumidor las
    entendiera.

    Attributes:
        allowed: si la petición cabe dentro del límite.
        remaining: cuántas quedan en la ventana actual. Nunca negativo.
        retry_after_seconds: segundos que faltan para que la ventana se renueve. Es lo que
            viaja en la cabecera `Retry-After`, y sin él un cliente rechazado solo puede
            reintentar a ciegas.
    """

    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimiter(ABC):
    """Contrato de un contador de peticiones por ventana de tiempo."""

    @abstractmethod
    def hit(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        """Cuenta una petición y dice si cabe dentro del límite.

        La operación es de escritura y lectura a la vez, y tiene que ser ATÓMICA: contar y
        después preguntar el total en dos viajes deja una ventana en la que dos peticiones
        simultáneas leen el mismo número y las dos se creen la última permitida. Es la misma
        clase de carrera que el descuento de cupo, y se resuelve igual: una sola operación
        indivisible.

        Args:
            key: quién se está limitando. La construye quien llama e incluye el ámbito, para
                que dos límites distintos no compartan contador.
            limit: peticiones permitidas dentro de la ventana.
            window_seconds: duración de la ventana.

        Returns:
            El veredicto para ESTA petición.
        """
