"""Puerto del servicio de caché.

El contrato es deliberadamente pequeño —leer, escribir con vencimiento, invalidar— y habla
solo de cadenas de texto. Serializar es responsabilidad de quien llama: meter JSON en el
puerto lo ataría a un formato concreto y obligaría a cambiar la interfaz el día que convenga
otro, que es justo lo que un puerto debe evitar.

Sobre qué se cachea, la regla del proyecto no admite matices (`CLAUDE.md`): el catálogo sí, la
disponibilidad de cupos **nunca**. Un `available_slots` de hace treinta segundos es
exactamente el fallo que este sistema existe para impedir.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class CacheService(ABC):
    """Contrato de una caché de clave-valor con vencimiento."""

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Lee un valor de la caché.

        Args:
            key: clave a consultar.

        Returns:
            El valor almacenado, o `None` si la clave no existe o ya venció.
        """

    @abstractmethod
    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Guarda un valor con un tiempo de vida.

        El TTL es obligatorio y no tiene valor por defecto: una entrada sin vencimiento en un
        sistema donde el catálogo cambia entre semestres es una fuga de memoria con datos
        obsoletos dentro.

        Args:
            key: clave bajo la que guardar.
            value: contenido a guardar, ya serializado.
            ttl_seconds: segundos que la entrada permanece válida.
        """

    @abstractmethod
    def delete(self, key: str) -> None:
        """Invalida una entrada de la caché.

        No falla si la clave no existe: el resultado buscado —que esa clave no esté— ya se
        cumple.

        Args:
            key: clave a invalidar.
        """
