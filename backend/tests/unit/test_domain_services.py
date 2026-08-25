"""Pruebas unitarias de los servicios de dominio del catálogo académico.

Son objetos sin estado que reciben todo por parámetro, así que se prueban sin base de datos,
sin repositorios y sin dobles: se les pasan datos y se comprueba qué deciden. Esa es
exactamente la ventaja de haberlos separado del caso de uso.
"""

from __future__ import annotations

from datetime import time
from uuid import uuid4

import pytest

from app.domain.exceptions.enrollment import (
    CorequisitesNotMetError,
    PrerequisitesNotMetError,
    ScheduleConflictError,
)
from app.domain.services.corequisite_validator import CorequisiteValidator
from app.domain.services.prerequisite_validator import PrerequisiteValidator
from app.domain.services.schedule_conflict_detector import ScheduleConflictDetector
from tests.unit.factories import crear_franja, crear_materia, crear_oferta

# ---------------------------------------------------------------------------
# PrerequisiteValidator
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_course_without_prerequisites_is_always_allowed() -> None:
    PrerequisiteValidator().validate(course_id=uuid4(), required=[], approved_course_ids=set())


@pytest.mark.unit
def test_when_the_only_prerequisite_is_approved_it_passes() -> None:
    calculo_i = crear_materia(code="MAT101")

    PrerequisiteValidator().validate(
        course_id=uuid4(),
        required=[calculo_i],
        approved_course_ids={calculo_i.id},
    )


@pytest.mark.unit
def test_when_a_prerequisite_is_missing_it_raises() -> None:
    calculo_i = crear_materia(code="MAT101")

    with pytest.raises(PrerequisitesNotMetError):
        PrerequisiteValidator().validate(
            course_id=uuid4(), required=[calculo_i], approved_course_ids=set()
        )


@pytest.mark.unit
def test_the_error_names_exactly_which_courses_are_missing() -> None:
    # El estudiante necesita saber QUÉ le falta para poder hacer algo al respecto. Un aviso
    # genérico le obliga a adivinar.
    calculo_i = crear_materia(code="MAT101")
    programacion_i = crear_materia(code="PRG101")
    fisica = crear_materia(code="FIS101")

    with pytest.raises(PrerequisitesNotMetError) as error:
        PrerequisiteValidator().validate(
            course_id=uuid4(),
            required=[calculo_i, programacion_i, fisica],
            approved_course_ids={programacion_i.id},
        )

    assert error.value.details["missing_prerequisites"] == ["FIS101", "MAT101"]


@pytest.mark.unit
def test_the_missing_list_comes_sorted() -> None:
    # Un orden que cambia entre peticiones hace imposible probar la respuesta y confunde a
    # quien la lee dos veces.
    materias = [crear_materia(code=c) for c in ("PRG101", "FIS101", "MAT101")]

    with pytest.raises(PrerequisitesNotMetError) as error:
        PrerequisiteValidator().validate(
            course_id=uuid4(), required=materias, approved_course_ids=set()
        )

    assert error.value.details["missing_prerequisites"] == ["FIS101", "MAT101", "PRG101"]


@pytest.mark.unit
def test_approving_unrelated_courses_does_not_satisfy_a_prerequisite() -> None:
    exigida = crear_materia(code="MAT101")
    otra = crear_materia(code="DER101")

    with pytest.raises(PrerequisitesNotMetError):
        PrerequisiteValidator().validate(
            course_id=uuid4(), required=[exigida], approved_course_ids={otra.id}
        )


@pytest.mark.unit
def test_only_direct_prerequisites_are_checked() -> None:
    """Aprobar MAT102 basta para MAT201, aunque MAT101 no aparezca.

    No es una simplificación: si el estudiante aprobó MAT102, la institución ya validó en su
    momento que cumplía lo anterior. Recorrer la cadena entera volvería a exigir materias que
    pudieron ser homologadas o cursadas bajo otro plan de estudios.
    """
    calculo_ii = crear_materia(code="MAT102")

    PrerequisiteValidator().validate(
        course_id=uuid4(),
        required=[calculo_ii],
        approved_course_ids={calculo_ii.id},
    )


# ---------------------------------------------------------------------------
# CorequisiteValidator
# ---------------------------------------------------------------------------


