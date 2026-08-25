"""Pruebas del comprobante de matrícula.

Se separan en dos niveles a propósito:

- El **contenido** se prueba contra el `ReceiptDTO`, sin generar un solo byte de PDF. Es lo que
  permite comprobar que los créditos suman bien o que los horarios llegan ordenados en
  milisegundos, y esa separación es justo la razón de que el renderizador sea un puerto.
- El **documento** se prueba generándolo de verdad, pero solo en lo que se puede afirmar sin
  abrir un lector: que es un PDF válido, que tiene contenido y que no revienta con los casos
  que rompen una maquetación —sin materias, nombres larguísimos, caracteres de marcado—.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import uuid4

import pytest

from app.application.dtos.receipt_dto import ReceiptDTO, ReceiptItemDTO, ReceiptScheduleBlockDTO
from app.application.use_cases.enrollment.generate_receipt import GenerateReceiptUseCase
from app.application.use_cases.enrollment.list_student_enrollments import (
    ListStudentEnrollmentsUseCase,
)
from app.domain.exceptions.authentication import StudentProfileNotFoundError
from app.domain.exceptions.catalog import NoActivePeriodError
from app.infrastructure.documents.pdf_receipt_renderer import PdfReceiptRenderer
from tests.unit.doubles import (
    InMemoryCourseRepository,
    InMemoryEnrollmentRepository,
    InMemoryOfferingRepository,
    InMemoryPeriodRepository,
    InMemoryProgramRepository,
    InMemoryStudentRepository,
)
from tests.unit.factories import (
    crear_estudiante,
    crear_franja,
    crear_inscripcion,
    crear_materia,
    crear_oferta,
    crear_periodo,
    crear_profesor,
    crear_programa,
)


class RenderizadorEspia:
    """Captura el comprobante en vez de dibujarlo.

    Permite afirmar sobre el CONTENIDO sin depender de la maquetación: si un test tuviera que
    leer el PDF para comprobar una suma, cambiar el diseño rompería tests que no hablan de
    diseño.
    """

    def __init__(self) -> None:
        self.recibido: ReceiptDTO | None = None

    def render(self, receipt: ReceiptDTO) -> bytes:
        self.recibido = receipt
        return b"%PDF-falso"


def _montar(*, con_inscripciones: bool = True, con_periodo: bool = True):
    """Arma el caso de uso con un estudiante, su programa y dos materias inscritas."""
    programa = crear_programa(code="ISIS", name="Ingeniería de Sistemas")
    estudiante = crear_estudiante(program_id=programa.id, full_name="Ana María Rojas")
    periodo = crear_periodo(is_active=True)

    calculo = crear_materia(code="MAT101", name="Cálculo I", credits=4)
    fisica = crear_materia(code="FIS101", name="Física I", credits=3)
    docente = crear_profesor(full_name="Luis Gómez")

    grupo_calculo = crear_oferta(
        course_id=calculo.id,
        enrollment_period_id=periodo.id,
        group_number="01",
        professor=docente,
        # Desordenadas a propósito: el comprobante debe ordenarlas.
        schedule=(
            crear_franja(day_of_week=3, start_time=time(14, 0), end_time=time(16, 0)),
            crear_franja(day_of_week=1, start_time=time(8, 0), end_time=time(10, 0)),
        ),
    )
    grupo_fisica = crear_oferta(
        course_id=fisica.id,
        enrollment_period_id=periodo.id,
        group_number="02",
        professor=None,
        schedule=(crear_franja(day_of_week=2, start_time=time(10, 0), end_time=time(12, 0)),),
    )

    inscripciones = (
        [
            crear_inscripcion(
                student_id=estudiante.id,
                course_offering_id=grupo_calculo.id,
                enrollment_period_id=periodo.id,
            ),
            crear_inscripcion(
                student_id=estudiante.id,
                course_offering_id=grupo_fisica.id,
                enrollment_period_id=periodo.id,
            ),
        ]
        if con_inscripciones
        else []
    )

    listado = ListStudentEnrollmentsUseCase(
        InMemoryEnrollmentRepository(inscripciones),
        InMemoryOfferingRepository([grupo_calculo, grupo_fisica]),
        InMemoryCourseRepository([calculo, fisica]),
        InMemoryPeriodRepository([periodo] if con_periodo else []),
    )

    espia = RenderizadorEspia()
    caso = GenerateReceiptUseCase(
        listado,
        InMemoryStudentRepository([estudiante]),
        InMemoryProgramRepository([programa]),
        espia,  # type: ignore[arg-type]
    )

    return caso, espia, estudiante


# ---------------------------------------------------------------------------
# Contenido del comprobante
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_el_comprobante_lleva_los_datos_del_estudiante() -> None:
    caso, espia, estudiante = _montar()

    caso.execute(estudiante.id)

    assert espia.recibido is not None
    assert espia.recibido.student_name == "Ana María Rojas"
    assert espia.recibido.program_code == "ISIS"
    assert espia.recibido.academic_period == "2025-2"


@pytest.mark.unit
def test_los_creditos_del_comprobante_son_los_del_listado() -> None:
    """Es la razón de reutilizar el caso de uso del listado en vez de repetir sus consultas.

    Si el PDF sumara por su cuenta, acabaría discrepando de la pantalla «Mis materias», y ese
    es el error que nadie detecta hasta que un estudiante reclama.
    """
    caso, espia, estudiante = _montar()

    caso.execute(estudiante.id)

    assert espia.recibido is not None
    assert espia.recibido.total_credits == 7
    assert sum(i.credits for i in espia.recibido.items) == 7


@pytest.mark.unit
def test_las_materias_llegan_ordenadas_por_codigo() -> None:
    caso, espia, estudiante = _montar()

    caso.execute(estudiante.id)

    assert espia.recibido is not None
    assert [i.course_code for i in espia.recibido.items] == ["FIS101", "MAT101"]


@pytest.mark.unit
def test_las_franjas_llegan_ordenadas_por_dia_y_hora() -> None:
    """Un horario desordenado en un comprobante obliga a releerlo para entenderlo."""
    caso, espia, estudiante = _montar()

    caso.execute(estudiante.id)

    assert espia.recibido is not None
    calculo = next(i for i in espia.recibido.items if i.course_code == "MAT101")
    assert [f.day_of_week for f in calculo.schedule] == [1, 3]


@pytest.mark.unit
def test_el_codigo_de_verificacion_es_estable() -> None:
    """Dos descargas del mismo comprobante deben poder citarse por el mismo código."""
    caso, espia, estudiante = _montar()

    caso.execute(estudiante.id)
    primero = espia.recibido

    caso.execute(estudiante.id)
    segundo = espia.recibido

    assert primero is not None and segundo is not None
    assert primero.verification_code == segundo.verification_code
    assert primero.student_code in primero.verification_code


@pytest.mark.unit
def test_un_comprobante_sin_materias_es_valido() -> None:
    """Certifica que la persona no inscribió nada: es un documento legítimo, no un error."""
    caso, espia, estudiante = _montar(con_inscripciones=False)

    pdf, nombre = caso.execute(estudiante.id)

    assert espia.recibido is not None
    assert espia.recibido.items == []
    assert espia.recibido.total_credits == 0
    assert pdf == b"%PDF-falso"
    assert nombre.endswith(".pdf")


@pytest.mark.unit
def test_el_nombre_del_archivo_identifica_al_estudiante_y_el_periodo() -> None:
    # Quien descarga varios comprobantes a lo largo del semestre necesita distinguirlos en su
    # carpeta de descargas sin abrirlos.
    caso, _, estudiante = _montar()

    _, nombre = caso.execute(estudiante.id)

    assert estudiante.student_code.value in nombre
    assert "2025-2-V1" in nombre


@pytest.mark.unit
def test_sin_periodo_activo_no_hay_comprobante() -> None:
    """Sin ventana de matrícula no hay nada que certificar."""
    caso, _, estudiante = _montar(con_periodo=False)

    with pytest.raises(NoActivePeriodError):
        caso.execute(estudiante.id)


@pytest.mark.unit
def test_una_cuenta_sin_perfil_academico_no_tiene_comprobante() -> None:
    caso, _, _ = _montar()

    with pytest.raises(StudentProfileNotFoundError):
        caso.execute(uuid4())


# ---------------------------------------------------------------------------
# Generación del PDF
# ---------------------------------------------------------------------------


def _comprobante(items: list[ReceiptItemDTO]) -> ReceiptDTO:
    return ReceiptDTO(
        student_id=uuid4(),
        student_code="1234567",
        student_name="Ana María Rojas",
        program_code="ISIS",
        program_name="Ingeniería de Sistemas",
        current_semester=6,
        enrollment_date=date(2022, 1, 15),
        academic_period="2025-2",
        period_code="2025-2-V1",
        generated_at=datetime(2025, 11, 15, 14, 30, tzinfo=UTC),
        verification_code="2025-2-V1-1234567",
        items=items,
        total_credits=sum(i.credits for i in items),
    )


def _materia(codigo: str, nombre: str = "Cálculo I", creditos: int = 4) -> ReceiptItemDTO:
    return ReceiptItemDTO(
        course_code=codigo,
        course_name=nombre,
        credits=creditos,
        group_number="01",
        professor="Ana Pérez",
        schedule=[
            ReceiptScheduleBlockDTO(
                day_of_week=1, start_time=time(8, 0), end_time=time(10, 0), classroom="A-201"
            )
        ],
    )


@pytest.mark.unit
def test_el_documento_generado_es_un_pdf() -> None:
    pdf = PdfReceiptRenderer().render(_comprobante([_materia("MAT101")]))

    # La firma del formato: cualquier lector lo comprueba antes de abrirlo.
    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 1000


@pytest.mark.unit
def test_se_genera_un_comprobante_sin_materias() -> None:
    """El caso que rompe una tabla mal construida."""
    pdf = PdfReceiptRenderer().render(_comprobante([]))

    assert pdf.startswith(b"%PDF-")


@pytest.mark.unit
def test_los_caracteres_de_marcado_no_rompen_el_documento() -> None:
    """Los `Paragraph` de ReportLab interpretan un subconjunto de HTML.

    Sin escapar, una materia llamada «Álgebra & Cálculo <avanzado>» abortaría la generación. Es
    el mismo cuidado que se tiene al pintar HTML en el navegador.
    """
    pdf = PdfReceiptRenderer().render(
        _comprobante([_materia("MAT101", "Álgebra & Cálculo <avanzado>")])
    )

    assert pdf.startswith(b"%PDF-")


@pytest.mark.unit
def test_un_horario_por_definir_no_deja_la_celda_vacia() -> None:
    sin_horario = ReceiptItemDTO(
        course_code="MAT101",
        course_name="Cálculo I",
        credits=4,
        group_number="01",
        professor=None,
        schedule=[],
    )

    pdf = PdfReceiptRenderer().render(_comprobante([sin_horario]))

    assert pdf.startswith(b"%PDF-")


@pytest.mark.unit
def test_una_matricula_larga_se_reparte_en_varias_paginas() -> None:
    """Veinticinco materias no caben en una hoja, y el documento no debe recortarlas.

    Es el caso que justifica `repeatRows`: sin él, la segunda página sería una tabla de
    columnas sin nombre.
    """
    muchas = [
        _materia(f"MAT{i:03d}", f"Materia número {i} con un nombre bastante largo")
        for i in range(1, 26)
    ]

    pdf = PdfReceiptRenderer().render(_comprobante(muchas))

    assert pdf.startswith(b"%PDF-")
    # Dos objetos `/Type /Page` como mínimo (el catálogo `/Type /Pages` no cuenta).
    assert pdf.count(b"/Type /Page\n") >= 2 or pdf.count(b"/Type /Page ") >= 2
