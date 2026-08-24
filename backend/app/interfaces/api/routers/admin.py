"""Router de administración académica.

TODOS los endpoints de este router exigen rol `ADMIN`, y esa exigencia se declara **una sola
vez**, en el `dependencies` del router. Repetirla endpoint por endpoint funcionaría igual hasta
el día en que alguien añada uno y se olvide: el endpoint quedaría abierto a cualquier
estudiante autenticado, y nada fallaría de forma visible. Declararla en el router hace que la
protección sea el comportamiento por defecto y no algo que haya que recordar.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.application.dtos.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.enrollment_period import EnrollmentPeriod
from app.domain.value_objects.schedule_block import ScheduleBlock
from app.interfaces.api.dependencies.auth import require_admin
from app.interfaces.api.dependencies.di import (
    ActivateEnrollmentPeriodUseCaseDep,
    AdjustOfferingCapacityUseCaseDep,
    CreateCourseOfferingUseCaseDep,
    CreateCourseUseCaseDep,
    CreateEnrollmentPeriodUseCaseDep,
    ListEnrollmentPeriodsUseCaseDep,
)
from app.interfaces.api.routers.courses import a_schema_de_grupo
from app.interfaces.api.schemas.admin_schemas import (
    CreateCourseSchema,
    CreateEnrollmentPeriodSchema,
    CreateOfferingSchema,
    EnrollmentPeriodSchema,
    UpdateCapacitySchema,
)
from app.interfaces.api.schemas.catalog_schemas import (
    CourseSchema,
    OfferingDetailSchema,
    PageSchema,
)
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema

router = APIRouter(
    prefix="/admin",
    tags=["administracion"],
    dependencies=[Depends(require_admin)],
    responses={
        401: {"model": ErrorResponseSchema, "description": "Token ausente o inválido"},
        403: {"model": ErrorResponseSchema, "description": "Se requiere rol de administrador"},
    },
)


@router.post(
    "/enrollment-periods",
    response_model=EnrollmentPeriodSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una ventana de matrícula",
    responses={
        409: {
            "model": ErrorResponseSchema,
            "description": "Ya existe una ventana con ese código, o el rango de fechas es inválido",
        }
    },
)
def create_enrollment_period(
    payload: CreateEnrollmentPeriodSchema,
    use_case: CreateEnrollmentPeriodUseCaseDep,
) -> EnrollmentPeriodSchema:
    """Registra una ventana de matrícula nueva, **desactivada**.

    Crear y activar son operaciones separadas: permite preparar la ventana con antelación y
    abrirla cuando corresponda, sin que se abra sola al llegar la fecha.
    """
    periodo = use_case.execute(
        code=payload.code,
        academic_period=payload.academic_period,
        name=payload.name,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )

    return _a_schema(periodo)


def _a_schema(periodo: EnrollmentPeriod) -> EnrollmentPeriodSchema:
    """Traduce la entidad a su representación pública."""
    return EnrollmentPeriodSchema(
        id=periodo.id,
        code=periodo.code,
        academic_period=periodo.academic_period,
        name=periodo.name,
        starts_at=periodo.starts_at,
        ends_at=periodo.ends_at,
        is_active=periodo.is_active,
    )


@router.get(
    "/enrollment-periods",
    response_model=PageSchema[EnrollmentPeriodSchema],
    status_code=status.HTTP_200_OK,
    summary="Listar las ventanas de matrícula",
)
def list_enrollment_periods(
    use_case: ListEnrollmentPeriodsUseCaseDep,
    page: Annotated[int, Query(ge=1, description="Número de página")] = 1,
    size: Annotated[
        int, Query(ge=1, le=MAX_PAGE_SIZE, description="Ventanas por página")
    ] = DEFAULT_PAGE_SIZE,
) -> PageSchema[EnrollmentPeriodSchema]:
    """Lista las ventanas, de la más reciente a la más antigua.

    Es lo que permite obtener el identificador de una ventana para activarla, sin depender de
    haber guardado la respuesta de su creación.
    """
    resultado = use_case.execute(page=page, size=size)

    return PageSchema[EnrollmentPeriodSchema](
        items=[_a_schema(p) for p in resultado.items],
        total=resultado.total,
        page=resultado.page,
        size=resultado.size,
    )


@router.put(
    "/enrollment-periods/{period_id}/activate",
    response_model=EnrollmentPeriodSchema,
    status_code=status.HTTP_200_OK,
    summary="Abrir una ventana de matrícula",
    responses={404: {"model": ErrorResponseSchema, "description": "La ventana no existe"}},
)
def activate_enrollment_period(
    period_id: UUID,
    use_case: ActivateEnrollmentPeriodUseCaseDep,
) -> EnrollmentPeriodSchema:
    """Abre la ventana indicada y cierra la que estuviera abierta.

    Las dos escrituras ocurren en la misma transacción y en ese orden: el índice único parcial
    `ix_enrollment_periods_active` prohíbe que existan dos ventanas activas a la vez, así que
    el cambio pasa por «ninguna activa» —un estado válido— y nunca por «dos activas».

    Es idempotente: activar una ventana que ya está abierta devuelve la ventana sin tocar nada.
    """
    return _a_schema(use_case.execute(period_id))


@router.post(
    "/courses",
    response_model=CourseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una materia del catálogo",
    responses={
        409: {
            "model": ErrorResponseSchema,
            "description": "Ya existe una materia con ese código",
        }
    },
)
def create_course(
    payload: CreateCourseSchema,
    use_case: CreateCourseUseCaseDep,
) -> CourseSchema:
    """Da de alta una materia.

    La materia es la definición, no algo que se pueda inscribir: hasta que no se le abra un
    grupo con `POST /admin/offerings` no aparece en ninguna oferta.
    """
    materia = use_case.execute(
        code=payload.code,
        name=payload.name,
        credits=payload.credits,
        description=payload.description,
    )

    return CourseSchema(
        id=materia.id,
        code=materia.code.value,
        name=materia.name,
        credits=materia.credits,
        description=materia.description,
    )


@router.post(
    "/offerings",
    response_model=OfferingDetailSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Abrir un grupo en el período activo",
    responses={
        404: {
            "model": ErrorResponseSchema,
            "description": "No hay período activo, o la materia o el docente no existen",
        },
        409: {
            "model": ErrorResponseSchema,
            "description": "El número de grupo ya existe, o el horario se solapa consigo mismo",
        },
    },
)
def create_offering(
    payload: CreateOfferingSchema,
    use_case: CreateCourseOfferingUseCaseDep,
) -> OfferingDetailSchema:
    """Abre un grupo de una materia en la ventana de matrícula activa.

    El período no viaja en el cuerpo: se toma del activo. Aceptarlo permitiría crear grupos en
    un semestre cerrado por un identificador copiado, y el fallo solo se notaría cuando los
    estudiantes no vieran la materia.
    """
    grupo = use_case.execute(
        course_id=payload.course_id,
        professor_id=payload.professor_id,
        group_number=payload.group_number,
        total_capacity=payload.total_capacity,
        schedule=[
            ScheduleBlock(
                day_of_week=f.day_of_week,
                start_time=f.start_time,
                end_time=f.end_time,
                classroom=f.classroom,
            )
            for f in payload.schedule
        ],
    )

    return _a_schema_de_grupo(grupo)


@router.put(
    "/offerings/{offering_id}/capacity",
    response_model=OfferingDetailSchema,
    status_code=status.HTTP_200_OK,
    summary="Ajustar el cupo de un grupo",
    responses={
        404: {"model": ErrorResponseSchema, "description": "El grupo no existe"},
        409: {
            "model": ErrorResponseSchema,
            "description": "El cupo es menor que los inscritos, o el grupo cambió entretanto",
        },
    },
)
def adjust_offering_capacity(
    offering_id: UUID,
    payload: UpdateCapacitySchema,
    use_case: AdjustOfferingCapacityUseCaseDep,
) -> OfferingDetailSchema:
    """Cambia el cupo total de un grupo.

    No permite bajarlo por debajo del número de inscritos: nadie queda expulsado por un ajuste
    administrativo. Al aplicarse, invalida la entrada de caché del grupo, que guarda el cupo
    total.
    """
    return _a_schema_de_grupo(use_case.execute(offering_id, total_capacity=payload.total_capacity))


def _a_schema_de_grupo(offering: CourseOffering) -> OfferingDetailSchema:
    """Traduce el grupo a la misma forma que devuelve `GET /offerings/{id}`.

    Reutiliza el traductor del catálogo en vez de construir uno propio: si administración
    devolviera un grupo con otra forma, el frontend tendría que distinguir de qué endpoint
    vino para leerlo.
    """
    base = a_schema_de_grupo(offering)

    return OfferingDetailSchema(
        **base.model_dump(),
        course_id=offering.course_id,
        enrollment_period_id=offering.enrollment_period_id,
    )
