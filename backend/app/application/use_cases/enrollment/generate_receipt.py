"""Caso de uso: comprobante de matrícula del estudiante."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.application.dtos.receipt_dto import ReceiptDTO, ReceiptItemDTO, ReceiptScheduleBlockDTO
from app.application.ports.document_service import ReceiptRenderer
from app.application.ports.repositories.program_repository import ProgramRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.use_cases.enrollment.list_student_enrollments import (
    ListStudentEnrollmentsUseCase,
)
from app.domain.exceptions.authentication import StudentProfileNotFoundError
from app.domain.exceptions.catalog import ProgramNotFoundError


class GenerateReceiptUseCase:
    """Compone el comprobante de matrícula y lo entrega ya dibujado.

    Reutiliza `ListStudentEnrollmentsUseCase` en vez de repetir sus consultas, y eso es lo que
    garantiza que el PDF diga EXACTAMENTE lo mismo que la pantalla «Mis materias». Duplicar la
    lógica sería la forma más fácil de acabar con un comprobante que suma distintos créditos
    que la interfaz, y ese es justo el error que nadie detecta hasta que un estudiante reclama.

    El documento se genera al vuelo, en cada petición, y no se guarda en ningún sitio. Durante
    la ventana de matrícula el contenido cambia con cada inscripción, así que un archivo
    almacenado quedaría obsoleto de inmediato; y guardarlo en Azure Storage obligaría a invalidarlo
    en cada operación para un documento que se descarga una o dos veces por semestre.
    """

    def __init__(
        self,
        enrollments_use_case: ListStudentEnrollmentsUseCase,
        student_repository: StudentRepository,
        program_repository: ProgramRepository,
        renderer: ReceiptRenderer,
    ) -> None:
        self._enrollments = enrollments_use_case
        self._students = student_repository
        self._programs = program_repository
        self._renderer = renderer

    def execute(self, student_id: UUID) -> tuple[bytes, str]:
        """Genera el comprobante del estudiante.

        Args:
            student_id: estudiante cuyo comprobante se genera. Sale del token, nunca de la
                petición: nadie puede descargar el comprobante de otro.

        Returns:
            Los bytes del PDF y el nombre de archivo sugerido.

        Raises:
            StudentProfileNotFoundError: si la cuenta no tiene perfil académico.
            ProgramNotFoundError: si el programa del estudiante ya no existe.
            NoActivePeriodError: si no hay ventana de matrícula activa. Sin período no hay
                matrícula que certificar.
        """
        estudiante = self._students.find_by_id(student_id)

        if estudiante is None:
            raise StudentProfileNotFoundError()

        programa = self._programs.find_by_id(estudiante.program_id)

        if programa is None:
            raise ProgramNotFoundError(estudiante.program_id)

        inscripciones = self._enrollments.execute(student_id)

        comprobante = ReceiptDTO(
            student_id=estudiante.id,
            student_code=estudiante.student_code.value,
            student_name=estudiante.full_name,
            program_code=programa.code,
            program_name=programa.name,
            current_semester=estudiante.current_semester,
            enrollment_date=estudiante.enrollment_date,
            academic_period=inscripciones.academic_period,
            period_code=inscripciones.period_code,
            generated_at=datetime.now(UTC),
            verification_code=_codigo_de_verificacion(
                estudiante.student_code.value, inscripciones.period_code
            ),
            items=[
                ReceiptItemDTO(
                    course_code=i.course_code,
                    course_name=i.course_name,
                    credits=i.credits,
                    group_number=i.group_number,
                    professor=i.professor,
                    schedule=[
                        ReceiptScheduleBlockDTO(
                            day_of_week=f.day_of_week,
                            start_time=f.start_time,
                            end_time=f.end_time,
                            classroom=f.classroom,
                        )
                        for f in sorted(i.schedule, key=lambda f: (f.day_of_week, f.start_time))
                    ],
                )
                for i in inscripciones.items
            ],
            total_credits=inscripciones.total_credits,
        )

        nombre = (
            f"comprobante-matricula-{estudiante.student_code.value}-{inscripciones.period_code}.pdf"
        )

        return self._renderer.render(comprobante), nombre


def _codigo_de_verificacion(student_code: str, period_code: str) -> str:
    """Construye la referencia con la que Registro Académico localiza la matrícula.

    Es determinista a propósito: el mismo estudiante y el mismo período dan siempre el mismo
    código, así que dos descargas del comprobante son comparables y una persona puede citarlo
    por teléfono sin que dependa de cuándo lo descargó.

    NO es una firma: no prueba que el documento no se haya alterado, y no pretende hacerlo.
    Para eso haría falta firmar el PDF, que exige un certificado y una gestión de claves que
    este proyecto no tiene. Se documenta así en el propio comprobante para no dar a entender
    una garantía que no existe.
    """
    return f"{period_code}-{student_code}"
