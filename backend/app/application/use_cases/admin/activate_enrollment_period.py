"""Caso de uso: abrir una ventana de matrícula.

Es la operación más delicada de la Fase 4. Cambia dos filas —desactivar la ventana anterior y
activar la nueva— y el esquema **prohíbe el estado intermedio**: `ix_enrollment_periods_active`
es un índice único parcial que rechaza dos períodos activos a la vez.

Eso obliga a dos cosas, y ninguna es opcional:

1. **Las dos escrituras van en la misma transacción.** Si la primera se confirmara sola, el
   sistema quedaría sin ningún período activo y la matrícula se cerraría para todo el mundo.
2. **El orden importa.** PostgreSQL comprueba el índice único al ejecutar cada sentencia, no al
   confirmar. Activar primero la nueva chocaría contra la anterior aunque las dos estuvieran en
   la misma transacción. Se desactiva primero y se activa después: se pasa por «ninguna activa»,
   que sí es un estado válido, en vez de por «dos activas», que no lo es.
"""

from __future__ import annotations

from uuid import UUID

from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.entities.enrollment_period import EnrollmentPeriod
from app.domain.exceptions.catalog import PeriodNotFoundError


class ActivateEnrollmentPeriodUseCase:
    """Abre una ventana de matrícula y cierra la que estuviera abierta."""

    def __init__(self, period_repository: PeriodRepository, unit_of_work: UnitOfWork) -> None:
        self._periods = period_repository
        self._uow = unit_of_work

    def execute(self, period_id: UUID) -> EnrollmentPeriod:
        """Activa la ventana indicada.

        Es **idempotente**: activar una ventana que ya está activa devuelve la ventana sin
        tocar nada. El estado que se pide ya se cumple, y responder con un error obligaría a
        quien llama a consultar antes para saber si puede llamar, que es justo lo que un `PUT`
        no debería exigir.

        No se comprueba que las fechas estén vigentes. Una ventana activada cuyo rango ya pasó
        es un estado coherente que la API ya modela: `GET /enrollment-periods/current` la
        devuelve con `is_active: true` e `is_open: false`, y quien decide si se puede inscribir
        es `is_open`. Rechazarlo aquí impediría además activar una ventana con unos minutos de
        adelanto o de retraso, que es un caso legítimo.

        Args:
            period_id: identificador de la ventana a abrir.

        Returns:
            La ventana, ya activa.

        Raises:
            PeriodNotFoundError: si la ventana no existe.
        """
        with self._uow:
            periodo = self._periods.find_by_id(period_id)

            if periodo is None:
                raise PeriodNotFoundError(period_id)

            if periodo.is_active:
                # Ya estaba abierta. No se escribe nada: un `UPDATE` que no cambia el valor
                # movería `updated_at` sin que hubiera pasado nada, y esa columna es un dato
                # de diagnóstico que debe reflejar cambios reales.
                return periodo

            anterior = self._periods.find_active()

            if anterior is not None:
                # PRIMERO desactivar. El índice único parcial se comprueba en cada sentencia,
                # así que el orden inverso fallaría con clave duplicada dentro de la propia
                # transacción.
                anterior.is_active = False
                self._periods.save(anterior)
                # `flush` antes de activar la nueva: sin él, SQLAlchemy podría reordenar las
                # dos escrituras al confirmar y el `UPDATE` de activación llegaría primero.
                self._uow.flush()

            periodo.is_active = True
            self._periods.save(periodo)
            self._uow.commit()

        return periodo
