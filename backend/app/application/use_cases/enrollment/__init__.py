"""Casos de uso de inscripción (Fase 3).

Existentes:

- `enroll_student.py`: EnrollStudentUseCase, la operación crítica del sistema. Inscribe con
  bloqueo optimista y reintentos acotados, dentro de una transacción que abarca el descuento
  de cupo y la creación de la inscripción.

Pendientes:

- `cancel_enrollment.py`: CancelEnrollmentUseCase, libera el cupo y solo permite cancelar lo
  propio (iteración 3.4).
- `get_student_schedule.py`: GetStudentScheduleUseCase, el horario armado del estudiante en el
  período activo (iteración 3.4).

Aquí ocurre todo lo que el requisito no funcional del proyecto pone a prueba: 5.000 estudiantes
concurrentes durante unas pocas horas, compitiendo por los mismos cupos. El sobrecupo se impide
con tres defensas en capas —la invariante de la entidad, el bloqueo optimista y el CHECK de
PostgreSQL—, y ninguna sustituye a las otras.
"""
