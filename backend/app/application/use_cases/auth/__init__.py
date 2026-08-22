"""Casos de uso de autenticación (Fase 1).

Contendrá:

- `authenticate_user.py`: AuthenticateUserUseCase, valida credenciales contra el repositorio de
  usuarios y emite el par de tokens a través del puerto `AuthService`.
- `refresh_token.py`: RefreshTokenUseCase, renueva el token de acceso a partir de un refresh
  token válido.

La firma criptográfica, el hash de contraseñas y los tiempos de expiración son responsabilidad
del adaptador `app.infrastructure.auth`, no de estos casos de uso.
"""
