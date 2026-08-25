"""Adaptador de `ReceiptRenderer` sobre ReportLab.

Dibuja el comprobante de matrícula en PDF. Es el único módulo del proyecto que sabe qué es una
página, un margen o una tipografía; el caso de uso le entrega el contenido ya compuesto y no
tiene forma de saber si detrás hay un PDF o un HTML.

**Por qué ReportLab y no una conversión desde HTML.** Las alternativas habituales —WeasyPrint,
wkhtmltopdf— convierten HTML a PDF y permiten maquetar con CSS, que es más cómodo. A cambio
exigen librerías del sistema: Cairo, Pango, o un navegador entero. En una imagen que se
despliega en Elastic Beanstalk eso significa cientos de megabytes más y un conjunto de
dependencias nativas que hay que mantener parcheadas. ReportLab es Python puro: se instala con
`pip` y la imagen no cambia de tamaño de forma apreciable.

**El documento se genera en memoria**, nunca en un archivo temporal. Las instancias del
autoescalado son efímeras y su disco no es compartido: un archivo escrito en una instancia no
existe para las demás, y limpiarlos correctamente cuando un proceso muere a mitad es un
problema que no hace falta tener.
"""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.application.dtos.receipt_dto import ReceiptDTO, ReceiptItemDTO
from app.application.ports.document_service import ReceiptRenderer

# Paleta alineada con la del frontend: el comprobante y la aplicación deben parecer el mismo
# sistema. Los valores son los equivalentes en RGB del azul institucional.
_AZUL = colors.HexColor("#1D4ED8")
_AZUL_OSCURO = colors.HexColor("#1E3A8A")
_TINTA = colors.HexColor("#1F2937")
_TINTA_SUAVE = colors.HexColor("#6B7280")
_LINEA = colors.HexColor("#E5E7EB")
_FONDO_SUAVE = colors.HexColor("#F3F4F6")

_MARGEN = 18 * mm

_DIAS = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 7: "Dom"}


class PdfReceiptRenderer(ReceiptRenderer):
    """Implementación del comprobante en PDF."""

    def render(self, receipt: ReceiptDTO) -> bytes:
        buffer = BytesIO()

        documento = BaseDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=_MARGEN,
            rightMargin=_MARGEN,
            topMargin=_MARGEN,
            # Margen inferior mayor: es donde se dibuja el pie con la paginación, y sin
            # espacio reservado el contenido se le montaría encima.
            bottomMargin=_MARGEN + 12 * mm,
            title=f"Comprobante de matrícula {receipt.period_code}",
            author="FlexGrade",
            subject=f"Matrícula {receipt.academic_period} · {receipt.student_code}",
        )

        marco = Frame(
            documento.leftMargin,
            documento.bottomMargin,
            documento.width,
            documento.height,
            id="cuerpo",
        )
        documento.addPageTemplates(
            [
                PageTemplate(
                    id="comprobante",
                    frames=[marco],
                    onPage=lambda lienzo, doc: _dibujar_pie(lienzo, doc, receipt),
                )
            ]
        )

        estilos = _construir_estilos()
        documento.build(list(_componer(receipt, estilos)))

        return buffer.getvalue()


# ---------------------------------------------------------------------------
# Composición
# ---------------------------------------------------------------------------


def _componer(receipt: ReceiptDTO, estilos: dict[str, ParagraphStyle]) -> list[object]:
    """Construye la lista de elementos que ReportLab va colocando en las páginas.

    El flujo se arma de una vez y el motor decide dónde cae cada salto de página. Calcular las
    páginas a mano sería frágil: un nombre de materia largo cambia la altura de su fila y
    desplaza todo lo que viene detrás.
    """
    elementos: list[object] = [
        *_encabezado(receipt, estilos),
        Spacer(1, 6 * mm),
        *_datos_del_estudiante(receipt, estilos),
        Spacer(1, 6 * mm),
        *_materias(receipt, estilos),
        Spacer(1, 6 * mm),
        *_nota_legal(receipt, estilos),
    ]

    return elementos


def _encabezado(receipt: ReceiptDTO, estilos: dict[str, ParagraphStyle]) -> list[object]:
    titulo = Paragraph("Comprobante de matrícula", estilos["titulo"])
    periodo = Paragraph(
        f"Período académico {receipt.academic_period} · Ventana {receipt.period_code}",
        estilos["subtitulo"],
    )

    # La marca a la izquierda y el título a la derecha, en una tabla sin bordes: es la forma
    # más simple de alinear dos bloques en la misma línea base sin posicionar a mano.
    tabla = Table(
        [[Paragraph("FlexGrade", estilos["marca"]), [titulo, periodo]]],
        colWidths=[38 * mm, None],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 1.2, _AZUL),
            ]
        ),
    )

    return [tabla]


