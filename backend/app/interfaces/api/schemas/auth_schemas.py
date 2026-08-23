"""Schemas de entrada y salida de los endpoints de autenticación."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class LoginRequestSchema(BaseModel):
    """Cuerpo de `POST /auth/login`."""

    email: str = Field(description="Correo institucional", examples=["estudiante@tdea.edu.co"])
    password: str = Field(description="Contraseña en claro", examples=["SecurePass123"])


class RefreshRequestSchema(BaseModel):
    """Cuerpo de `POST /auth/refresh`."""

    refresh_token: str = Field(description="Token de refresco entregado en el login")


class AuthenticatedUserSchema(BaseModel):
    """Datos públicos de la cuenta autenticada.

    No incluye `password_hash` ni ningún dato de credenciales.
    """

    id: UUID
    email: str
    role: str


class TokenPairSchema(BaseModel):
    """Par de tokens devuelto por login y refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Vigencia del access token, en segundos")


class LoginResponseSchema(TokenPairSchema):
    """Respuesta 200 de `POST /auth/login`.

    Extiende el par de tokens con los datos de la cuenta, para que el frontend
    no necesite una segunda llamada solo para saber quién inició sesión.
    """

    user: AuthenticatedUserSchema
