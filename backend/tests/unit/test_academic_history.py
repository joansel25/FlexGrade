"""Pruebas del expediente académico (iteración 9.4).

Cierra el círculo visible de la Fase 9: lo que la 9.3 escribe, esto lo devuelve. Hasta ahora el
semáforo decía «aprobada» sin que el estudiante pudiera ver dónde ni con qué nota.

Lo que se comprueba, sobre todo, es **el cálculo del promedio**. Es la cifra que decide becas y
que aparece en un certificado: si no coincide con el oficial, quien la vea la tomará por buena.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.use_cases.catalog.get_academic_history import GetAcademicHistoryUseCase
from app.domain.entities.academic_record import AcademicRecord
from app.domain.value_objects.grade import Grade
from app.domain.value_objects.history_status import HistoryStatus
from tests.unit.doubles import InMemoryAcademicHistory, InMemoryCourseRepository
from tests.unit.factories import crear_estudiante, crear_materia


def _escenario(filas: list[tuple[str, str, int, str]]):
    """Monta un expediente a partir de `(semestre, código, créditos, nota)`."""
    estudiante = crear_estudiante(student_code="202500001", full_name="Ada Álvarez")
    materias = {}
    registros: list[AcademicRecord] = []

    for semestre, codigo, creditos, nota in filas:
        materia = materias.setdefault(codigo, crear_materia(code=codigo, credits=creditos))
        registros.append(
            AcademicRecord.consolidate(
                student_id=estudiante.id,
                course_id=materia.id,
                academic_period=semestre,
                final_grade=Grade(Decimal(nota)),
            )
        )

    historial = InMemoryAcademicHistory()
    # Descendente, como el adaptador SQL: `groupby` depende de ese orden.
    historial.save_all(sorted(registros, key=lambda r: r.academic_period, reverse=True))

    caso = GetAcademicHistoryUseCase(historial, InMemoryCourseRepository(list(materias.values())))

    return caso, estudiante


@pytest.mark.unit
def test_el_promedio_se_pondera_por_creditos() -> None:
    """Una materia de 4 créditos pesa el doble que una de 2.

    Con media simple el resultado sería 3.50; ponderado es 4.00. La diferencia no es cosmética:
    es la cifra que decide si alguien conserva una beca, y una media simple no coincidiría con
    el certificado oficial.
    """
    caso, estudiante = _escenario(
        [("2025-2", "MAT101", 4, "4.50"), ("2025-2", "FIS101", 2, "2.50")]
    )

    expediente = caso.execute(estudiante)

    assert expediente.cumulative_average == Decimal("3.83")
    assert expediente.periods[0].credits_attempted == 6
    assert expediente.periods[0].credits_approved == 4


@pytest.mark.unit
def test_lo_perdido_aparece_igual_que_lo_aprobado() -> None:
    # Un expediente que oculta lo reprobado no es un expediente.
    caso, estudiante = _escenario(
        [("2025-2", "MAT101", 4, "4.50"), ("2025-2", "FIS101", 2, "2.50")]
    )

    expediente = caso.execute(estudiante)

    assert {e.status for e in expediente.periods[0].entries} == {
        HistoryStatus.APPROVED,
        HistoryStatus.FAILED,
    }


@pytest.mark.unit
def test_la_materia_repetida_sale_las_dos_veces() -> None:
    """Las dos ocurrieron, y el expediente las conserva en su semestre.

    Es lo que hace la restricción `UNIQUE (student_id, course_id, academic_period)`: la misma
    materia en dos semestres distintos son dos filas legítimas.
    """
    caso, estudiante = _escenario(
        [("2025-1", "MAT101", 4, "2.00"), ("2025-2", "MAT101", 4, "4.00")]
    )

    expediente = caso.execute(estudiante)

    assert [p.academic_period for p in expediente.periods] == ["2025-2", "2025-1"]
    assert expediente.total_credits_approved == 4
    assert expediente.cumulative_average == Decimal("3.00")


@pytest.mark.unit
def test_los_semestres_van_del_mas_reciente_al_mas_antiguo() -> None:
    # Es lo que se mira. Al revés obligaría a bajar hasta el final para ver lo último cursado.
    caso, estudiante = _escenario(
        [
            ("2024-1", "MAT101", 4, "4.00"),
            ("2025-2", "FIS101", 3, "3.00"),
            ("2024-2", "PRG101", 3, "5.00"),
        ]
    )

    expediente = caso.execute(estudiante)

    assert [p.academic_period for p in expediente.periods] == ["2025-2", "2024-2", "2024-1"]


@pytest.mark.unit
def test_cada_semestre_tiene_su_propio_promedio() -> None:
    caso, estudiante = _escenario(
        [("2025-1", "MAT101", 4, "2.00"), ("2025-2", "FIS101", 4, "5.00")]
    )

    expediente = caso.execute(estudiante)

    assert {p.academic_period: p.average for p in expediente.periods} == {
        "2025-2": Decimal("5.00"),
        "2025-1": Decimal("2.00"),
    }


@pytest.mark.unit
def test_un_expediente_vacio_es_una_respuesta_legitima() -> None:
    """Quien acaba de ingresar todavía no ha cerrado ningún semestre.

    Un 404 diría que algo está roto, y un promedio inventado sería peor: `0.00` sin materias se
    lee distinto de `0.00` con todas perdidas.
    """
    caso, estudiante = _escenario([])

    expediente = caso.execute(estudiante)

    assert expediente.periods == []
    assert expediente.total_credits_approved == 0
    assert expediente.cumulative_average == Decimal("0.00")
    assert expediente.student_code == "202500001"


@pytest.mark.unit
def test_las_materias_de_un_semestre_van_por_codigo() -> None:
    # Es como se lee un acta.
    caso, estudiante = _escenario(
        [
            ("2025-2", "PRG101", 3, "4.00"),
            ("2025-2", "FIS101", 3, "4.00"),
            ("2025-2", "MAT101", 3, "4.00"),
        ]
    )

    expediente = caso.execute(estudiante)

    assert [e.course.code.value for e in expediente.periods[0].entries] == [
        "FIS101",
        "MAT101",
        "PRG101",
    ]
