"""Entidades del dominio: objetos con identidad propia y comportamiento de negocio.

Un módulo por entidad, según `matricula_docs/docs/DATA_MODEL.md`.

Existentes:

- `user.py`: User, la cuenta de autenticación y su rol.
- `student.py`: Student, el perfil académico vinculado a un programa.
- `program.py`: Program, el programa académico y su plan de estudios.
- `course.py`: Course, la materia del catálogo.
- `professor.py`: Professor, el docente al que se asigna un grupo.
- `enrollment_period.py`: EnrollmentPeriod, la ventana temporal de matrícula (`is_open`,
  `time_remaining_seconds`).
- `course_offering.py`: CourseOffering, la oferta de una materia en un período. Transporta el
  campo `version` del bloqueo optimista y encapsula la invariante de cupo (`reserve_slot`,
  `release_slot`, `can_accept_enrollment`).
- `enrollment.py`: Enrollment, la inscripción de un estudiante en un grupo (`create`, `cancel`,
  `reactivate`, `is_active`).
- `course_requirement.py`: CourseRequirement, una materia exigida por otra dentro de un plan
  de estudios, junto con la forma en que la exige.

Las entidades **no** heredan de `Base` de SQLAlchemy: el mapeo a la base de datos vive en
`app.infrastructure.persistence.sqlalchemy` y los repositorios traducen entre ambos mundos.
"""
