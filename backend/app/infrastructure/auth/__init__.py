"""Adaptador de autenticación.

Contendrá `jwt_auth_service.py` con JwtAuthService, la implementación del puerto `AuthService`:
hash y verificación de contraseñas, y emisión y validación de tokens firmados con `JWT_SECRET`,
usando `JWT_EXPIRATION_SECONDS` para el token de acceso y `JWT_REFRESH_EXPIRATION_SECONDS` para
el de refresco.

El secreto se lee de la configuración, jamás se escribe en el código. Si en producción la
autenticación migra a Microsoft Entra External ID, se añade otro adaptador que implemente el mismo
puerto y ningún caso de uso cambia.
"""
