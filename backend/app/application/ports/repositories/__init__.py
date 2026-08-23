"""Puertos de persistencia: un repositorio por agregado de `matricula_docs/docs/DATA_MODEL.md`.

Existentes:

- `user_repository.py`: UserRepository, las cuentas de autenticación.
- `student_repository.py`: StudentRepository, los perfiles académicos.
- `program_repository.py`: ProgramRepository, los programas de la institución.
- `course_repository.py`: CourseRepository, el catálogo de materias, su búsqueda paginada y
  sus prerrequisitos directos.
- `offering_repository.py`: OfferingRepository, los grupos con su docente y su horario ya
  resueltos, más `count_enrolled` para leer el cupo ocupado sin pasar por la caché.
- `period_repository.py`: PeriodRepository, con `find_active` como consulta principal.

Pendiente de la Fase 3:

- `enrollment_repository.py`: EnrollmentRepository, segregado en `EnrollmentReader`
  (`find_active_by_student`, `occupancy_by_offering`) y `EnrollmentWriter` (`save`, `cancel`),
  para que un caso de uso de solo lectura no dependa del contrato completo. Incluirá el
  `get_for_update` que carga el grupo bajo control de concurrencia antes de descontar cupo, y
  la consulta del historial académico aprobado que alimenta la validación de prerrequisitos.

No hay un `IRepository[T]` genérico: esconde el lenguaje del dominio y obliga a filtrar en
memoria. Un repositorio nuevo implica un agregado nuevo; se verifica antes contra el modelo de
datos.
"""