def _datos_del_estudiante(receipt: ReceiptDTO, estilos: dict[str, ParagraphStyle]) -> list[object]:
    filas = [
        ["Estudiante", receipt.student_name],
        ["Código", receipt.student_code],
        ["Programa", f"{receipt.program_name} ({receipt.program_code})"],
        ["Semestre", str(receipt.current_semester)],
        ["Ingreso", receipt.enrollment_date.strftime("%d/%m/%Y")],
    ]

    tabla = Table(
        [[Paragraph(e, estilos["etiqueta"]), Paragraph(v, estilos["valor"])] for e, v in filas],
        colWidths=[32 * mm, None],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        ),
    )

    return [Paragraph("Datos del estudiante", estilos["seccion"]), Spacer(1, 2 * mm), tabla]


def _materias(receipt: ReceiptDTO, estilos: dict[str, ParagraphStyle]) -> list[object]:
    encabezado = Paragraph(f"Materias inscritas ({len(receipt.items)})", estilos["seccion"])

    if not receipt.items:
        # Un comprobante sin materias es un documento legítimo: certifica que la persona no
        # inscribió nada. Una tabla vacía se leería como un error de generación.
        return [
            encabezado,
            Spacer(1, 2 * mm),
            Paragraph(
                "No hay materias inscritas en este período. Este comprobante certifica "
                "únicamente ese estado a la fecha indicada.",
                estilos["aviso"],
            ),
        ]

    filas: list[list[object]] = [
        [
            Paragraph("Código", estilos["celdaEncabezado"]),
            Paragraph("Materia", estilos["celdaEncabezado"]),
            Paragraph("Grupo", estilos["celdaEncabezado"]),
            Paragraph("Cr.", estilos["celdaEncabezado"]),
            Paragraph("Horario", estilos["celdaEncabezado"]),
        ]
    ]

    for item in receipt.items:
        filas.append(
            [
                Paragraph(item.course_code, estilos["celdaCodigo"]),
                Paragraph(_materia_con_docente(item), estilos["celda"]),
                Paragraph(item.group_number, estilos["celdaCentrada"]),
                Paragraph(str(item.credits), estilos["celdaCentrada"]),
                Paragraph(_horario(item), estilos["celdaPequena"]),
            ]
        )

    filas.append(
        [
            Paragraph("", estilos["celda"]),
            Paragraph("Total de créditos", estilos["celdaTotal"]),
            Paragraph("", estilos["celda"]),
            Paragraph(str(receipt.total_credits), estilos["celdaTotalCentrada"]),
            Paragraph("", estilos["celda"]),
        ]
    )

    tabla = Table(
        filas,
        colWidths=[20 * mm, None, 14 * mm, 10 * mm, 46 * mm],
        # `repeatRows` reimprime la cabecera en cada página. Sin ella, la segunda página de un
        # estudiante con muchas materias sería una tabla de columnas sin nombre.
        repeatRows=1,
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _AZUL_OSCURO),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 1), (-1, -2), 0.5, _LINEA),
                # Filas alternas: en una tabla de cinco columnas ayudan a seguir la línea sin
                # perderse, y se imprimen bien incluso en blanco y negro.
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, _FONDO_SUAVE]),
                ("LINEABOVE", (0, -1), (-1, -1), 1, _AZUL),
                ("TOPPADDING", (0, -1), (-1, -1), 7),
            ]
        ),
    )

    return [encabezado, Spacer(1, 2 * mm), tabla]


def _nota_legal(receipt: ReceiptDTO, estilos: dict[str, ParagraphStyle]) -> list[object]:
    generado = receipt.generated_at.strftime("%d/%m/%Y a las %H:%M UTC")

    texto = (
        f"Documento generado el {generado}. "
        f"Código de verificación: <b>{receipt.verification_code}</b>. "
        "Este comprobante refleja el estado de la matrícula en el momento de su generación; "
        "durante la ventana de inscripción el contenido puede cambiar. "
        "No constituye una firma electrónica: para validarlo, consulte el código de "
        "verificación con Registro Académico."
    )

    # `KeepTogether` impide que la nota quede partida entre dos páginas, que es donde peor se
    # lee y donde más fácil es pasar por alto la advertencia.
    return [KeepTogether([Paragraph(texto, estilos["nota"])])]


# ---------------------------------------------------------------------------
# Utilidades de formato
# ---------------------------------------------------------------------------


def _materia_con_docente(item: ReceiptItemDTO) -> str:
    docente = item.professor or "Docente por asignar"

    return f"<b>{_escapar(item.course_name)}</b><br/><font size=7.5>{_escapar(docente)}</font>"


