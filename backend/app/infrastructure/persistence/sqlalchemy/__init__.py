"""Adaptador de persistencia sobre SQLAlchemy 2.x y PostgreSQL.

Contendrá:

- `session.py`: creación del engine a partir de `DATABASE_URL`, la fábrica de sesiones y la
  clase declarativa `Base` de la que heredan los modelos ORM.
- `unit_of_work.py`: SqlAlchemyUnitOfWork, implementación del puerto `UnitOfWork` sobre la
  sesión.
- `models/`: las declaraciones de tablas.
- `repositories/`: las implementaciones de los puertos de repositorio.

Las migraciones de Alembic leen los metadatos declarados aquí.
"""
