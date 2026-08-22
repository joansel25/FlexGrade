"""Casos de uso administrativos (Fase 4).

Contendrá:

- `create_enrollment_period.py`: CreateEnrollmentPeriodUseCase, abre una ventana de matrícula.
- `create_course_offering.py`: CreateCourseOfferingUseCase, crea un grupo con su cupo, profesor
  y bloques de horario.
- `generate_enrollment_report.py`: GenerateEnrollmentReportUseCase, reportes de inscripciones
  por programa y de ocupación por grupo.

La autorización por rol (solo ADMIN) se resuelve en las dependencias de la capa de interfaces;
estos casos de uso asumen que quien los invoca ya fue autorizado.
"""
