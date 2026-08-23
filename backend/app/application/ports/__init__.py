"""Puertos: las interfaces abstractas (ABC) que la infraestructura debe implementar.

El puerto es la abstracción y pertenece a la capa de aplicación; la implementación concreta
vive en `app.infrastructure`. Esa es la inversión de dependencias del patrón hexagonal.

Existentes, además del subpaquete `repositories`:

- `auth_service.py`: AuthService, hash y verificación de contraseñas, emisión y validación de
  tokens. Segregado en `PasswordHasher` y `TokenService`.
- `cache_service.py`: CacheService, lectura, escritura con TTL e invalidación de claves.
  Implementado con Redis. Cachea el catálogo; nunca la disponibilidad de cupos.

Pendientes:

- `notification_service.py`: NotificationService, notificación al estudiante tras inscribir o
  cancelar.
- `unit_of_work.py`: UnitOfWork, frontera transaccional (`commit`, `rollback`) que garantiza
  la atomicidad entre el descuento de cupo y la creación de la inscripción. Llega con la Fase
  3, que es la primera que escribe desde un endpoint; hasta entonces no habría quién lo use.

Cada puerto se declara con métodos que hablan el lenguaje del negocio. No existen puertos
genéricos ni parametrizados por tipo.
"""
