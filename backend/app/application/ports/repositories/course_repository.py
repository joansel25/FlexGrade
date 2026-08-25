"""Puerto de persistencia del agregado Course."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.application.dtos.pagination import Page
from app.domain.entities.course import Course
from app.domain.entities.course_requirement import CourseRequirement
from app.domain.value_objects.course_code import CourseCode


class CourseRepository(ABC):
    """Contrato de acceso al catálogo de materias."""

    @abstractmethod
    def find_by_id(self, course_id: UUID) -> Course | None:
        """Recupera una materia por su identificador.

        Args:
            course_id: identificador de la materia.

        Returns:
            La materia, o `None` si no existe.
        """

    @abstractmethod
    def find_by_code(self, code: CourseCode) -> Course | None:
        """Recupera una materia por su código institucional.

        Args:
            code: código de la materia (por ejemplo `MAT101`).

        Returns:
            La materia, o `None` si no existe.
        """

    @abstractmethod
    def find_by_ids(self, course_ids: Sequence[UUID]) -> dict[UUID, Course]:
        """Recupera varias materias de una vez, indexadas por identificador.

        Existe para componer el horario del estudiante: se tienen los grupos y hace falta el
        código y el nombre de cada materia. Pedirlas una a una sería un N+1 sobre una consulta
        que el estudiante abre constantemente durante la matrícula.

        Devuelve un diccionario y no una lista porque quien llama va a buscarlas por
        identificador, no a recorrerlas.

        Args:
            course_ids: identificadores de las materias.

        Returns:
            Las materias encontradas. Los identificadores inexistentes se omiten.
        """

    @abstractmethod
    def find_requirements(self, course_id: UUID, program_id: UUID) -> list[CourseRequirement]:
        """Recupera lo que una materia exige DENTRO de un plan de estudios concreto.

        El programa no es un filtro opcional, es parte de la pregunta. Un requisito académico
        no une dos materias, une dos materias **dentro de una carrera**: la misma `FIS101`
        puede exigir `MAT101` en Ingeniería y no exigir nada en un plan donde entra como
        electiva. Preguntar «qué exige FIS101» sin decir en qué plan no tiene una única
        respuesta correcta.

        Devuelve prerrequisitos y correquisitos juntos, en una sola consulta, porque quien
        valida una inscripción necesita los dos y separarlos en dos métodos duplicaría el
        viaje a la base de datos dentro de la transacción más disputada del sistema. Quien
        solo quiera unos filtra por `requirement_type`.

        Son solo los requisitos **directos**, no el cierre transitivo: si B exige A y C exige
        B, consultar los de C devuelve solo B. Es lo que valida `PrerequisiteValidator`, y su
        docstring explica por qué recorrer la cadena entera sería incorrecto.

        Args:
            course_id: identificador de la materia.
            program_id: plan de estudios sobre el que se pregunta.

        Returns:
            Los requisitos directos ordenados por código, o una lista vacía si no tiene.
        """

    @abstractmethod
    def find_mutual_corequisites(self, course_id: UUID, program_id: UUID) -> set[UUID]:
        """Recupera las materias con las que esta forma bloque de correquisitos mutuos.

        Una materia devuelta aquí cumple las dos direcciones a la vez: `course_id` la exige
        como correquisito y ella exige a `course_id`. Es el caso de la teoría y su
        laboratorio, que se cursan juntos.

        Existe como consulta propia y no se resuelve pidiendo los requisitos de cada
        correquisito porque eso sería una consulta por materia exigida —un N+1— dentro de la
        transacción de inscripción. Aquí es una sola sentencia con un autojoin.

        Lo usa `CorequisiteValidator`: a estas materias no se les exige estar ya inscritas,
        porque son exactamente las que producirían un bloqueo circular en el que ninguna de
        las dos podría entrar nunca.

        Args:
            course_id: identificador de la materia.
            program_id: plan de estudios sobre el que se pregunta.

        Returns:
            Los identificadores de las materias del bloque, o un conjunto vacío.
        """

    @abstractmethod
    def belongs_to_program(self, course_id: UUID, program_id: UUID) -> bool:
        """Indica si la materia forma parte del plan de estudios de un programa.

        Es lo que sostiene el `403 COURSE_NOT_IN_PROGRAM` de `API.md`: un estudiante de Derecho
        no debe poder inscribir Programación II, aunque la materia exista y tenga cupo.

        Args:
            course_id: identificador de la materia.
            program_id: programa contra el que comprobar.

        Returns:
            `True` si la materia está en ese plan de estudios.
        """

    @abstractmethod
    def search(
        self,
        *,
        page: int,
        size: int,
        program_id: UUID | None = None,
        semester: int | None = None,
        search: str | None = None,
    ) -> Page[Course]:
        """Busca materias del catálogo aplicando los filtros de `GET /courses`.

        Los filtros son acumulativos y todos opcionales: sin ninguno devuelve el catálogo
        completo paginado.

        Args:
            page: número de página, empezando en 1.
            size: cuántas materias por página.
            program_id: si se indica, solo las materias del plan de estudios de ese programa.
            semester: si se indica, solo las materias cuyo semestre sugerido coincida. Depende
                del plan de estudios, así que solo tiene sentido junto a `program_id`; sin él,
                filtra por las materias que estén sugeridas en ese semestre en cualquier plan.
            search: si se indica, busca el texto en el nombre o en el código de la materia,
                sin distinguir mayúsculas.

        Returns:
            La página de resultados y el total de coincidencias.
        """

    @abstractmethod
    def find_study_plan(self, program_id: UUID) -> list[tuple[Course, int, bool]]:
        """Recupera el plan de estudios completo de un programa.

        Devuelve cada materia junto con su semestre sugerido y si es obligatoria, porque esos
        dos datos NO son de la materia sino de su relación con el programa: la misma materia
        puede ser de primer semestre y obligatoria en una carrera, y de tercero y electiva en
        otra. Por eso la entidad `Course` no los lleva.

        Sin paginar, al contrario que `search`. Un plan tiene decenas de materias y su valor
        está en verse entero: responde «qué me falta para graduarme», y eso no se contesta de
        veinte en veinte.

        Args:
            program_id: programa cuyo plan se consulta.

        Returns:
            Tríos de materia, semestre sugerido y obligatoriedad, ordenados por semestre y
            luego por código. Vacío si el programa no tiene plan cargado.
        """

    @abstractmethod
    def save(self, course: Course) -> None:
        """Persiste una materia nueva o los cambios de una existente.

        No confirma la transacción: eso le corresponde a la `UnitOfWork` del caso de uso, que
        es quien sabe si la operación completa terminó bien.

        Args:
            course: la materia a persistir.
        """
