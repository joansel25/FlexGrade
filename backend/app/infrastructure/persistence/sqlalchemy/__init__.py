"""Adaptador de persistencia sobre SQLAlchemy 2.x y PostgreSQL.

Contiene:

- `models/`: las declaraciones de tablas y, en `models/base.py`, la clase declarativa `Base` de
  la que heredan todos los modelos ORM.
- `session.py` (pendiente): creación del engine a partir de `DATABASE_URL` y la fábrica de
  sesiones.
- `unit_of_work.py` (pendiente): SqlAlchemyUnitOfWork, implementación del puerto `UnitOfWork`
  sobre la sesión.
- `repositories/` (pendiente): las implementaciones de los puertos de repositorio.

La `Base` vive junto a los modelos y no en `session.py` a propósito: `alembic/env.py` necesita
importar el `MetaData` para poder autogenerar migraciones, y hacerlo a través de un módulo que
construye el engine acoplaría la lectura del esquema a la apertura de una conexión.

Las migraciones de Alembic leen los metadatos declarados aquí.
"""
