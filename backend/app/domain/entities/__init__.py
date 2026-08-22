"""Entidades del dominio: objetos con identidad propia y comportamiento de negocio.

Contendrá un módulo por entidad, según `matricula_docs/docs/DATA_MODEL.md`:

- `student.py`: Student, el perfil académico vinculado a un programa.
- `course.py`: Course, la materia del plan de estudios y sus prerrequisitos.
- `course_offering.py`: CourseOffering, la oferta de una materia en un período. Encapsula la
  invariante crítica de cupo (`reserve_slot`, `release_slot`, `can_accept_enrollment`) y el
  campo `version` del bloqueo optimista.
- `enrollment.py`: Enrollment, la inscripción de un estudiante en un grupo (ENROLLED,
  CANCELLED, WAITLISTED).
- `enrollment_period.py`: EnrollmentPeriod, la ventana temporal de matrícula.

Las entidades **no** heredan de `Base` de SQLAlchemy: el mapeo a la base de datos vive en
`app.infrastructure.persistence.sqlalchemy` y los repositorios traducen entre ambos mundos.
"""
