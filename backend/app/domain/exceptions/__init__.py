"""Excepciones del dominio: cada regla de negocio violada tiene su excepción específica.

Existentes:

- `base.py`: DomainError, la raíz de la jerarquía. Nunca se lanza directamente.
- `invalid_value.py`: los value objects rechazando un valor que viola su invariante
  (`InvalidEmailError`, `InvalidStudentCodeError`, `InvalidCourseCodeError`,
  `InvalidScheduleBlockError`).
- `authentication.py`: credenciales inválidas, cuenta desactivada, token inválido y cuenta
  sin perfil de estudiante.
- `catalog.py`: materia o grupo inexistentes, y ausencia de período de matrícula activo.

Pendientes de la Fase 3:

- `capacity_exceeded.py`: el grupo ya no tiene cupo disponible.
- `prerequisites_not_met.py`: el estudiante no ha aprobado los prerrequisitos de la materia.
- `schedule_conflict.py`: el horario del grupo choca con otra inscripción activa.
- `already_enrolled.py`: el estudiante ya está inscrito en ese grupo en el período vigente.

Nunca se lanza `Exception` genérica. La capa de `interfaces` traduce estas excepciones a
códigos HTTP mediante un handler centralizado; el dominio no conoce esa traducción.
"""
