"""Puertos: las interfaces abstractas (ABC) que la infraestructura debe implementar.

El puerto es la abstracción y pertenece a la capa de aplicación; la implementación concreta
vive en `app.infrastructure`. Esa es la inversión de dependencias del patrón hexagonal.

Contendrá, además del subpaquete `repositories`:

- `cache_service.py`: CacheService, lectura/escritura/invalidación de claves con TTL para el
  catálogo. Implementado con Redis.
- `auth_service.py`: AuthService, hash y verificación de contraseñas, emisión y validación de
  tokens.
- `notification_service.py`: NotificationService, notificación al estudiante tras inscribir o
  cancelar.
- `unit_of_work.py`: UnitOfWork, frontera transaccional (`commit`, `rollback`) que garantiza la
  atomicidad entre el descuento de cupo y la creación de la inscripción.

Cada puerto se declara con métodos que hablan el lenguaje del negocio. No existen puertos
genéricos ni parametrizados por tipo.
"""
