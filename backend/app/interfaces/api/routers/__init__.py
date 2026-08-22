"""Routers de FastAPI: un módulo por recurso de la API.

Contiene hoy `health.py` (liveness check de la Fase 0). En las fases siguientes se sumarán
`auth.py`, `students.py`, `courses.py`, `enrollments.py`, `periods.py` y `admin.py`, todos
registrados bajo el prefijo `API_V1_PREFIX` según el contrato de `docs/API.md`.

Cada router declara sus rutas y delega en un caso de uso. Ninguno consulta la base de datos ni
resuelve reglas de negocio: si un endpoint necesita decidir algo, esa decisión pertenece al
dominio o a un caso de uso.
"""
