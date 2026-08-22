"""Capa de dominio: el núcleo del negocio, libre de frameworks e infraestructura.

Contendrá los subpaquetes:

- `entities`: agregados con comportamiento (Student, Course, CourseOffering, Enrollment,
  EnrollmentPeriod).
- `value_objects`: valores inmutables sin identidad (StudentCode, CourseCode, ScheduleBlock).
- `exceptions`: excepciones específicas de las reglas académicas.
- `services`: servicios de dominio con reglas que no pertenecen a una sola entidad.

Este paquete no importa SQLAlchemy, FastAPI, Pydantic, Redis ni ningún módulo de
`app.infrastructure` o `app.interfaces`. Sus pruebas corren en milisegundos, sin base de datos.
"""