def _validar(
    *,
    required,
    inscritas=frozenset(),
    aprobadas=frozenset(),
    mutuas=frozenset(),
) -> None:
    """Invoca al validador con los conjuntos vacíos por defecto.

    Los cuatro conjuntos hacen que cada llamada ocupe seis líneas, y en estos tests lo que
    importa es cuál de ellos contiene la materia exigida. Nombrar solo ese es lo que deja la
    diferencia entre un caso y otro a la vista.
    """
    CorequisiteValidator().validate(
        course_id=uuid4(),
        required=required,
        enrolled_course_ids=set(inscritas),
        approved_course_ids=set(aprobadas),
        mutual_course_ids=set(mutuas),
    )


@pytest.mark.unit
def test_a_course_without_corequisites_is_always_allowed() -> None:
    _validar(required=[])


@pytest.mark.unit
def test_a_corequisite_enrolled_in_this_period_satisfies_the_rule() -> None:
    calculo_i = crear_materia(code="MAT101")

    _validar(required=[calculo_i], inscritas={calculo_i.id})


@pytest.mark.unit
def test_a_corequisite_already_approved_also_satisfies_the_rule() -> None:
    """Quien ya la aprobó tiene con más motivo lo que el correquisito busca garantizar.

    Exigirle cursarla otra vez convertiría la regla en un castigo por ir adelantado.
    """
    calculo_i = crear_materia(code="MAT101")

    _validar(required=[calculo_i], aprobadas={calculo_i.id})


@pytest.mark.unit
def test_a_corequisite_neither_enrolled_nor_approved_is_rejected() -> None:
    calculo_i = crear_materia(code="MAT101")

    with pytest.raises(CorequisitesNotMetError) as error:
        _validar(required=[calculo_i])

    assert error.value.details["missing_corequisites"] == ["MAT101"]


@pytest.mark.unit
def test_a_mutual_corequisite_does_not_have_to_be_enrolled_yet() -> None:
    """Es la salida al bloqueo circular, y la razón de que exista `mutual_course_ids`.

    Si A exige B y B exige A, exigir que la otra esté inscrita ANTES hace que la primera de
    las dos falle siempre: el bloque entero queda fuera de la matrícula por cualquier camino
    que se intente.
    """
    laboratorio = crear_materia(code="TAL101")

    _validar(required=[laboratorio], mutuas={laboratorio.id})


@pytest.mark.unit
def test_the_exemption_applies_only_to_the_mutual_ones() -> None:
    """Un correquisito en un solo sentido sigue teniendo que estar inscrito.

    Sin esta distinción, declarar cualquier correquisito equivaldría a no declarar ninguno.
    """
    laboratorio = crear_materia(code="TAL101")
    calculo_i = crear_materia(code="MAT101")

    with pytest.raises(CorequisitesNotMetError) as error:
        _validar(required=[laboratorio, calculo_i], mutuas={laboratorio.id})

    assert error.value.details["missing_corequisites"] == ["MAT101"]


@pytest.mark.unit
def test_the_missing_corequisites_come_sorted() -> None:
    materias = [crear_materia(code=c) for c in ("PRG101", "FIS101", "MAT101")]

    with pytest.raises(CorequisitesNotMetError) as error:
        _validar(required=materias)

    assert error.value.details["missing_corequisites"] == ["FIS101", "MAT101", "PRG101"]


# ---------------------------------------------------------------------------
# ScheduleConflictDetector
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_with_nothing_enrolled_there_is_no_conflict() -> None:
    candidato = crear_oferta(schedule=(crear_franja(),))

    ScheduleConflictDetector().ensure_no_conflict(candidate=candidato, enrolled=[])


@pytest.mark.unit
def test_classes_on_different_days_do_not_conflict() -> None:
    lunes = crear_oferta(schedule=(crear_franja(day_of_week=1),))
    martes = crear_oferta(schedule=(crear_franja(day_of_week=2),))

    ScheduleConflictDetector().ensure_no_conflict(candidate=martes, enrolled=[lunes])


