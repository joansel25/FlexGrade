"""Servicios de dominio: reglas de negocio que no pertenecen a una sola entidad.

Contendrá:

- `prerequisite_validator.py`: PrerequisiteValidator, verifica contra el historial académico
  que el estudiante haya aprobado todos los prerrequisitos de la materia.
- `schedule_conflict_detector.py`: ScheduleConflictDetector, determina si los bloques de
  horario de un grupo se solapan con los de las inscripciones activas del estudiante.

Son objetos sin estado que reciben todo lo que necesitan por parámetro: no consultan la base de
datos ni conocen repositorios. Eso los hace probables con datos en memoria.
"""
