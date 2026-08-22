"""Value objects: valores inmutables, sin identidad, que se comparan por su contenido.

Contendrá:

- `student_code.py`: StudentCode, el código institucional del estudiante con su validación de
  formato.
- `course_code.py`: CourseCode, el código de la materia (ej. "MAT101").
- `schedule_block.py`: ScheduleBlock, un bloque de horario (día, hora de inicio, hora de fin)
  capaz de responder si se solapa con otro. Es la pieza que sostiene la detección de choque de
  horarios.

Se implementan como dataclasses congeladas (`frozen=True`) que validan sus invariantes en la
construcción: un value object inválido nunca debe llegar a existir.
"""
