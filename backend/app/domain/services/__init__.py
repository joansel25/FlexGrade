"""Servicios de dominio: reglas de negocio que no pertenecen a una sola entidad.

Existentes:

- `prerequisite_validator.py`: PrerequisiteValidator, verifica contra el historial académico
  que el estudiante haya aprobado todos los prerrequisitos directos de la materia.
- `corequisite_validator.py`: CorequisiteValidator, las dos caras de la regla de
  correquisitos: `validate` comprueba al inscribir que el estudiante curse a la vez lo que la
  materia exige a la vez, y `resolve_cancellation` impide que cancelar deje inscrita una
  materia sin el correquisito que exige. Trata aparte el bloque de materias unidas por
  correquisitos mutuos, que de otro modo sería imposible de inscribir y, al cancelar,
  imposible de abandonar.
- `schedule_conflict_detector.py`: ScheduleConflictDetector, determina si los bloques de
  horario de un grupo se solapan con los de las inscripciones activas del estudiante.

Son objetos sin estado que reciben todo lo que necesitan por parámetro: no consultan la base de
datos ni conocen repositorios. Eso los hace probables con datos en memoria, en milisegundos.

Existen separados y no dentro de `EnrollStudentUseCase` porque cada uno tiene su propia razón
para cambiar (`ARCHITECTURE.md` sección 5, principio S): la regla de prerrequisitos y la de
choque de horarios evolucionan por motivos distintos, y el caso de uso solo cambia si cambia el
flujo de orquestación.
"""
