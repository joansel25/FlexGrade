"""Pruebas unitarias de las excepciones del catálogo.

No comprueban que la excepción se lance —eso lo hacen los tests de los casos de uso— sino que
su carga útil sea la correcta. El campo `details` no es decorativo: `main.py` lo serializa tal
cual dentro del bloque `error` de la respuesta, así que forma parte del contrato público
descrito en `API.md`. Un `details` vacío donde debería ir el identificador deja al frontend
sin saber qué recurso falló.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.exceptions.base import DomainError
from app.domain.exceptions.catalog import (
    CourseNotFoundError,
    NoActivePeriodError,
    OfferingNotFoundError,
)


@pytest.mark.unit
def test_course_not_found_carries_the_course_id_in_details() -> None:
    course_id = uuid4()

    error = CourseNotFoundError(course_id)

    assert error.details == {"course_id": str(course_id)}


@pytest.mark.unit
def test_offering_not_found_carries_the_offering_id_in_details() -> None:
    offering_id = uuid4()

    error = OfferingNotFoundError(offering_id)

    assert error.details == {"offering_id": str(offering_id)}


@pytest.mark.unit
def test_no_active_period_has_no_details() -> None:
    # No hay ningun identificador que informar: el fallo es la ausencia de un recurso, no un
    # recurso concreto que no se encontro.
    assert NoActivePeriodError().details == {}


@pytest.mark.unit
@pytest.mark.parametrize(
    "error",
    [CourseNotFoundError(uuid4()), OfferingNotFoundError(uuid4()), NoActivePeriodError()],
)
def test_catalog_errors_have_a_message_and_descend_from_domain_error(error: DomainError) -> None:
    # Descender de `DomainError` es lo que hace que el handler centralizado de `main.py` las
    # recoja. Una excepcion del catalogo que herede de `Exception` se convertiria en un 500.
    assert isinstance(error, DomainError)
    assert error.message
