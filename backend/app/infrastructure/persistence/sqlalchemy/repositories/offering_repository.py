"""Adaptador de `OfferingRepository` sobre SQLAlchemy."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.application.ports.repositories.offering_repository import OfferingRepository
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.professor import Professor
from app.domain.value_objects.schedule_block import ScheduleBlock
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.professor import ProfessorModel
from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel


class SQLAlchemyOfferingRepository(OfferingRepository):
    """Implementación del puerto de grupos contra PostgreSQL.

    Devuelve siempre el grupo completo —con su docente y sus franjas de horario— y lo hace en
    un **número fijo de consultas**, independientemente de cuántos grupos se pidan: una trae
    los grupos, otra los docentes de todos ellos y otra las franjas de todos ellos. Recorrer
    los grupos preguntando por su horario uno a uno (el problema N+1) convertiría el endpoint
    más consultado del pico de matrícula en decenas de viajes a la base de datos.

    Se resuelve con consultas por lote en vez de con un `LEFT JOIN` deliberadamente: el join
    obligaría a tratar el docente como una columna que puede venir nula dentro de una fila
    tipada como si nunca lo fuera, y esa discrepancia entre lo declarado y lo real es
    justamente donde se esconden los `AttributeError` en producción.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, offering_id: UUID) -> CourseOffering | None:
        modelo = self._session.get(CourseOfferingModel, offering_id)

        if modelo is None:
            return None

        return self._a_entidad(
            modelo,
            docentes=self._docentes_de([modelo.professor_id]),
            horarios=self._horarios_de([modelo.id]),
        )

    def find_by_course_and_period(
        self, course_id: UUID, enrollment_period_id: UUID
    ) -> list[CourseOffering]:
        sentencia = (
            select(CourseOfferingModel)
            .where(CourseOfferingModel.course_id == course_id)
            .where(CourseOfferingModel.enrollment_period_id == enrollment_period_id)
            .order_by(CourseOfferingModel.group_number)
        )
        modelos = list(self._session.execute(sentencia).scalars())

        if not modelos:
            return []

        docentes = self._docentes_de([m.professor_id for m in modelos])
        horarios = self._horarios_de([m.id for m in modelos])

        return [self._a_entidad(m, docentes=docentes, horarios=horarios) for m in modelos]

    def find_by_ids(self, offering_ids: Sequence[UUID]) -> list[CourseOffering]:
        if not offering_ids:
            return []

        sentencia = (
            select(CourseOfferingModel)
            .where(CourseOfferingModel.id.in_(offering_ids))
            .order_by(CourseOfferingModel.group_number)
        )
        modelos = list(self._session.execute(sentencia).scalars())

        if not modelos:
            return []

        # Mismo patron que `find_by_course_and_period`: un numero fijo de consultas, sea cual
        # sea la cantidad de grupos.
        docentes = self._docentes_de([m.professor_id for m in modelos])
        horarios = self._horarios_de([m.id for m in modelos])

        return [self._a_entidad(m, docentes=docentes, horarios=horarios) for m in modelos]

    def try_reserve_slot(self, offering_id: UUID) -> bool:
        # UNA sola sentencia: comprueba la capacidad y descuenta el cupo a la vez. No hay
        # lectura previa, asi que no existe ventana entre comprobar y escribir.
        #
        # `enrolled_count + 1` se calcula en SQL, no en Python: dos transacciones que lean 39
        # y ambas escriban 40 produciran sobrecupo; dos que ordenen "incrementa en uno" no,
        # porque PostgreSQL serializa el acceso a la fila y la segunda parte del valor que la
        # primera dejo.
        sentencia = (
            update(CourseOfferingModel)
            .where(CourseOfferingModel.id == offering_id)
            .where(CourseOfferingModel.enrolled_count < CourseOfferingModel.total_capacity)
            .values(
                enrolled_count=CourseOfferingModel.enrolled_count + 1,
                version=CourseOfferingModel.version + 1,
            )
        )

        # `rowcount` es 1 si se aplico y 0 si el grupo estaba lleno o no existe. No hay tercer
        # caso: `id` es clave primaria y el WHERE no puede afectar a mas de una fila.
        return bool(self._session.execute(sentencia).rowcount == 1)

    def try_release_slot(self, offering_id: UUID) -> bool:
        sentencia = (
            update(CourseOfferingModel)
            .where(CourseOfferingModel.id == offering_id)
            .where(CourseOfferingModel.enrolled_count > 0)
            .values(
                enrolled_count=CourseOfferingModel.enrolled_count - 1,
                version=CourseOfferingModel.version + 1,
            )
        )

        return bool(self._session.execute(sentencia).rowcount == 1)

    def save(self, offering: CourseOffering) -> None:
        # Grupo y franjas en la misma llamada, dentro de la transacción de quien llama: un
        # grupo publicado sin su horario no es un estado que deba poder observarse.
        self._session.merge(
            CourseOfferingModel(
                id=offering.id,
                enrollment_period_id=offering.enrollment_period_id,
                course_id=offering.course_id,
                professor_id=None if offering.professor is None else offering.professor.id,
                group_number=offering.group_number,
                total_capacity=offering.total_capacity,
                enrolled_count=offering.enrolled_count,
                version=offering.version,
            )
        )

        for franja in offering.schedule:
            self._session.add(
                ScheduleBlockModel(
                    course_offering_id=offering.id,
                    day_of_week=franja.day_of_week,
                    start_time=franja.start_time,
                    end_time=franja.end_time,
                    classroom=franja.classroom,
                )
            )

    def update_capacity(
        self, offering_id: UUID, *, new_capacity: int, expected_version: int
    ) -> bool:
        sentencia = (
            update(CourseOfferingModel)
            .where(CourseOfferingModel.id == offering_id)
            # Bloqueo optimista por version: si otra operacion toco el grupo entre la lectura
            # y esta escritura, no se aplica nada y quien llama decide si reintentar.
            .where(CourseOfferingModel.version == expected_version)
            # Segunda condicion, y no es redundante con la comprobacion del caso de uso: entre
            # leer el grupo y escribirlo pueden entrar inscripciones nuevas. Sin ella el UPDATE
            # chocaria contra el CHECK (enrolled_count <= total_capacity) y abortaria la
            # transaccion entera en vez de devolver un fallo que se puede manejar.
            .where(CourseOfferingModel.enrolled_count <= new_capacity)
            .values(
                total_capacity=new_capacity,
                version=CourseOfferingModel.version + 1,
            )
        )

        return bool(self._session.execute(sentencia).rowcount == 1)

    def count_enrolled(self, offering_id: UUID) -> int | None:
        # Lectura mínima y siempre contra PostgreSQL: es el dato que nunca se cachea. Trae una
        # sola columna en vez de la fila entera porque se ejecuta en cada consulta de detalle
        # durante el pico.
        sentencia = select(CourseOfferingModel.enrolled_count).where(
            CourseOfferingModel.id == offering_id
        )
        return self._session.execute(sentencia).scalar_one_or_none()

    # ------------------------------------------------------------------ helpers

    def _docentes_de(self, professor_ids: Sequence[UUID | None]) -> dict[UUID, Professor]:
        """Trae en una sola consulta los docentes de todos los grupos indicados.

        Args:
            professor_ids: identificadores de docente, tal como vienen de los grupos. Se
                admiten `None` porque un grupo puede publicarse sin docente asignado.

        Returns:
            Los docentes indexados por identificador.
        """
        presentes = {pid for pid in professor_ids if pid is not None}

        if not presentes:
            return {}

        sentencia = select(ProfessorModel).where(ProfessorModel.id.in_(presentes))

        return {
            m.id: Professor(
                id=m.id,
                full_name=m.full_name,
                email=m.email,
                created_at=m.created_at,
            )
            for m in self._session.execute(sentencia).scalars()
        }

    def _horarios_de(self, offering_ids: Sequence[UUID]) -> dict[UUID, list[ScheduleBlock]]:
        """Trae en una sola consulta las franjas de todos los grupos indicados.

        Args:
            offering_ids: identificadores de los grupos.

        Returns:
            Las franjas agrupadas por grupo y ordenadas por día y hora. Es un `defaultdict`,
            así que un grupo sin horario publicado devuelve una lista vacía en vez de fallar.
        """
        agrupados: dict[UUID, list[ScheduleBlock]] = defaultdict(list)

        if not offering_ids:
            return agrupados

        sentencia = (
            select(ScheduleBlockModel)
            .where(ScheduleBlockModel.course_offering_id.in_(offering_ids))
            .order_by(ScheduleBlockModel.day_of_week, ScheduleBlockModel.start_time)
        )

        for modelo in self._session.execute(sentencia).scalars():
            agrupados[modelo.course_offering_id].append(
                ScheduleBlock(
                    day_of_week=modelo.day_of_week,
                    start_time=modelo.start_time,
                    end_time=modelo.end_time,
                    classroom=modelo.classroom,
                )
            )

        return agrupados

    @staticmethod
    def _a_entidad(
        modelo: CourseOfferingModel,
        *,
        docentes: dict[UUID, Professor],
        horarios: dict[UUID, list[ScheduleBlock]],
    ) -> CourseOffering:
        """Convierte el modelo ORM y sus datos asociados en la entidad del dominio."""
        return CourseOffering(
            id=modelo.id,
            enrollment_period_id=modelo.enrollment_period_id,
            course_id=modelo.course_id,
            group_number=modelo.group_number,
            total_capacity=modelo.total_capacity,
            enrolled_count=modelo.enrolled_count,
            version=modelo.version,
            professor=(
                docentes.get(modelo.professor_id) if modelo.professor_id is not None else None
            ),
            schedule=tuple(horarios.get(modelo.id, [])),
        )