def _horario(item: ReceiptItemDTO) -> str:
    if not item.schedule:
        return "Horario por definir"

    lineas = []

    for franja in item.schedule:
        dia = _DIAS.get(franja.day_of_week, str(franja.day_of_week))
        aula = f" · {_escapar(franja.classroom)}" if franja.classroom else ""
        lineas.append(
            f"{dia} {franja.start_time.strftime('%H:%M')}–{franja.end_time.strftime('%H:%M')}{aula}"
        )

    return "<br/>".join(lineas)


def _escapar(texto: str) -> str:
    """Neutraliza los caracteres que ReportLab interpretaría como marcado.

    Los `Paragraph` admiten un subconjunto de HTML, así que un nombre con `&` o `<` rompería la
    generación del documento. Es el mismo cuidado que se tiene al pintar HTML en el navegador:
    el dato del usuario nunca se concatena crudo dentro del marcado.
    """
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _dibujar_pie(lienzo: Canvas, documento: BaseDocTemplate, receipt: ReceiptDTO) -> None:
    """Pie de página con la referencia y la paginación.

    Se dibuja directamente sobre el lienzo, fuera del flujo, para que aparezca en TODAS las
    páginas sin ocupar espacio en el contenido. La paginación importa aquí: un comprobante de
    dos hojas del que solo se imprime una queda incompleto sin que nadie lo note.
    """
    lienzo.saveState()
    lienzo.setFont("Helvetica", 7.5)
    lienzo.setFillColor(_TINTA_SUAVE)

    y = _MARGEN + 4 * mm

    lienzo.drawString(
        _MARGEN,
        y,
        f"{receipt.student_code} · {receipt.period_code} · Ref. {receipt.verification_code}",
    )
    lienzo.drawRightString(A4[0] - _MARGEN, y, f"Página {documento.page}")

    lienzo.setStrokeColor(_LINEA)
    lienzo.setLineWidth(0.5)
    lienzo.line(_MARGEN, y + 3.5 * mm, A4[0] - _MARGEN, y + 3.5 * mm)

    lienzo.restoreState()


def _construir_estilos() -> dict[str, ParagraphStyle]:
    """Estilos del documento.

    Se usan las tipografías base de PDF (Helvetica) y no una fuente propia: van incrustadas en
    todo lector, así que el comprobante se ve igual en cualquier equipo sin sumar el archivo de
    la fuente al peso del documento.
    """
    base = getSampleStyleSheet()["BodyText"]

    def estilo(nombre: str, **kwargs: object) -> ParagraphStyle:
        return ParagraphStyle(nombre, parent=base, **kwargs)

    return {
        "marca": estilo(
            "marca", fontName="Helvetica-Bold", fontSize=17, textColor=_AZUL, leading=20
        ),
        "titulo": estilo(
            "titulo",
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=_TINTA,
            leading=17,
            alignment=2,
        ),
        "subtitulo": estilo(
            "subtitulo", fontSize=8.5, textColor=_TINTA_SUAVE, leading=11, alignment=2
        ),
        "seccion": estilo(
            "seccion", fontName="Helvetica-Bold", fontSize=10, textColor=_AZUL_OSCURO, leading=13
        ),
        "etiqueta": estilo("etiqueta", fontSize=8.5, textColor=_TINTA_SUAVE, leading=12),
        "valor": estilo(
            "valor", fontName="Helvetica-Bold", fontSize=8.5, textColor=_TINTA, leading=12
        ),
        "celdaEncabezado": estilo(
            "celdaEncabezado",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=colors.white,
            leading=11,
        ),
        "celda": estilo("celda", fontSize=8.5, textColor=_TINTA, leading=11),
        "celdaPequena": estilo("celdaPequena", fontSize=7.5, textColor=_TINTA, leading=10),
        "celdaCodigo": estilo(
            "celdaCodigo",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            textColor=_AZUL_OSCURO,
            leading=11,
        ),
        "celdaCentrada": estilo(
            "celdaCentrada", fontSize=8.5, textColor=_TINTA, leading=11, alignment=TA_CENTER
        ),
        "celdaTotal": estilo(
            "celdaTotal",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=_TINTA,
            leading=12,
            alignment=2,
        ),
        "celdaTotalCentrada": estilo(
            "celdaTotalCentrada",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=_AZUL_OSCURO,
            leading=12,
            alignment=TA_CENTER,
        ),
        "aviso": estilo("aviso", fontSize=9, textColor=_TINTA_SUAVE, leading=13),
        "nota": estilo("nota", fontSize=7.5, textColor=_TINTA_SUAVE, leading=10.5),
    }
