"""Servicio de dominio: comprueba que un requisito nuevo deje el plan cursable.

Un plan de estudios es un grafo dirigido: cada arista dice «para ver esta materia hace falta
aquella». Casi cualquier arista es legítima, pero **un ciclo que contenga al menos un
prerrequisito hace imposible cursar todas las materias que lo forman**, y nada en el sistema
avisaría.

`MAT101` exige `MAT102` como prerrequisito y `MAT102` exige `MAT101`: para inscribir la
primera hay que haber aprobado la segunda, y para aprobar la segunda hay que haber inscrito la
primera. Las dos quedan ininscribibles para siempre. La base las acepta —cada fila es válida por
separado—, `PrerequisiteValidator` las rechaza una a una sin poder decir por qué, y el semáforo
las pinta bloqueadas sin salida. El error solo se descubre cuando un estudiante se queda
atascado, meses después de que alguien cargara el plan.

**Un ciclo de correquisitos SÍ es legítimo** y por eso la regla no habla de ciclos a secas.
«`FIS101` y `LAB101` se cursan juntas» es un ciclo mutuo, es la forma normal de decir que dos
materias van en bloque, y la iteración 6.2 construyó la exención que lo hace inscribible. Lo que
no se puede satisfacer es mezclar: si en la vuelta hay un prerrequisito, alguna materia tendría
que estar aprobada antes de poder cursarse.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.entities.course import Course
from app.domain.entities.course_requirement import CourseRequirement
from app.domain.exceptions.admin import ImpossibleRequirementCycleError
from app.domain.value_objects.requirement_type import RequirementType


class RequirementGraph:
    """Decide si una arista nueva deja el plan cursable."""

    @staticmethod
    def ensure_satisfiable(
        *,
        course: Course,
        required: Course,
        requirement_type: RequirementType,
        existing: dict[UUID, list[CourseRequirement]],
    ) -> None:
        """Comprueba que añadir el requisito no cierre un ciclo imposible de satisfacer.

        Args:
            course: la materia que impone el requisito.
            required: la materia exigida.
            requirement_type: cómo se exige.
            existing: los requisitos que YA tiene el plan, indexados por materia que los impone.
                Se pasan enteros porque el ciclo puede cerrarse a varias aristas de distancia:
                mirar solo la pareja detectaría `A→B→A` y no `A→B→C→A`.

        Raises:
            ImpossibleRequirementCycleError: si el requisito cierra un ciclo con al menos un
                prerrequisito. Lleva la vuelta completa, porque saber que «hay un ciclo» no dice
                cuál de las aristas quitar.
        """
        if course.id == required.id:
            # Se comprueba aquí y no solo con el CHECK de la base para poder nombrar la materia.
            raise ImpossibleRequirementCycleError(cycle=[course.code.value, course.code.value])

        # Se busca el camino de vuelta: desde la materia EXIGIDA hasta la que exige. Si existe,
        # la arista nueva lo cierra en ciclo.
        vuelta = RequirementGraph._camino(
            desde=required.id, hasta=course.id, aristas=existing, visitadas=set()
        )

        if vuelta is None:
            return

        # `vuelta` son las aristas de required -> ... -> course. La nueva cierra course -> required.
        hay_prerrequisito = requirement_type is RequirementType.PREREQUISITE or any(
            r.is_prerequisite() for r in vuelta
        )

        if not hay_prerrequisito:
            # Ciclo de puros correquisitos: es el bloque que se cursa junto, y la exención de
            # pares mutuos de la 6.2 lo hace inscribible.
            return

        raise ImpossibleRequirementCycleError(
            # La vuelta ya termina en la materia que exige, así que el ciclo se lee entero:
            # A -> B -> ... -> A. Repetir el primer código al final no es redundante; es lo que
            # permite verlo como una vuelta y no como una lista.
            cycle=[course.code.value, required.code.value]
            + [r.course.code.value for r in vuelta],
        )

    @staticmethod
    def _camino(
        *,
        desde: UUID,
        hasta: UUID,
        aristas: dict[UUID, list[CourseRequirement]],
        visitadas: set[UUID],
    ) -> list[CourseRequirement] | None:
        """Devuelve los requisitos que llevan de una materia a otra, o `None` si no hay camino.

        Recorrido en profundidad. `visitadas` corta los ciclos que YA existieran en el plan: sin
        él la recursión no terminaría, y un plan cargado a mano puede traerlos.
        """
        if desde in visitadas:
            return None

        visitadas.add(desde)

        for requisito in aristas.get(desde, []):
            if requisito.course.id == hasta:
                return [requisito]

            resto = RequirementGraph._camino(
                desde=requisito.course.id, hasta=hasta, aristas=aristas, visitadas=visitadas
            )

            if resto is not None:
                return [requisito] + resto

        return None
