"""Adaptadores de persistencia.

Contendrá hoy un único subpaquete, `sqlalchemy`, con la implementación sobre PostgreSQL 16.
El nivel intermedio existe para que un adaptador de persistencia distinto (por ejemplo, uno en
memoria para pruebas de integración o un almacén documental futuro) tenga dónde vivir sin
mezclarse con el mapeo relacional.
"""