@pytest.mark.unit
def test_overlapping_classes_raise() -> None:
    inscrito = crear_oferta(
        schedule=(crear_franja(day_of_week=1, start_time=time(8, 0), end_time=time(10, 0)),)
    )
    candidato = crear_oferta(
        schedule=(crear_franja(day_of_week=1, start_time=time(9, 0), end_time=time(11, 0)),)
    )

    with pytest.raises(ScheduleConflictError):
        ScheduleConflictDetector().ensure_no_conflict(candidate=candidato, enrolled=[inscrito])


@pytest.mark.unit
def test_consecutive_classes_do_not_conflict() -> None:
    # El borde que más se falla: una termina a las 10:00 y la siguiente empieza a las 10:00.
    # Tratarlo como conflicto bloquearía horarios perfectamente válidos.
    inscrito = crear_oferta(
        schedule=(crear_franja(day_of_week=1, start_time=time(8, 0), end_time=time(10, 0)),)
    )
    candidato = crear_oferta(
        schedule=(crear_franja(day_of_week=1, start_time=time(10, 0), end_time=time(12, 0)),)
    )

    ScheduleConflictDetector().ensure_no_conflict(candidate=candidato, enrolled=[inscrito])


@pytest.mark.unit
def test_the_error_identifies_the_group_and_the_moment_of_the_clash() -> None:
    # La interfaz necesita poder señalarlo en el horario, no solo rechazar la operación.
    inscrito = crear_oferta(
        schedule=(crear_franja(day_of_week=3, start_time=time(8, 0), end_time=time(10, 0)),)
    )
    candidato = crear_oferta(
        schedule=(crear_franja(day_of_week=3, start_time=time(9, 0), end_time=time(11, 0)),)
    )

    with pytest.raises(ScheduleConflictError) as error:
        ScheduleConflictDetector().ensure_no_conflict(candidate=candidato, enrolled=[inscrito])

    assert error.value.details == {
        "conflicting_offering_id": str(inscrito.id),
        "day_of_week": 3,
        "start_time": "09:00:00",
    }


@pytest.mark.unit
def test_a_clash_in_any_of_several_blocks_is_detected() -> None:
    # Un grupo tiene varias franjas. Basta con que UNA choque.
    inscrito = crear_oferta(
        schedule=(
            crear_franja(day_of_week=1, start_time=time(6, 0), end_time=time(8, 0)),
            crear_franja(day_of_week=4, start_time=time(14, 0), end_time=time(16, 0)),
        )
    )
    candidato = crear_oferta(
        schedule=(
            crear_franja(day_of_week=2, start_time=time(8, 0), end_time=time(10, 0)),
            crear_franja(day_of_week=4, start_time=time(15, 0), end_time=time(17, 0)),
        )
    )

    with pytest.raises(ScheduleConflictError):
        ScheduleConflictDetector().ensure_no_conflict(candidate=candidato, enrolled=[inscrito])


@pytest.mark.unit
def test_the_clash_is_found_against_any_of_several_enrolled_groups() -> None:
    sin_choque = crear_oferta(schedule=(crear_franja(day_of_week=1),))
    con_choque = crear_oferta(
        schedule=(crear_franja(day_of_week=5, start_time=time(8, 0), end_time=time(10, 0)),)
    )
    candidato = crear_oferta(
        schedule=(crear_franja(day_of_week=5, start_time=time(9, 0), end_time=time(11, 0)),)
    )

    with pytest.raises(ScheduleConflictError) as error:
        ScheduleConflictDetector().ensure_no_conflict(
            candidate=candidato, enrolled=[sin_choque, con_choque]
        )

    assert error.value.details["conflicting_offering_id"] == str(con_choque.id)


@pytest.mark.unit
def test_a_group_without_a_published_schedule_never_conflicts() -> None:
    # Un grupo puede publicarse antes de asignar horario. Sin franjas no hay con qué chocar.
    inscrito = crear_oferta(schedule=(crear_franja(),))
    sin_horario = crear_oferta(schedule=())

    ScheduleConflictDetector().ensure_no_conflict(candidate=sin_horario, enrolled=[inscrito])


@pytest.mark.unit
def test_a_group_does_not_conflict_with_itself() -> None:
    # Evita un falso positivo si quien llama incluyera el candidato en la lista por descuido.
    grupo = crear_oferta(schedule=(crear_franja(),))

    ScheduleConflictDetector().ensure_no_conflict(candidate=grupo, enrolled=[grupo])
