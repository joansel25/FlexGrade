"""Casos de uso de inscripción (Fase 3): el corazón del sistema.

Contendrá:

- `enroll_student.py`: EnrollStudentUseCase, el caso de uso crítico. Valida período activo,
  prerrequisitos, choque de horario e inscripción duplicada, y descuenta el cupo dentro de una
  transacción (`UnitOfWork`) con bloqueo optimista y reintentos limitados.
- `cancel_enrollment.py`: CancelEnrollmentUseCase, cancela una inscripción y libera el cupo.
- `get_student_schedule.py`: GetStudentScheduleUseCase, horario consolidado del estudiante.

Estos casos de uso orquestan; las reglas viven en `app.domain.services` y en los métodos de las
entidades (`CourseOffering.reserve_slot`, `Enrollment.cancel`).
"""
