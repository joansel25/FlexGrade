"""Puertos de persistencia: un repositorio por agregado de `matricula_docs/docs/DATA_MODEL.md`.

Contendrá:

- `student_repository.py`: StudentRepository, con métodos como `find_by_id`,
  `find_by_student_code` y la consulta del historial académico aprobado que alimenta la
  validación de prerrequisitos.
- `course_repository.py`: CourseRepository, catálogo de materias y sus prerrequisitos.
- `offering_repository.py`: OfferingRepository, incluye `get_for_update` para cargar el grupo
  bajo control de concurrencia antes de descontar cupo.
- `enrollment_repository.py`: EnrollmentRepository, segregado en `EnrollmentReader`
  (`find_active_by_student`, `occupancy_by_offering`) y `EnrollmentWriter` (`save`, `cancel`),
  para que un caso de uso de solo lectura no dependa del contrato completo.
- `period_repository.py`: PeriodRepository, con `find_active` como consulta principal.

No hay un `IRepository[T]` genérico: esconde el lenguaje del dominio y obliga a filtrar en
memoria. Un repositorio nuevo implica un agregado nuevo; se verifica antes contra el modelo de
datos.
"""
