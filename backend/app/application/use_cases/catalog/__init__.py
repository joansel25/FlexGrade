"""Casos de uso del catálogo académico (Fase 2).

Contendrá:

- `list_courses.py`: ListCoursesUseCase, listado paginado de materias.
- `get_course_offerings.py`: GetCourseOfferingsUseCase, grupos de una materia en el período
  activo.
- `get_offering_detail.py`: GetOfferingDetailUseCase, detalle de un grupo con sus bloques de
  horario.

Son las consultas de mayor frecuencia durante el pico de matrícula: se apoyan en el puerto
`CacheService` con TTL corto. La disponibilidad exacta de cupos nunca se sirve desde caché.
"""
