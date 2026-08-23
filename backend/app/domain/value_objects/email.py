"""Value object del correo electrónico institucional."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.exceptions.invalid_value import InvalidEmailError

# Validación deliberadamente conservadora: comprueba la forma general del correo,
# no el RFC 5322 completo. Un regex exhaustivo es ilegible y sigue sin garantizar
# que la dirección exista; la verificación real es enviar un mensaje.
_PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")

_LONGITUD_MAXIMA = 255


@dataclass(frozen=True)
class Email:
    """Correo electrónico validado e inmutable.

    Existe para evitar la obsesión por primitivas: una función que recibe `str`
    acepta `""` o `"lo que sea"`; una que recibe `Email` no.

    Attributes:
        value: la dirección normalizada en minúsculas y sin espacios extremos.
    """

    value: str

    def __post_init__(self) -> None:
        normalizado = self.value.strip().lower()

        if not normalizado:
            raise InvalidEmailError("El correo electrónico no puede estar vacío")

        if len(normalizado) > _LONGITUD_MAXIMA:
            raise InvalidEmailError(
                f"El correo excede los {_LONGITUD_MAXIMA} caracteres permitidos"
            )

        if not _PATRON_EMAIL.match(normalizado):
            raise InvalidEmailError(f"El correo '{self.value}' no tiene un formato válido")

        # `frozen=True` bloquea la asignación directa; se normaliza vía object.__setattr__.
        object.__setattr__(self, "value", normalizado)

    def __str__(self) -> str:
        return self.value
