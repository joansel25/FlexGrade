"""Adaptador del limitador de peticiones sobre Redis 7.

Contiene `redis_rate_limiter.py` con `RedisRateLimiter`, la implementación del puerto
`RateLimiter`: contador por ventana fija, atómico mediante un script Lua, y con la misma
degradación elegante que la caché —si Redis no responde, la petición pasa—.

El contador vive en Redis y no en el proceso porque con varias instancias detrás del
Application Gateway cada una llevaría su propia cuenta, y el límite real sería el declarado
multiplicado por un número de instancias que cambia solo con el autoescalado.
"""
