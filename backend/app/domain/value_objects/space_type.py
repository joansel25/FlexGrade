"""Tipo de espacio físico donde se dicta una clase."""

from __future__ import annotations

from enum import Enum


class SpaceType(str, Enum):
    """Qué clase de espacio es, de las que la institución distingue de verdad.

    La distinción no es descriptiva: cambia qué se puede programar dentro. Un laboratorio tiene
    puestos de trabajo y no filas de pupitres, así que su aforo no se amplía acercando sillas; un
    auditorio no sirve para una práctica aunque quepan todos. Cuando la Fase 7 comprueba que el
    grupo cabe en el espacio, el tipo es lo que permitirá decir además si el espacio es el
    adecuado y no solo si es lo bastante grande.

    Tres valores y no más, porque son los que aparecen en la asignación real de un semestre.
    Añadir «sala de cómputo» o «taller» es una fila más en este enum el día que exista una regla
    que los trate distinto; inventarlos antes solo llena la lista.

    Hereda de `str` como el resto de enumeraciones del dominio, así que el valor viaja tal cual
    a la base de datos y a la respuesta JSON.
    """

    CLASSROOM = "CLASSROOM"
    LABORATORY = "LABORATORY"
    AUDITORIUM = "AUDITORIUM"
