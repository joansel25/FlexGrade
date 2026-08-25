"""Estado de una materia dentro del plan de estudios de un estudiante."""

from __future__ import annotations

from enum import Enum


class CourseStatus(str, Enum):
    """En qué punto está el estudiante respecto a una materia de su plan.

    No es un atributo de la materia ni del plan: es el cruce de los dos con el historial
    académico y con la oferta del período. La misma materia está `APPROVED` para quien la cursó
    y `BLOCKED` para quien no aprobó lo anterior.

    Los cinco valores existen porque cada uno lleva a una acción distinta en la pantalla, que es
    la única prueba que justifica un estado más:

    - `APPROVED`: ya la aprobó. No hay nada que hacer.
    - `ENROLLED`: la está cursando en el período vigente. Se ofrece ir a «Mis materias».
    - `AVAILABLE`: puede inscribirla ahora mismo. Es la única sobre la que se pulsa.
    - `NOT_OFFERED`: cumple los requisitos, pero no hay grupos este período. Ofrecer inscribirla
      sería empujar hacia una pantalla vacía.
    - `BLOCKED`: le falta algo. La respuesta trae qué, porque «bloqueada» sin más deja a la
      persona igual de atascada que antes.

    NO existe un estado «de otro semestre», aunque la hoja de ruta lo nombrara. El semestre
    sugerido del plan es una sugerencia y no una restricción —lo dice el modelo de datos—, así
    que convertirlo en estado afirmaría un impedimento que el sistema no aplica: quien cumpla
    los prerrequisitos puede inscribir una materia de tercero estando en primero. La pantalla
    agrupa por semestre, que es lo que esa idea aportaba de verdad.

    Hereda de `str` como el resto de enumeraciones del dominio, así que el valor viaja tal cual
    a la respuesta JSON.
    """

    APPROVED = "APPROVED"
    ENROLLED = "ENROLLED"
    AVAILABLE = "AVAILABLE"
    NOT_OFFERED = "NOT_OFFERED"
    BLOCKED = "BLOCKED"
