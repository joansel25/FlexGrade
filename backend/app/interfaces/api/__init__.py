"""API REST del sistema, construida con FastAPI.

Contiene `main.py` (creación de la aplicación y registro de routers, es el entrypoint del
contenedor: `uvicorn app.interfaces.api.main:app`) y contendrá los subpaquetes `routers`,
`schemas` y `dependencies`.

Los routers son delgados: validan el request con un schema Pydantic, invocan un caso de uso
inyectado y traducen las excepciones del dominio a códigos HTTP.
"""
