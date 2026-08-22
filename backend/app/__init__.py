"""Paquete raíz del backend del Sistema de Matrícula Académica.

Organiza el código en las cuatro capas de la arquitectura hexagonal descritas en
`matricula_docs/docs/ARCHITECTURE.md`:

- `domain`: entidades, value objects, servicios y excepciones de negocio. No conoce a nadie.
- `application`: casos de uso, puertos (interfaces) y DTOs. Solo conoce a `domain`.
- `infrastructure`: adaptadores de salida (SQLAlchemy, Redis, JWT, SMTP, configuración).
- `interfaces`: adaptadores de entrada (API REST con FastAPI).

Regla de dependencias: las flechas apuntan siempre hacia el centro. Ni `domain` ni
`application` importan nada de `infrastructure` ni de `interfaces`.
"""
