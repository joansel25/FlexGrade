"""Casos de uso de administración académica (Fase 4).

Existentes:

- `create_enrollment_period.py`: CreateEnrollmentPeriodUseCase, registra una ventana de
  matrícula, siempre desactivada.

Pendientes:

- `activate_enrollment_period.py`: activa una ventana y desactiva la anterior en la misma
  transacción, porque el índice único parcial rechazaría el estado intermedio con dos activas.
- `create_course.py` y `create_course_offering.py`: alta de materias y de grupos.
- `adjust_offering_capacity.py`: ajuste de cupo con bloqueo optimista.
- `generate_enrollment_report.py` y el de ocupación.

Todos exigen rol ADMIN. La comprobación vive en la dependencia `AdminUserDep` y no en cada
caso de uso: el permiso es una cuestión del borde de la aplicación, no de la regla de negocio.
"""
