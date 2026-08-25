"""Servicio de dominio: validación de prerrequisitos."""

from __future__ import annotations

from uuid import UUID

from app.domain.entities.course import Course
from app.domain.exceptions.enrollment import PrerequisitesNotMetError


class PrerequisiteValidator:
    """Comprueba que el estudiante haya aprobado lo que la materia exige.

    Es un objeto sin estado y recibe todo por parámetro: no consulta la base de datos ni conoce
    repositorios. Quien lo llama trae las materias exigidas y las que el estudiante aprobó, y
    este servicio se limita a decidir. Eso lo hace comprobable con datos en memoria y le da una
    única razón para cambiar: que cambie la regla de prerrequisitos.

    Compara **prerrequisitos directos**, no el cierre transitivo. Si `MAT201` exige `MAT102` y
    esta a su vez `MAT101`, para inscribir `MAT201` basta con tener aprobada `MAT102`. No es una
    simplificación: si el estudiante aprobó `MAT102`, la institución ya validó en su momento que
    cumplía lo anterior. Recorrer la cadena entera volvería a exigir materias que pudieron ser
    homologadas o cursadas bajo otro plan de estudios.
    """

    def missing(
        self,
        *,
        required: list[Course],
        approved_course_ids: set[UUID],
    ) -> list[str]:
        """Devuelve los códigos de los prerrequisitos que faltan por aprobar.

        Es la regla en su forma consultable, y `validate` no es más que esto seguido de un
        `raise`. Están separados porque tienen dos consumidores con necesidades opuestas: la
        inscripción quiere que falle, y el semáforo del plan quiere saber qué falta en cada una
        de las decenas de materias del plan sin provocar una excepción por cada una.

        Compartir implementación no es una comodidad, es el requisito de la iteración 6.3: el
        semáforo pinta lo que la inscripción va a decidir, y dos copias de la misma regla
        acaban discrepando el día que una de las dos cambia.

        Args:
            required: prerrequisitos directos de la materia.
            approved_course_ids: identificadores de las materias que el estudiante tiene
                aprobadas. Se recibe como conjunto porque la comprobación es de pertenencia y
                el historial de alguien avanzado puede tener decenas de entradas.

        Returns:
            Los códigos que faltan, ORDENADOS. Un orden que cambia solo porque cambió el de la
            consulta hace imposible probar la respuesta y confunde a quien la lee dos veces.
            Vacío si no falta ninguno.
        """
        return sorted(
            materia.code.value for materia in required if materia.id not in approved_course_ids
        )

    def validate(
        self,
        *,
        course_id: UUID,
        required: list[Course],
        approved_course_ids: set[UUID],
    ) -> None:
        """Verifica que no falte ningún prerrequisito.

        Args:
            course_id: materia que se quiere inscribir.
            required: prerrequisitos directos de esa materia.
            approved_course_ids: identificadores de las materias que el estudiante tiene
                aprobadas.

        Raises:
            PrerequisitesNotMetError: si falta alguno. El error lleva los **códigos** de las
                materias que faltan, no solo un aviso: el estudiante necesita saber qué le
                falta para poder hacer algo al respecto.
        """
        faltantes = self.missing(required=required, approved_course_ids=approved_course_ids)

        if faltantes:
            raise PrerequisitesNotMetError(course_id, faltantes)
