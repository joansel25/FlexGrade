"""Pruebas unitarias de los value objects del dominio."""

from __future__ import annotations

import pytest

from app.domain.exceptions.invalid_value import (
    InvalidCourseCodeError,
    InvalidEmailError,
    InvalidStudentCodeError,
)
from app.domain.value_objects.course_code import CourseCode
from app.domain.value_objects.email import Email
from app.domain.value_objects.student_code import StudentCode


@pytest.mark.unit
def test_email_when_has_uppercase_and_spaces_is_normalized() -> None:
    assert Email("  Estudiante@TDEA.edu.CO  ").value == "estudiante@tdea.edu.co"


@pytest.mark.unit
@pytest.mark.parametrize(
    "valor",
    ["", "   ", "sin-arroba", "@sindominio.co", "usuario@", "usuario@dominio", "a b@c.co"],
)
def test_email_when_format_is_invalid_raises_invalid_email(valor: str) -> None:
    with pytest.raises(InvalidEmailError):
        Email(valor)


@pytest.mark.unit
def test_email_when_exceeds_max_length_raises_invalid_email() -> None:
    with pytest.raises(InvalidEmailError):
        Email("a" * 250 + "@tdea.edu.co")


@pytest.mark.unit
def test_email_when_same_address_differs_in_case_instances_are_equal() -> None:
    # La normalización hace que dos escrituras del mismo correo sean el mismo
    # value object, que es lo que permite buscarlo de forma determinista.
    assert Email("Estudiante@TDEA.edu.co") == Email("estudiante@tdea.edu.co")


@pytest.mark.unit
def test_student_code_when_valid_keeps_its_digits() -> None:
    assert StudentCode("1234567").value == "1234567"


@pytest.mark.unit
@pytest.mark.parametrize("valor", ["", "12345", "abc1234", "1234-567", "1" * 21])
def test_student_code_when_format_is_invalid_raises_invalid_student_code(valor: str) -> None:
    with pytest.raises(InvalidStudentCodeError):
        StudentCode(valor)


@pytest.mark.unit
def test_course_code_when_valid_keeps_its_value() -> None:
    assert CourseCode("MAT101").value == "MAT101"


@pytest.mark.unit
def test_course_code_when_lowercase_or_padded_is_normalized() -> None:
    # El estudiante escribe "mat101" en el buscador; la busqueda tiene que encontrarlo.
    assert CourseCode("  mat101 ").value == "MAT101"


@pytest.mark.unit
@pytest.mark.parametrize(
    "valor",
    ["", "   ", "MAT", "101", "M101", "MAT1", "MAT-101", "MAT 101", "MATEMATICAS101"],
)
def test_course_code_when_format_is_invalid_raises_invalid_course_code(valor: str) -> None:
    with pytest.raises(InvalidCourseCodeError):
        CourseCode(valor)


@pytest.mark.unit
def test_course_code_when_same_code_differs_in_case_instances_are_equal() -> None:
    assert CourseCode("mat101") == CourseCode("MAT101")
