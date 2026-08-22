"""Pruebas de integración: los adaptadores contra la infraestructura real.

Contendrá las pruebas de los repositorios SQLAlchemy y del unit of work contra un PostgreSQL
levantado con Testcontainers, las del adaptador de Redis, y las migraciones de Alembic aplicadas
de cero.

Aquí vive la prueba de concurrencia del descuento de cupo (Fase 3): varias transacciones
compitiendo por el último cupo, verificando que exactamente una gana. Es la que respalda el
requisito no funcional central del sistema.

Se marcan con `@pytest.mark.integration`.
"""
