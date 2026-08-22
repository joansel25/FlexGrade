"""Capa de infraestructura: los adaptadores de salida que implementan los puertos.

Contendrá los subpaquetes:

- `persistence`: SQLAlchemy (sesión, modelos ORM, repositorios, unit of work).
- `cache`: adaptador de Redis.
- `auth`: adaptador de JWT y hash de contraseñas.
- `notifications`: adaptador de envío de notificaciones.
- `config`: configuración de la aplicación leída del entorno.

Aquí vive todo lo que habla con el mundo exterior y nada de lógica de negocio. Puede importar
de `app.domain` y `app.application` (necesita conocer los puertos que implementa y las
entidades que construye); lo contrario nunca ocurre.
"""
