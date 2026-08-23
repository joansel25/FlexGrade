"""Excepción raíz de todos los errores del dominio."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base de todas las excepciones del dominio.

    Permite que la capa de API registre un único manejador de respaldo y que los
    casos de uso distingan un fallo de negocio previsible de un error inesperado.
    Nunca se lanza directamente: siempre una subclase con nombre propio.

    Attributes:
        message: descripción del fallo, apta para mostrarse al usuario.
        details: datos estructurados que acompañan al error en la respuesta HTTP.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}
