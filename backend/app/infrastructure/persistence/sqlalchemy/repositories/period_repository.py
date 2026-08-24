"""Adaptador de `PeriodRepository` sobre SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.dtos.pagination import Page
from app.application.ports.repositories.period_repository import PeriodRepository
from app.domain.entities.enrollment_period import EnrollmentPeriod
from app.infrastructure.persistence.sqlalchemy.models.enrollment_period import EnrollmentPeriodModel


class SQLAlchemyPeriodRepository(PeriodRepository):
    """Implementación del puerto de períodos de matrícula contra PostgreSQL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_active(self) -> EnrollmentPeriod | None:
        # `scalar_one_or_none` y no `first()`: si alguna vez hubiera dos períodos activos, es
        # preferible un error ruidoso a devolver uno al azar y mostrar en silencio la oferta
        # del semestre equivocado. El índice único parcial `ix_enrollment_periods_active`
        # hace que ese estado no pueda existir, así que esta llamada no puede fallar por esa
        # causa; la elección del método deja la intención escrita en el código.
        sentencia = select(EnrollmentPeriodModel).where(EnrollmentPeriodModel.is_active.is_(True))
        modelo = self._session.execute(sentencia).scalar_one_or_none()
        return self._a_entidad(modelo) if modelo is not None else None

    def find_by_id(self, period_id: UUID) -> EnrollmentPeriod | None:
        modelo = self._session.get(EnrollmentPeriodModel, period_id)
        return self._a_entidad(modelo) if modelo is not None else None

    def find_by_code(self, code: str) -> EnrollmentPeriod | None:
        sentencia = select(EnrollmentPeriodModel).where(EnrollmentPeriodModel.code == code)
        modelo = self._session.execute(sentencia).scalar_one_or_none()
        return self._a_entidad(modelo) if modelo is not None else None

    def list_all(self, *, page: int, size: int) -> Page[EnrollmentPeriod]:
        total = self._session.execute(
            select(func.count()).select_from(EnrollmentPeriodModel)
        ).scalar_one()

        sentencia = (
            select(EnrollmentPeriodModel)
            .order_by(EnrollmentPeriodModel.starts_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        periodos = [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

        return Page(items=periodos, total=total, page=page, size=size)

    def save(self, period: EnrollmentPeriod) -> None:
        modelo = self._session.get(EnrollmentPeriodModel, period.id)

        if modelo is None:
            self._session.add(self._a_modelo(period))
            return

        modelo.code = period.code
        modelo.academic_period = period.academic_period
        modelo.name = period.name
        modelo.starts_at = period.starts_at
        modelo.ends_at = period.ends_at
        modelo.is_active = period.is_active

    @staticmethod
    def _a_modelo(period: EnrollmentPeriod) -> EnrollmentPeriodModel:
        """Convierte la entidad del dominio en el modelo ORM.

        `created_at` no se asigna: lo gestiona la base con su `DEFAULT NOW()`.
        """
        return EnrollmentPeriodModel(
            id=period.id,
            code=period.code,
            academic_period=period.academic_period,
            name=period.name,
            starts_at=period.starts_at,
            ends_at=period.ends_at,
            is_active=period.is_active,
        )

    @staticmethod
    def _a_entidad(modelo: EnrollmentPeriodModel) -> EnrollmentPeriod:
        """Convierte el modelo ORM en la entidad del dominio."""
        return EnrollmentPeriod(
            id=modelo.id,
            code=modelo.code,
            academic_period=modelo.academic_period,
            name=modelo.name,
            starts_at=modelo.starts_at,
            ends_at=modelo.ends_at,
            is_active=modelo.is_active,
            created_at=modelo.created_at,
        )
