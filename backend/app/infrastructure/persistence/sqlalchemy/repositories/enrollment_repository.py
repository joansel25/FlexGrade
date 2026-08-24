"""Adaptador de `EnrollmentRepository` sobre SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.repositories.enrollment_repository import EnrollmentRepository
from app.domain.entities.enrollment import Enrollment
from app.domain.value_objects.enrollment_status import EnrollmentStatus
from app.infrastructure.persistence.sqlalchemy.models.enrollment import EnrollmentModel


class SQLAlchemyEnrollmentRepository(EnrollmentRepository):
    """Implementación del puerto de inscripciones contra PostgreSQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------ lectura

    def find_by_id(self, enrollment_id: UUID) -> Enrollment | None:
        modelo = self._session.get(EnrollmentModel, enrollment_id)
        return self._a_entidad(modelo) if modelo is not None else None

    def find_active_by_student(
        self, student_id: UUID, enrollment_period_id: UUID
    ) -> list[Enrollment]:
        sentencia = (
            select(EnrollmentModel)
            .where(EnrollmentModel.student_id == student_id)
            .where(EnrollmentModel.enrollment_period_id == enrollment_period_id)
            .where(EnrollmentModel.status == EnrollmentStatus.ENROLLED.value)
            .order_by(EnrollmentModel.enrolled_at)
        )
        return [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

    def find_by_student_and_offering(
        self, student_id: UUID, course_offering_id: UUID, enrollment_period_id: UUID
    ) -> Enrollment | None:
        # Sin filtrar por estado: se busca la fila que ocupa la restricción UNIQUE, esté
        # activa o cancelada, para poder reactivarla en vez de intentar un INSERT que fallaría.
        sentencia = (
            select(EnrollmentModel)
            .where(EnrollmentModel.student_id == student_id)
            .where(EnrollmentModel.course_offering_id == course_offering_id)
            .where(EnrollmentModel.enrollment_period_id == enrollment_period_id)
        )
        modelo = self._session.execute(sentencia).scalar_one_or_none()
        return self._a_entidad(modelo) if modelo is not None else None

    # ----------------------------------------------------------------- escritura

    def save(self, enrollment: Enrollment) -> None:
        """Persiste la inscripción sin confirmar la transacción.

        El `commit` lo decide el `UnitOfWork`: confirmar aquí rompería la atomicidad con el
        descuento de cupo, que es justamente lo que esa frontera existe para garantizar.
        """
        modelo = self._session.get(EnrollmentModel, enrollment.id)

        if modelo is None:
            nuevo = self._a_modelo(enrollment)
            self._session.add(nuevo)

            # `flush` sin `commit`: envía el INSERT para que PostgreSQL aplique el
            # `DEFAULT NOW()` de `enrolled_at`, y devuelve esa marca a la entidad. Hace falta
            # porque el dominio deja deliberadamente esa fecha en manos de la base —es la
            # única fuente horaria fiable con varias instancias en marcha— y sin esta lectura
            # la respuesta de `POST /enrollments` saldría con `enrolled_at: null`, que es lo
            # contrario de lo que promete `API.md`.
            #
            # Sigue dentro de la transacción: si algo falla después, este INSERT se revierte
            # con todo lo demás.
            self._session.flush()
            self._session.refresh(nuevo, ["enrolled_at"])
            enrollment.enrolled_at = nuevo.enrolled_at
            return

        modelo.status = enrollment.status.value
        modelo.cancelled_at = enrollment.cancelled_at

    # ------------------------------------------------------------------ mapeo

    @staticmethod
    def _a_entidad(modelo: EnrollmentModel) -> Enrollment:
        """Convierte el modelo ORM en la entidad del dominio."""
        return Enrollment(
            id=modelo.id,
            student_id=modelo.student_id,
            course_offering_id=modelo.course_offering_id,
            enrollment_period_id=modelo.enrollment_period_id,
            status=EnrollmentStatus(modelo.status),
            enrolled_at=modelo.enrolled_at,
            cancelled_at=modelo.cancelled_at,
        )

    @staticmethod
    def _a_modelo(enrollment: Enrollment) -> EnrollmentModel:
        """Convierte la entidad del dominio en el modelo ORM.

        `enrolled_at` y `updated_at` no se asignan: los gestiona la base de datos con su
        `DEFAULT NOW()` y el trigger `trg_enrollments_updated_at`.
        """
        return EnrollmentModel(
            id=enrollment.id,
            student_id=enrollment.student_id,
            course_offering_id=enrollment.course_offering_id,
            enrollment_period_id=enrollment.enrollment_period_id,
            status=enrollment.status.value,
            cancelled_at=enrollment.cancelled_at,
        )
