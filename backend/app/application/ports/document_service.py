"""Puerto de generación de documentos descargables."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dtos.receipt_dto import ReceiptDTO


class ReceiptRenderer(ABC):
    """Contrato de dibujado del comprobante de matrícula.

    Recibe el contenido ya compuesto y devuelve los bytes del documento. No consulta nada: si
    necesitara la base de datos, la maquetación acabaría decidiendo qué se muestra, y cambiar
    el diseño obligaría a tocar consultas.

    Es un puerto y no una función suelta por lo de siempre en esta arquitectura: el caso de uso
    depende de la abstracción, así que sustituir reportlab por otro motor —o por un
    comprobante en HTML— se hace escribiendo un adaptador nuevo y cambiando una línea de
    `di.py`, sin que el caso de uso se entere.
    """

    @abstractmethod
    def render(self, receipt: ReceiptDTO) -> bytes:
        """Dibuja el comprobante.

        Args:
            receipt: el contenido completo del documento.

        Returns:
            Los bytes del documento listo para descargar.
        """
