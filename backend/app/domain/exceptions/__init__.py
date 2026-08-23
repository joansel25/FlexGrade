"""Excepciones del dominio: cada regla de negocio violada tiene su excepción específica.

Existentes:

- `base.py`: DomainError, la raíz de la jerarquía. Nunca se lanza directamente.
- `invalid_value.py`: los value objects rechazando un valor que viola su invariante
  (`InvalidEmailError`, `InvalidStudentCodeError`, `InvalidCourseCodeError`,
  `InvalidScheduleBlockError`).
- `authentication.py`: credenciales inválidas, cuenta desactivada, token inválido y cuenta
  sin perfil de estudiante.
- `catalog.py`: materia o grupo inexistentes, y ausencia de período de matrícula activo.
- `enrollment.py`: todo lo que puede impedir una inscripción o una cancelación —cupo agotado,
  período cerrado, doble inscripción, prerrequisitos sin aprobar, choque de horario, materia
  fuera del plan de estudios— más los errores de cancelación. Se agrupan en un módulo y no en
  uno por excepción porque comparten contexto y se leen juntas.

Nunca se lanza `Exception` genérica. La capa de `interfaces` traduce estas excepciones a
códigos HTTP mediante un handler centralizado; el dominio no conoce esa traducción.
"""
