"""DTOs: estructuras planas para transportar datos entre capas.

Existentes:

- `auth_dto.py`: el contenido verificado de un token, el par de tokens y el resultado del
  login.
- `pagination.py`: Page, el contenedor de resultados paginados que comparten todos los
  listados, con los límites de tamaño de página.

Pendientes:

- `course_dto.py`: CourseDTO y OfferingDTO, proyecciones del catálogo (Fase 2).
- `enrollment_dto.py`: EnrollmentDTO, resultado de inscribir o consultar una inscripción
  (Fase 3).

Se implementan como dataclasses sin comportamiento. No sustituyen a las entidades (que son
ricas en lógica y no se serializan directamente) ni a los schemas Pydantic de la capa de API
(que validan y serializan el request/response HTTP).
"""
