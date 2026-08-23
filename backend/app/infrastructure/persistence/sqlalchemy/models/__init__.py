"""Modelos ORM: el mapeo de las tablas descritas en el DDL de `docs/DATA_MODEL.md`.

Un módulo por tabla. La Fase 1 (autenticación) cubrió `users`, `programs`, `students` y
`administrators`. La Fase 2 añade el catálogo académico (`professors`, `courses`,
`program_courses`, `course_prerequisites`) y la oferta del semestre (`enrollment_periods`,
`course_offerings`, `schedule_blocks`), incluidos los dos elementos que sostienen el requisito
no funcional central: `course_offerings.version` (bloqueo optimista) y el
`CHECK (enrolled_count <= total_capacity)`. La Fase 3 cierra el esquema con `enrollments` y
`academic_history`.

Aquí se declaran columnas, restricciones e índices. Estos modelos son **solo persistencia**: no
contienen lógica de negocio y no son las entidades del dominio; los repositorios traducen entre
modelo ORM y entidad.

Importar este paquete registra todos los modelos en `Base.metadata`. Ese es el contrato del que
depende `alembic/env.py`: un modelo que no se importe aquí queda fuera del `MetaData` y Alembic
lo leería como una tabla sobrante que debe borrar.
"""

from app.infrastructure.persistence.sqlalchemy.models.academic_history import AcademicHistoryModel
from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.base import Base
from app.infrastructure.persistence.sqlalchemy.models.course import CourseModel
from app.infrastructure.persistence.sqlalchemy.models.course_offering import CourseOfferingModel
from app.infrastructure.persistence.sqlalchemy.models.course_prerequisite import (
    CoursePrerequisiteModel,
)
from app.infrastructure.persistence.sqlalchemy.models.enrollment import EnrollmentModel
from app.infrastructure.persistence.sqlalchemy.models.enrollment_period import EnrollmentPeriodModel
from app.infrastructure.persistence.sqlalchemy.models.professor import ProfessorModel
from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
from app.infrastructure.persistence.sqlalchemy.models.program_course import ProgramCourseModel
from app.infrastructure.persistence.sqlalchemy.models.schedule_block import ScheduleBlockModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel

__all__ = [
    "AcademicHistoryModel",
    "AdministratorModel",
    "Base",
    "CourseModel",
    "CourseOfferingModel",
    "CoursePrerequisiteModel",
    "EnrollmentModel",
    "EnrollmentPeriodModel",
    "ProfessorModel",
    "ProgramCourseModel",
    "ProgramModel",
    "ScheduleBlockModel",
    "StudentModel",
    "UserModel",
]
