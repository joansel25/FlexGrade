"""Value object `Grade`: la nota final de una inscripción."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.domain.exceptions.invalid_value import InvalidValueError

MINIMA = Decimal("0.0")
MAXIMA = Decimal("5.0")
#: A partir de aquí la materia se aprueba. Es la escala colombiana, y la misma que usa el seed
#: al repartir el historial de ejemplo.
APROBATORIA = Decimal("3.0")


@dataclass(frozen=True)
class Grade:
    """Nota final en la escala de 0.0 a 5.0, con dos decimales.

    ES UN VALUE OBJECT Y NO UN `float` por dos razones que no son de estilo:

    **El rango es una regla de negocio, no una validación de formato.** Una nota de 7.5 no es un
    dato mal escrito: es una calificación de otra escala, y aceptarla dejaría a un estudiante
    aprobado según un criterio que el sistema no tiene. Si el rango viviera en el schema de
    Pydantic, el dominio podría recibirla por cualquier otro camino —el seed, una migración, un
    caso de uso nuevo— sin que nada lo impidiera.

    **`float` no vale para una nota.** `0.1 + 0.2` no es `0.3` en coma flotante, y una nota que
    cae justo en la frontera de aprobación decidiría el semestre de alguien según un error de
    redondeo binario. Se usa `Decimal`, que es lo que la columna `NUMERIC(3,2)` guarda.

    El redondeo es HALF_UP y no el `ROUND_HALF_EVEN` que Python trae por defecto: `2.995` tiene
    que subir a `3.00` —aprobar— y no bajar a `2.99`. El bancario es correcto para promediar
    dinero y equivocado para redondear a favor de una persona.

    Attributes:
        value: la nota, ya normalizada a dos decimales.
    """

    value: Decimal

    def __post_init__(self) -> None:
        try:
            normalizada = Decimal(self.value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError) as error:
            raise InvalidValueError("La nota no es un número válido") from error

        if not MINIMA <= normalizada <= MAXIMA:
            raise InvalidValueError(
                f"La nota debe estar entre {MINIMA} y {MAXIMA}; se recibió {self.value}"
            )

        object.__setattr__(self, "value", normalizada)

    def aprueba(self) -> bool:
        """Indica si la nota alcanza el mínimo para dar la materia por aprobada."""
        return self.value >= APROBATORIA

    def __str__(self) -> str:
        return f"{self.value:.2f}"
