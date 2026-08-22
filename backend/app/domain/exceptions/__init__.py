"""Excepciones del dominio: cada regla de negocio violada tiene su excepción específica.

Contendrá:

- `capacity_exceeded.py`: el grupo ya no tiene cupo disponible.
- `prerequisites_not_met.py`: el estudiante no ha aprobado los prerrequisitos de la materia.
- `schedule_conflict.py`: el horario del grupo choca con otra inscripción activa.
- `already_enrolled.py`: el estudiante ya está inscrito en ese grupo en el período vigente.

Nunca se lanza `Exception` genérica. La capa de `interfaces` traduce estas excepciones a
códigos HTTP mediante un handler centralizado; el dominio no conoce esa traducción.
"""
