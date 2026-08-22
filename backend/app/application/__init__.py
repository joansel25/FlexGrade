"""Capa de aplicación: orquesta el dominio y declara los contratos con el mundo exterior.

Contendrá los subpaquetes:

- `use_cases`: un caso de uso por operación del sistema. Orquesta, pero no decide: las reglas
  viven en el dominio.
- `ports`: interfaces abstractas (ABC) que la infraestructura implementa.
- `dtos`: estructuras planas para transportar datos entre capas.

Esta capa depende únicamente de `app.domain`. No importa SQLAlchemy, Redis, FastAPI ni ningún
módulo de `app.infrastructure` o `app.interfaces`: recibe sus dependencias como abstracciones
por el constructor.
"""
