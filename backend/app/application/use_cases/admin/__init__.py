"""Casos de uso de administración académica (Fase 4).

Existentes:

- `create_enrollment_period.py`: CreateEnrollmentPeriodUseCase, registra una ventana de
  matrícula, siempre desactivada.
- `activate_enrollment_period.py`: ActivateEnrollmentPeriodUseCase, abre una ventana y cierra
  la anterior en la misma transacción y en ese orden, porque el índice único parcial rechaza
  el estado intermedio con dos activas.
- `list_enrollment_periods.py`: ListEnrollmentPeriodsUseCase, listado paginado.
- `create_course.py`: CreateCourseUseCase, alta de una materia del catálogo.
- `create_course_offering.py`: CreateCourseOfferingUseCase, apertura de un grupo en el período
  activo, con su horario.
- `adjust_offering_capacity.py`: AdjustOfferingCapacityUseCase, ajuste de cupo con bloqueo
  optimista por `version` e invalidación de la caché del grupo.
- `generate_enrollment_report.py`: GenerateEnrollmentReportUseCase, cifras de matrícula del
  período activo y su desglose por programa.
- `generate_occupancy_report.py`: GenerateOccupancyReportUseCase, ocupación por grupo, paginada
  y ordenada del más lleno al más vacío.

Con estos dos reportes la Fase 4 queda completa. Los dos se calculan en vivo: ninguno se
cachea ni se precalcula, porque se consultan mientras la matrícula ocurre y una cifra vieja que
parece actual es peor que no tener el reporte.

Todos exigen rol ADMIN. La comprobación vive en la dependencia `AdminUserDep` y no en cada
caso de uso: el permiso es una cuestión del borde de la aplicación, no de la regla de negocio.
"""
