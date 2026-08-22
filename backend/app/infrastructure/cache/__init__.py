"""Adaptador de caché sobre Redis 7.

Contendrá `redis_cache_service.py` con RedisCacheService, la implementación del puerto
`CacheService`: conexión a partir de `REDIS_URL`, serialización de valores y TTL corto (30-60
segundos) para las consultas de catálogo, que son las de mayor frecuencia durante el pico de
matrícula.

Regla de negocio que este adaptador debe respetar: **la disponibilidad de cupos nunca se
cachea**. El descuento de cupo y la verificación de disponibilidad consultan siempre
PostgreSQL.
"""
