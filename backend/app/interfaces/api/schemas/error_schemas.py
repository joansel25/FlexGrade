"""Schema del formato único de error de la API.

Toda respuesta de error del sistema usa esta forma, definida en `API.md`:

```json
{"error": {"code": "...", "message": "...", "details": {...}}}
```

Un formato único permite que el frontend tenga un solo camino de manejo de
errores y que `error.code` —estable y legible por máquina— sea lo que decide el
mensaje que ve el usuario, en vez de parsear textos.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetailSchema(BaseModel):
    """Cuerpo del error."""

    code: str = Field(description="Código estable del error, p. ej. ALREADY_ENROLLED")
    message: str = Field(description="Mensaje legible para el usuario final")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Datos estructurados que acompañan al error",
    )


class ErrorResponseSchema(BaseModel):
    """Envoltura estándar de cualquier respuesta de error."""

    error: ErrorDetailSchema
