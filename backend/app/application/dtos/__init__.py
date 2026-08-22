"""DTOs: estructuras planas para transportar datos entre capas.

Contendrá:

- `enrollment_dto.py`: EnrollmentDTO, resultado de inscribir o consultar una inscripción.
- `course_dto.py`: CourseDTO y OfferingDTO, proyecciones del catálogo.

Se implementan como dataclasses sin comportamiento. No sustituyen a las entidades (que son
ricas en lógica y no se serializan directamente) ni a los schemas Pydantic de la capa de API
(que validan y serializan el request/response HTTP).
"""
