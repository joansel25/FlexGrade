"""Caso de uso: dar de alta una materia en el catálogo."""

from __future__ import annotations

from uuid import uuid4

from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.domain.entities.course import Course
from app.domain.exceptions.admin import DuplicateCourseCodeError
from app.domain.value_objects.course_code import CourseCode


class CreateCourseUseCase:
    """Registra una materia nueva del catálogo académico.

    La materia es la definición —`Cálculo I`, 4 créditos—, no algo que se inscriba. Lo que se
    inscribe son sus grupos, que se crean aparte con `CreateCourseOfferingUseCase`: una materia
    recién creada no aparece en ninguna oferta hasta que alguien le abra un grupo, y eso es lo
    que permite preparar el catálogo de un semestre antes de decidir cuántos grupos tendrá.

    No se invalida la caché del catálogo al crear. Las entradas son por página y por filtro
    —`catalog:v1:courses:p=1:s=20:...`—, así que borrar la entrada de la materia nueva no
    serviría de nada: la que quedaría desactualizada es cada página del listado que pudiera
    contenerla, y no hay forma de enumerarlas. El TTL de 30-60 s las renueva solo, y una
    materia que tarda menos de un minuto en aparecer en el listado no es un problema: nadie
    puede inscribirla todavía porque aún no tiene grupos.
    """

    def __init__(self, course_repository: CourseRepository, unit_of_work: UnitOfWork) -> None:
        self._courses = course_repository
        self._uow = unit_of_work

    def execute(
        self,
        *,
        code: str,
        name: str,
        credits: int,
        description: str | None = None,
    ) -> Course:
        """Crea la materia.

        Args:
            code: código institucional (por ejemplo `MAT101`). Se normaliza a mayúsculas al
                construir el value object.
            name: nombre completo de la materia.
            credits: créditos que otorga; tiene que ser positivo.
            description: descripción del contenido, opcional.

        Returns:
            La materia creada.

        Raises:
            InvalidCourseCodeError: si el código no cumple el formato institucional.
            DuplicateCourseCodeError: si ya existe una materia con ese código.
        """
        # El value object valida el formato ANTES de tocar la base de datos, y de paso
        # normaliza el código: así `mat101` y `MAT101` no acaban siendo dos materias distintas
        # que la restricción UNIQUE no detectaría como duplicadas.
        codigo = CourseCode(code)

        with self._uow:
            # La restricción UNIQUE de `courses.code` también lo impediría, pero devolvería
            # «duplicate key value violates unique constraint», que no dice qué corregir.
            if self._courses.find_by_code(codigo) is not None:
                raise DuplicateCourseCodeError(codigo.value)

            materia = Course(
                id=uuid4(),
                code=codigo,
                name=name,
                credits=credits,
                description=description,
            )

            self._courses.save(materia)
            self._uow.commit()

        return materia
