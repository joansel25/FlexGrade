"""Casos de uso del catálogo académico (Fase 2).

Existentes:

- `list_courses.py`: ListCoursesUseCase, listado paginado de materias con filtros por
  programa, semestre y texto libre.
- `get_course_detail.py`: GetCourseDetailUseCase, materia junto a sus prerrequisitos directos.
- `get_course_offerings.py`: GetCourseOfferingsUseCase, grupos de una materia en el período
  activo.
- `get_offering_detail.py`: GetOfferingDetailUseCase, detalle de un grupo con su docente y sus
  bloques de horario.
- `get_current_period.py`: GetCurrentPeriodUseCase, ventana de matrícula vigente con su cuenta
  atrás.

Son las consultas de mayor frecuencia durante el pico de matrícula. Se apoyarán en el puerto
`CacheService` con TTL corto a partir de la iteración 2.4. La disponibilidad exacta de cupos
nunca se sirve desde caché.
"""
