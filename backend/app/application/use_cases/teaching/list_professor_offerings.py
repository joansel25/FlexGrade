"""Caso de uso: los grupos que dicta un docente en el período activo."""

from __future__ import annotations

from uuid import UUID

from app.application.dtos.teaching_dto import ProfessorOfferingDTO, ProfessorOfferingsDTO
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository


class ListProfessorOfferingsUseCase:
    """Compone la carga docente del período activo.

    Es la primera pantalla del docente y el cimiento de la 9.2: calificar se hace SOBRE un
    grupo, así que antes hay que poder decir cuáles son suyos.

    **El docente sale del token, nunca de la ruta.** Es la misma regla que separa
    `GET /students/me/study-plan` de `GET /admin/programs/{id}/plan`: si el identificador
    viajara en la URL, cualquier docente podría pedir la carga —y en la 9.2, las notas— de otro.
    No hay parámetro con el que pedir la de otra persona porque no existe tal parámetro.

    **Sin período activo devuelve una lista vacía, no un error.** Entre semestres no hay ventana
    abierta y eso es normal: un 404 diría que algo está roto cuando lo que pasa es que todavía
    no hay nada que dictar.
    """

    def __init__(
        self,
        offering_repository: OfferingRepository,
        course_repository: CourseRepository,
        period_repository: PeriodRepository,
    ) -> None:
        self._offerings = offering_repository
        self._courses = course_repository
        self._periods = period_repository

    def execute(self, professor_id: UUID) -> ProfessorOfferingsDTO:
        """Devuelve los grupos del docente en la ventana activa.

        Args:
            professor_id: perfil docente resuelto desde el token.

        Returns:
            Sus grupos con la materia ya resuelta, o una respuesta vacía si no hay período
            activo o no tiene carga este semestre.
        """
        periodo = self._periods.find_active()

        if periodo is None:
            return ProfessorOfferingsDTO(period_code=None, academic_period=None, offerings=[])

        grupos = self._offerings.find_by_professor(professor_id, periodo.id)

        if not grupos:
            return ProfessorOfferingsDTO(
                period_code=periodo.code,
                academic_period=periodo.academic_period,
                offerings=[],
            )

        # Una consulta para todas las materias, no una por grupo: un docente con seis grupos
        # son seis viajes a la base para pintar una lista.
        materias = self._courses.find_by_ids([g.course_id for g in grupos])

        return ProfessorOfferingsDTO(
            period_code=periodo.code,
            academic_period=periodo.academic_period,
            offerings=[
                ProfessorOfferingDTO(
                    offering=grupo,
                    course=materias[grupo.course_id],
                )
                for grupo in grupos
                # Un grupo cuya materia no está en el catálogo es un dato roto, no un caso a
                # mostrar: pintarlo sin nombre daría una fila que nadie sabe qué es.
                if grupo.course_id in materias
            ],
        )
