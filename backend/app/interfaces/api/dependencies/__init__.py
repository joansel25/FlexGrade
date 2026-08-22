"""Dependencias inyectables de FastAPI (`Depends`).

Contendrá:

- `auth.py`: `get_current_user` y `require_admin`, que validan el token y el rol antes de que
  el endpoint se ejecute.
- `di.py`: el cableado de la inyección de dependencias, donde cada puerto se resuelve a su
  implementación concreta (sesión de SQLAlchemy, repositorios, caché de Redis, unit of work) y
  se construyen los casos de uso.

Este es el único lugar donde la capa externa conecta abstracciones con implementaciones; el
resto del código depende solo de los puertos. En las pruebas, `app.dependency_overrides`
sustituye estas dependencias por dobles.
"""
