"""Errores que nacen en la capa de API y no en el dominio.

**Por qué esto no es una excepción de dominio.** Todas las demás lo son —`CourseNotFoundError`,
`OfferingFullError`, `AdminRequiredError`— porque expresan una regla del negocio académico: que
una materia no existe, que un grupo se llenó, que solo Registro Académico puede abrir un
período. «No más de cinco intentos de inicio de sesión por minuto» no es ninguna regla
académica: es una protección operativa del borde, y el día que la ponga el WAF del Application
Gateway el dominio no debería enterarse de que existió.

Meterla en `domain/exceptions/` habría sido más cómodo —el manejador de `DomainError` ya está
escrito— y habría metido en el núcleo un concepto que no le pertenece. Esa comodidad es
exactamente como los dominios se llenan de infraestructura.
"""

from __future__ import annotations

from typing import Any


class RateLimitExceededError(Exception):
    """El cliente superó el número de peticiones permitidas en la ventana.

    Attributes:
        message: qué pasó, en lenguaje que se le puede mostrar a una persona.
        details: el límite y el ámbito, para que el cliente sepa cuál de los cuatro se agotó.
        retry_after_seconds: lo que falta para que la ventana se renueve. Viaja en la cabecera
            `Retry-After`, y sin él un cliente rechazado solo puede reintentar a ciegas —que
            durante la ventana de matrícula significa reintentar en bucle y empeorar justo lo
            que el límite existe para contener—.
    """

    def __init__(
        self,
        message: str,
        retry_after_seconds: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.details: dict[str, Any] = details or {}
