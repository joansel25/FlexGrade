"""Casos de uso, agrupados por área funcional del sistema.

Contendrá los subpaquetes `auth`, `catalog`, `enrollment` y `admin`, con un módulo y una clase
por caso de uso, siguiendo el patrón `<Verbo><Sustantivo>UseCase` con un único método público
`execute(...)`.

Un caso de uso recibe puertos (abstracciones) por constructor, coordina entidades y servicios
de dominio, y devuelve DTOs. Si una operación se limita a delegar una llamada al repositorio y
no orquesta nada, no se crea un caso de uso para ella (YAGNI).
"""
