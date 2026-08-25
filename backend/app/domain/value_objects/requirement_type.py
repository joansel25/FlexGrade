"""Tipo de requisito académico entre dos materias."""

from __future__ import annotations

from enum import Enum


class RequirementType(str, Enum):
    """Cómo exige una materia a otra dentro de un plan de estudios.

    Los dos valores se parecen al leerlos y no se parecen en nada al validarlos, y esa es la
    razón de que sean un tipo y no un booleano `es_prerrequisito`:

    - `PREREQUISITE`: hay que **haberla aprobado antes**. Se comprueba contra el historial
      académico, que es un hecho consumado y no cambia durante la matrícula.
    - `COREQUISITE`: hay que **cursarla a la vez**. Se comprueba contra las inscripciones
      activas del período vigente, un estado que cambia mientras la persona matricula y que
      puede satisfacerse inscribiendo la otra materia un segundo después.

    Hereda de `str` como el resto de enumeraciones del dominio (`EnrollmentStatus`,
    `UserRole`): así el valor viaja tal cual a la base de datos y a la respuesta JSON sin
    conversiones intermedias, y una comparación contra la cadena `"PREREQUISITE"` sigue
    funcionando.
    """

    PREREQUISITE = "PREREQUISITE"
    COREQUISITE = "COREQUISITE"
