"""Casos de uso de administración académica (Fase 4).

Existentes:

- `create_enrollment_period.py`: CreateEnrollmentPeriodUseCase, registra una ventana de
  matrícula, siempre desactivada.
- `activate_enrollment_period.py`: ActivateEnrollmentPeriodUseCase, abre una ventana y cierra
  la anterior en la misma transacción y en ese orden, porque el índice único parcial rechaza
  el estado intermedio con dos activas.
- `list_enrollment_periods.py`: ListEnrollmentPeriodsUseCase, listado paginado.

Pendientes:

- `create_course.py` y `create_course_offering.py`: alta de materias y de grupos.
- `adjust_offering_capacity.py`: ajuste de cupo con bloqueo optimista.
- `generate_enrollment_report.py` y el de ocupación.

Todos exigen rol ADMIN. La comprobación vive en la dependencia `AdminUserDep` y no en cada
caso de uso: el permiso es una cuestión del borde de la aplicación, no de la regla de negocio.
"""
