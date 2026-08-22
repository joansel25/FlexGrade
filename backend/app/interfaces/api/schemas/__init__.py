"""Schemas Pydantic de request y response de la API.

Contendrá `auth_schemas.py`, `student_schemas.py`, `enrollment_schemas.py` y `error_schemas.py`
(formato uniforme de error que documenta `docs/API.md`).

Los schemas viven exclusivamente en esta capa: validan y serializan el borde HTTP. No se usan
como entidades del dominio ni como DTOs de la capa de aplicación, aunque a veces se parezcan;
mezclarlos acoplaría el modelo de negocio al contrato público de la API.
"""
