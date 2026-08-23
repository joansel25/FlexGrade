"""Value object del código institucional del estudiante."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.exceptions.invalid_value import InvalidStudentCodeError

# El código institucional es numérico. El rango de longitud cubre los formatos
# historicos de la institución sin admitir cadenas arbitrarias.
_PATRON_CODIGO = re.compile(r"^\d{6,20}$")


@dataclass(frozen=True)
class StudentCode:
    """Código con el que la institución identifica a un estudiante.

    Attributes:
        value: el código, solo dígitos.
    """

    value: str

    def __post_init__(self) -> None:
        normalizado = self.value.strip()

        if not _PATRON_CODIGO.match(normalizado):
            raise InvalidStudentCodeError(
                f"El código '{self.value}' no cumple el formato institucional "
                "(entre 6 y 20 dígitos)"
            )

        object.__setattr__(self, "value", normalizado)

    def __str__(self) -> str:
        return self.value
