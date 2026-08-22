"""Implementaciones SQLAlchemy de los puertos de `app.application.ports.repositories`.

Contendrá un módulo por repositorio (student, course, offering, enrollment, period). Cada clase
recibe la sesión por constructor, ejecuta las consultas y **mapea entre modelos ORM y entidades
del dominio** en ambos sentidos: el dominio nunca ve un objeto de SQLAlchemy.

Por el principio de sustitución de Liskov, estas implementaciones deben ser intercambiables con
los dobles usados en pruebas unitarias sin que el comportamiento observable cambie. Sus pruebas
son de integración, contra una base de datos real levantada con Testcontainers.
"""
