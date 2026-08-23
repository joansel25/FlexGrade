"""Errores de construcción de value objects."""

from __future__ import annotations

from app.domain.exceptions.base import DomainError


class InvalidValueError(DomainError):
    """Un value object recibió un valor que viola su invariante."""


class InvalidEmailError(InvalidValueError):
    """El correo electrónico no tiene un formato válido."""


class InvalidStudentCodeError(InvalidValueError):
    """El código de estudiante no cumple el formato institucional."""
