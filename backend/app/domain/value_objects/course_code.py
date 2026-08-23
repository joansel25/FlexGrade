"""Value object del código institucional de una materia."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.exceptions.invalid_value import InvalidCourseCodeError

# Formato institucional: unas letras de área seguidas de un número de nivel, como `MAT101`
# o `ISIS2010`. Se valida la forma, no que la materia exista: eso lo responde el repositorio.
_PATRON_CODIGO = re.compile(r"^[A-Z]{2,8}\d{2,6}$")


@dataclass(frozen=True)
class CourseCode:
    """Código con el que la institución identifica una materia.

    Es el identificador que reconocen estudiantes y docentes —nadie pide "la materia
    `550e8400-e29b`", piden `MAT101`— y por eso merece un tipo propio en vez de un `str`
    cualquiera.

    Attributes:
        value: el código normalizado en mayúsculas y sin espacios extremos.
    """

    value: str

    def __post_init__(self) -> None:
        normalizado = self.value.strip().upper()

        if not _PATRON_CODIGO.match(normalizado):
            raise InvalidCourseCodeError(
                f"El código '{self.value}' no cumple el formato institucional "
                "(de 2 a 8 letras seguidas de 2 a 6 dígitos, por ejemplo MAT101)"
            )

        # `frozen=True` bloquea la asignación directa; se normaliza vía object.__setattr__.
        object.__setattr__(self, "value", normalizado)

    def __str__(self) -> str:
        return self.value
