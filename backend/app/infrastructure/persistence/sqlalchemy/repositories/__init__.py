"""Implementaciones SQLAlchemy de los puertos de `app.application.ports.repositories`.

Un módulo por repositorio: `user`, `student`, `program`, `course`, `offering` y `period`. Queda
pendiente `enrollment`, de la Fase 3. Cada clase recibe la sesión por constructor, ejecuta las
consultas y **mapea entre modelos ORM y entidades del dominio** en ambos sentidos: el dominio
nunca ve un objeto de SQLAlchemy.

Por el principio de sustitución de Liskov, estas implementaciones deben ser intercambiables con
los dobles usados en pruebas unitarias sin que el comportamiento observable cambie. Sus pruebas
son de integración, contra el PostgreSQL real de `docker-compose` (o el servicio del runner en
CI), porque el esquema usa elementos que ningún motor en memoria reproduce.

Regla que estas clases deben respetar sin excepción: **el número de consultas no puede depender
del número de resultados**. `SQLAlchemyOfferingRepository` es el ejemplo a seguir; resuelve
cualquier cantidad de grupos, con sus docentes y sus horarios, en dos consultas fijas.
"""
