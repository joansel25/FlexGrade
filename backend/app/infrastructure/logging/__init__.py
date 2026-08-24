"""Configuración de observabilidad: formato de los registros y trazado de peticiones.

Vive en `infrastructure/` porque es una decisión de plataforma, no de negocio: el dominio no
sabe que existe CloudWatch, igual que no sabe que existe PostgreSQL.
"""
