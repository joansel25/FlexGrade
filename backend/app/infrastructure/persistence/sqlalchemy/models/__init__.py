"""Modelos ORM: el mapeo de las tablas descritas en el DDL de `docs/DATA_MODEL.md`.

Un módulo por tabla. La Fase 1 (autenticación) cubre las cuatro primeras: `users`, `programs`,
`students` y `administrators`. Las del catálogo académico (`courses`, `course_prerequisites`,
`program_courses`, `professors`), las de la oferta del semestre (`enrollment_periods`,
`course_offerings`, `schedule_blocks`), `enrollments` y `academic_history` se incorporan en las
Fases 2 y 3, incluidos los elementos que sostienen el requisito no funcional central:
`course_offerings.version` (bloqueo optimista) y el `CHECK (enrolled_count <= total_capacity)`.

Aquí se declaran columnas, restricciones e índices. Estos modelos son **solo persistencia**: no
contienen lógica de negocio y no son las entidades del dominio; los repositorios traducen entre
modelo ORM y entidad.

Importar este paquete registra todos los modelos en `Base.metadata`. Ese es el contrato del que
depende `alembic/env.py`: un modelo que no se importe aquí queda fuera del `MetaData` y Alembic
lo leería como una tabla sobrante que debe borrar.
"""

from app.infrastructure.persistence.sqlalchemy.models.administrator import AdministratorModel
from app.infrastructure.persistence.sqlalchemy.models.base import Base
from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel

__all__ = [
    "AdministratorModel",
    "Base",
    "ProgramModel",
    "StudentModel",
    "UserModel",
]
