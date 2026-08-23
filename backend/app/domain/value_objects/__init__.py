"""Value objects: valores inmutables, sin identidad, que se comparan por su contenido.

Existentes:

- `email.py`: Email, el correo institucional normalizado y validado.
- `user_role.py`: UserRole, el conjunto cerrado de roles (`STUDENT`, `ADMIN`).
- `student_code.py`: StudentCode, el código institucional del estudiante.
- `course_code.py`: CourseCode, el código de la materia (por ejemplo `MAT101`).
- `schedule_block.py`: ScheduleBlock, un bloque de horario (día, hora de inicio, hora de fin)
  capaz de responder si se solapa con otro. Es la pieza que sostiene la detección de choque de
  horarios.
- `enrollment_status.py`: EnrollmentStatus, el conjunto cerrado de estados de una inscripción.

Se implementan como dataclasses congeladas (`frozen=True`) que validan sus invariantes en la
construcción: un value object inválido nunca debe llegar a existir.
"""
