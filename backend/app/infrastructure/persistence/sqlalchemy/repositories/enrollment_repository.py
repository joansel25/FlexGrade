"""Adaptador de `EnrollmentRepository` sobre SQLAlchemy."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.ports.repositories.enrollment_repository import EnrollmentRepository
from app.domain.entities.enrollment import Enrollment
from app.domain.value_objects.enrollment_status import EnrollmentStatus
from app.domain.value_objects.grade import Grade
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.enrollment import EnrollmentModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel


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

    def find_ungraded_offerings(self, enrollment_period_id: UUID) -> list[UUID]:
        sentencia = (
            select(EnrollmentModel.course_offering_id)
            .where(EnrollmentModel.enrollment_period_id == enrollment_period_id)
            .where(EnrollmentModel.status == EnrollmentStatus.ENROLLED.value)
            .where(EnrollmentModel.final_grade.is_(None))
            .distinct()
        )

        return list(self._session.execute(sentencia).scalars())

    def count_ungraded(self, enrollment_period_id: UUID) -> int:
        sentencia = (
            select(func.count())
            .select_from(EnrollmentModel)
            .where(EnrollmentModel.enrollment_period_id == enrollment_period_id)
            .where(EnrollmentModel.status == EnrollmentStatus.ENROLLED.value)
            .where(EnrollmentModel.final_grade.is_(None))
        )

        return int(self._session.execute(sentencia).scalar_one())

    def find_graded_in_period(self, enrollment_period_id: UUID) -> list[Enrollment]:
        sentencia = (
            select(EnrollmentModel)
            .where(EnrollmentModel.enrollment_period_id == enrollment_period_id)
            .where(EnrollmentModel.status == EnrollmentStatus.ENROLLED.value)
            .where(EnrollmentModel.final_grade.is_not(None))
            .order_by(EnrollmentModel.enrolled_at)
        )

        return [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

    def find_by_offering(self, offering_id: UUID) -> list[Enrollment]:
        """Todas las inscripciones VIVAS de un grupo, para pasar lista y calificar.

        Filtra las canceladas: quien dio de baja la materia no la cursó, y sacarla en la lista
        del docente invitaría a calificar una fila que el dominio va a rechazar.

        Ordena por identificador de estudiante y no por nombre: el nombre lo resuelve el caso de
        uso, que es quien tiene los perfiles, y ordenar aquí por un dato que no está obligaría a
        un `JOIN` solo para eso.
        """
        sentencia = (
            select(EnrollmentModel)
            .where(EnrollmentModel.course_offering_id == offering_id)
            .where(EnrollmentModel.status == EnrollmentStatus.ENROLLED.value)
            .order_by(EnrollmentModel.enrolled_at)
        )

        return [self._a_entidad(m) for m in self._session.execute(sentencia).scalars()]

    def find_by_student_and_offering_any_status(
        self, student_id: UUID, offering_id: UUID
    ) -> Enrollment | None:
        """La inscripción de un estudiante en un grupo, ESTÉ COMO ESTÉ.

        Se distingue de `find_by_student_and_offering`, que solo devuelve las vivas. Calificar
        necesita ver también las canceladas: sin ellas, intentar calificar a quien se dio de
        baja respondería «no está inscrito», que suena a error de tecleo, en vez de «canceló la
        materia», que es lo que pasó.
        """
        sentencia = (
            select(EnrollmentModel)
            .where(EnrollmentModel.student_id == student_id)
            .where(EnrollmentModel.course_offering_id == offering_id)
            .order_by(EnrollmentModel.enrolled_at.desc())
            .limit(1)
        )
        modelo = self._session.execute(sentencia).scalar_one_or_none()

        return None if modelo is None else self._a_entidad(modelo)

    def count_active_in_program(
        self, *, course_id: UUID, program_id: UUID, enrollment_period_id: UUID
    ) -> int:
        # Se cuenta en la base y no en memoria: durante la matrícula una materia popular tiene
        # miles de inscripciones, y traerlas para medir su longitud es cargar el pico de tráfico
        # en el proceso para responder un número.
        sentencia = (
            select(func.count())
            .select_from(EnrollmentModel)
            .join(CourseOfferingModel, CourseOfferingModel.id == EnrollmentModel.course_offering_id)
            .join(StudentModel, StudentModel.id == EnrollmentModel.student_id)
            .where(CourseOfferingModel.course_id == course_id)
            .where(StudentModel.program_id == program_id)
            .where(EnrollmentModel.enrollment_period_id == enrollment_period_id)
            .where(EnrollmentModel.status == EnrollmentStatus.ENROLLED.value)
        )

        return int(self._session.execute(sentencia).scalar_one())

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
        modelo.final_grade = (
            None if enrollment.final_grade is None else enrollment.final_grade.value
        )
        modelo.graded_at = enrollment.graded_at

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
            final_grade=None if modelo.final_grade is None else Grade(modelo.final_grade),
            graded_at=modelo.graded_at,
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
