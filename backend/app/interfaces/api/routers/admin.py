"""Router de administración académica.

TODOS los endpoints de este router exigen rol `ADMIN`, y esa exigencia se declara **una sola
vez**, en el `dependencies` del router. Repetirla endpoint por endpoint funcionaría igual hasta
el día en que alguien añada uno y se olvide: el endpoint quedaría abierto a cualquier
estudiante autenticado, y nada fallaría de forma visible. Declararla en el router hace que la
protección sea el comportamiento por defecto y no algo que haya que recordar.
"""

from __future__ import annotations

from datetime import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.application.dtos.admin_dto import ScheduleBlockRequest
from app.application.dtos.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.domain.entities.course_offering import CourseOffering
from app.domain.entities.enrollment_period import EnrollmentPeriod
from app.domain.entities.space import Space
from app.domain.value_objects.space_type import SpaceType
from app.interfaces.api.dependencies.auth import require_admin
from app.interfaces.api.dependencies.di import (
    ActivateEnrollmentPeriodUseCaseDep,
    AdjustOfferingCapacityUseCaseDep,
    ConsolidatePeriodUseCaseDep,
    CreateCourseOfferingUseCaseDep,
    CreateCourseUseCaseDep,
    CreateEnrollmentPeriodUseCaseDep,
    CreateSpaceUseCaseDep,
    FindAvailableSpacesUseCaseDep,
    GenerateEnrollmentReportUseCaseDep,
    GenerateOccupancyReportUseCaseDep,
    GetProgramStudyPlanUseCaseDep,
    ListEnrollmentPeriodsUseCaseDep,
    ListSpacesUseCaseDep,
    ProgramRepositoryDep,
    RemovePlanCourseUseCaseDep,
    RemoveRequirementUseCaseDep,
    SetPlanCourseUseCaseDep,
    SetRequirementUseCaseDep,
)
from app.interfaces.api.routers.courses import a_schema_de_grupo
from app.interfaces.api.schemas.admin_schemas import (
    AvailableSpacesSchema,
    ConsolidationSchema,
    CreateCourseSchema,
    CreateEnrollmentPeriodSchema,
    CreateOfferingSchema,
    CreateSpaceSchema,
    EnrollmentPeriodSchema,
    PlanRequirementSchema,
    ProgramPlanEntrySchema,
    ProgramPlanSchema,
    ProgramSchema,
    ProgramsSchema,
    SetPlanCourseSchema,
    SetRequirementSchema,
    SpaceSchema,
    SpacesSchema,
    UpdateCapacitySchema,
)
from app.interfaces.api.schemas.catalog_schemas import (
    CourseSchema,
    OfferingDetailSchema,
    PageSchema,
)
from app.interfaces.api.schemas.error_schemas import ErrorResponseSchema
from app.interfaces.api.schemas.report_schemas import (
    EnrollmentReportSchema,
    OccupancyReportSchema,
    OfferingOccupancySchema,
    ProgramEnrollmentsSchema,
    ReportTotalsSchema,
)

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
            # El aula viaja como CÓDIGO y sin resolver: buscarla en el inventario y fallar si
            # no existe es una decisión, y este router no decide.
            ScheduleBlockRequest(
                day_of_week=f.day_of_week,
                start_time=f.start_time,
                end_time=f.end_time,
                space_code=f.space_code,
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


@router.post(
    "/spaces",
    response_model=SpaceSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta un espacio físico",
    responses={
        409: {"model": ErrorResponseSchema, "description": "Ya existe un espacio con ese código"},
    },
)
def create_space(payload: CreateSpaceSchema, use_case: CreateSpaceUseCaseDep) -> SpaceSchema:
    """Crea un aula, un laboratorio o un auditorio.

    Hasta la iteración 8.3 el inventario solo se poblaba con el seed: dar de alta un aula nueva
    exigía un `INSERT` escrito por alguien con acceso a PostgreSQL.

    El código se guarda NORMALIZADO, en mayúsculas y sin espacios. Sin eso, `a-201` y `A-201`
    convivirían como dos aulas distintas y la restricción de doble reserva no podría impedir
    nada, porque creería que son sitios diferentes.
    """
    return _a_schema_de_espacio(
        use_case.execute(
            code=payload.code,
            space_type=payload.space_type,
            name=payload.name,
            capacity=payload.capacity,
            campus=payload.campus,
            building=payload.building,
        )
    )


@router.get(
    "/spaces",
    response_model=SpacesSchema,
    status_code=status.HTTP_200_OK,
    summary="Inventario de espacios físicos",
)
def list_spaces(
    use_case: ListSpacesUseCaseDep,
    space_type: Annotated[SpaceType | None, Query(description="Filtra por tipo")] = None,
    campus: Annotated[str | None, Query(max_length=100, description="Filtra por sede")] = None,
) -> SpacesSchema:
    """Lista el inventario completo, con filtros opcionales.

    Sin paginar: son decenas o pocos cientos, y quien asigna un aula necesita verlos todos.
    """
    espacios = use_case.execute(space_type=space_type, campus=campus)

    return SpacesSchema(items=[_a_schema_de_espacio(e) for e in espacios], total=len(espacios))


@router.get(
    "/programs",
    response_model=ProgramsSchema,
    status_code=status.HTTP_200_OK,
    summary="Programas académicos",
)
def list_programs(repositorio: ProgramRepositoryDep) -> ProgramsSchema:
    """Lista los programas, para poder elegir cuál plan editar.

    Es la única lectura de este router que no pasa por un caso de uso, y no por descuido: no hay
    ninguna decisión que tomar —ni filtros, ni orden que elegir, ni reglas— y envolverla en una
    clase que solo delega añadiría una capa sin nada dentro.
    """
    programas = repositorio.find_all()

    return ProgramsSchema(
        items=[
            ProgramSchema(id=p.id, code=p.code, name=p.name, total_semesters=p.total_semesters)
            for p in programas
        ],
        total=len(programas),
    )


@router.get(
    "/programs/{program_id}/plan",
    response_model=ProgramPlanSchema,
    status_code=status.HTTP_200_OK,
    summary="Plan de estudios de un programa",
    responses={404: {"model": ErrorResponseSchema, "description": "El programa no existe"}},
)
def program_study_plan(
    program_id: UUID, use_case: GetProgramStudyPlanUseCaseDep
) -> ProgramPlanSchema:
    """Devuelve el plan de un programa cualquiera.

    Se distingue de `GET /students/me/study-plan` en QUIÉN elige el programa, y esa diferencia
    es una regla de autorización: allí sale del token y no puede elegirse, porque un estudiante
    que pasara el identificador de otra carrera vería materias que no puede inscribir. Aquí lo
    elige quien administra, que tiene que poder editar cualquiera.

    No trae el semáforo: aquel cruza el plan con el historial de una persona concreta, y aquí se
    está editando la carrera, no consultando el avance de nadie.
    """
    plan = use_case.execute(program_id)

    return ProgramPlanSchema(
        program_id=plan.program_id,
        program_code=plan.program_code,
        program_name=plan.program_name,
        total_semesters=plan.total_semesters,
        total_credits=plan.total_credits,
        courses=[
            ProgramPlanEntrySchema(
                id=e.course.id,
                code=e.course.code.value,
                name=e.course.name,
                credits=e.course.credits,
                suggested_semester=e.suggested_semester,
                is_mandatory=e.is_mandatory,
                requirements=[
                    PlanRequirementSchema(
                        course_id=r.course.id,
                        code=r.course.code.value,
                        name=r.course.name,
                        requirement_type=r.requirement_type.value,
                    )
                    for r in e.requirements
                ],
            )
            for e in plan.entries
        ],
    )


@router.put(
    "/programs/{program_id}/plan/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Poner una materia en el plan de un programa",
    responses={
        404: {"model": ErrorResponseSchema, "description": "El programa o la materia no existen"},
    },
)
def set_plan_course(
    program_id: UUID,
    course_id: UUID,
    payload: SetPlanCourseSchema,
    use_case: SetPlanCourseUseCaseDep,
) -> Response:
    """Añade la materia al plan, o cambia sus datos si ya estaba.

    `PUT` porque es idempotente: la clave de `program_courses` es la pareja `(programa,
    materia)`, así que no hay diferencia entre añadir y editar que quien administra tenga que
    conocer de antemano.
    """
    use_case.execute(
        program_id=program_id,
        course_id=course_id,
        suggested_semester=payload.suggested_semester,
        is_mandatory=payload.is_mandatory,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/programs/{program_id}/plan/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sacar una materia del plan de un programa",
    responses={
        404: {"model": ErrorResponseSchema, "description": "La materia no estaba en ese plan"},
        409: {
            "model": ErrorResponseSchema,
            "description": "Otras materias del plan la exigen",
        },
    },
)
def remove_plan_course(
    program_id: UUID, course_id: UUID, use_case: RemovePlanCourseUseCaseDep
) -> Response:
    """Retira la materia del plan.

    Se rechaza si otra materia del plan la exige. La clave foránea de los requisitos apunta a
    `program_courses` con `ON DELETE CASCADE`, así que sacarla borraría en silencio el requisito
    que la nombra, y nadie se enteraría hasta que un estudiante inscribiera la materia que
    dependía de ella.
    """
    use_case.execute(program_id=program_id, course_id=course_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/programs/{program_id}/plan/{course_id}/requirements/{required_course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cargar un requisito en el plan de un programa",
    responses={
        404: {"model": ErrorResponseSchema, "description": "Alguna materia no está en ese plan"},
        409: {
            "model": ErrorResponseSchema,
            "description": "El requisito cerraría un ciclo imposible, o dejaría atrapados a los "
            "ya matriculados",
        },
    },
)
def set_requirement(
    program_id: UUID,
    course_id: UUID,
    required_course_id: UUID,
    payload: SetRequirementSchema,
    use_case: SetRequirementUseCaseDep,
) -> Response:
    """Deja el requisito cargado, o le cambia el tipo si ya estaba.

    `PUT` porque es idempotente: la clave de `program_course_requirements` es la terna
    `(programa, materia, exigida)` y NO incluye el tipo, así que volver a cargarla con otro tipo
    lo cambia en vez de duplicar la regla.

    **Los requisitos son retroactivos** y el plan no se versiona. Se rechazan dos casos:

    - El que cerraría un **ciclo imposible** —una vuelta con al menos un prerrequisito—, que
      dejaría todas las materias del ciclo ininscribibles para siempre sin que nada avisara.
    - El **correquisito que atraparía** a quien ya está matriculado. Solo con la ventana
      CERRADA: con la ventana abierta el estudiante ve el pendiente en su lista de inscripciones
      y lo resuelve inscribiendo lo que falta.
    """
    use_case.execute(
        program_id=program_id,
        course_id=course_id,
        required_course_id=required_course_id,
        requirement_type=payload.requirement_type,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/programs/{program_id}/plan/{course_id}/requirements/{required_course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar un requisito del plan de un programa",
    responses={
        404: {"model": ErrorResponseSchema, "description": "Ese requisito no estaba cargado"},
    },
)
def remove_requirement(
    program_id: UUID,
    course_id: UUID,
    required_course_id: UUID,
    use_case: RemoveRequirementUseCaseDep,
) -> Response:
    """Retira el requisito.

    No tiene la comprobación de matriculados que sí tiene cargarlo, y no es una omisión: relajar
    una regla no puede dejar a nadie incompleto. Quien la cumplía sigue cumpliendo el plan, y
    quien no, deja de estar bloqueado.
    """
    use_case.execute(
        program_id=program_id, course_id=course_id, required_course_id=required_course_id
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/enrollment-periods/{period_id}/close",
    response_model=ConsolidationSchema,
    status_code=status.HTTP_200_OK,
    summary="Cerrar el semestre y llevar sus notas al historial",
    responses={
        404: {"model": ErrorResponseSchema, "description": "El período no existe"},
        409: {
            "model": ErrorResponseSchema,
            "description": (
                "Ya se consolidó, la ventana sigue abierta, quedan notas por poner, o alguna "
                "materia ya consta en ese semestre"
            ),
        },
    },
)
def close_enrollment_period(
    period_id: UUID,
    use_case: ConsolidatePeriodUseCaseDep,
) -> ConsolidationSchema:
    """Convierte las notas del período en historial académico.

    **Es la operación que cierra el ciclo académico y la única IRREVERSIBLE del sistema.** Lo que
    queda en `academic_history` decide prerrequisitos y aparece en el expediente; no hay
    operación que lo deshaga.

    Por eso todo se comprueba antes de escribir nada, y los cuatro rechazos van por separado:

    - `PERIOD_ALREADY_CONSOLIDATED`: repetirlo duplicaría el expediente.
    - `PERIOD_STILL_OPEN`: escribiría el expediente de un semestre en el que todavía entra
      gente, y quien se matriculara después no aparecería nunca en el historial.
    - `PERIOD_HAS_UNGRADED_ENROLLMENTS`: no hay valor con el que rellenar una nota que falta.
      `details.offerings` trae los grupos, porque el siguiente paso es hablar con esos docentes.
    - `ALREADY_IN_ACADEMIC_HISTORY`: alguna materia ya consta en ese semestre.

    Todo ocurre en una transacción: un cierre a medias dejaría estudiantes con medio expediente
    y prerrequisitos que se cumplen o no según la materia, que es el peor fallo posible porque
    no se parece a un fallo.
    """
    resumen = use_case.execute(period_id)

    return ConsolidationSchema(
        period_id=resumen.period_id,
        period_code=resumen.period_code,
        academic_period=resumen.academic_period,
        consolidated_at=resumen.consolidated_at,
        records=resumen.records,
        approved=resumen.approved,
    )


def _a_schema_de_espacio(espacio: Space) -> SpaceSchema:
    """Traduce la entidad `Space` a su representación pública."""
    return SpaceSchema(
        id=espacio.id,
        code=espacio.code,
        name=espacio.name,
        space_type=espacio.space_type.value,
        capacity=espacio.capacity,
        campus=espacio.campus,
        building=espacio.building,
    )


@router.get(
    "/spaces/available",
    response_model=AvailableSpacesSchema,
    status_code=status.HTTP_200_OK,
    summary="Espacios libres en una franja horaria",
    responses={
        400: {"model": ErrorResponseSchema, "description": "La franja pedida no es válida"},
        404: {"model": ErrorResponseSchema, "description": "No hay período activo"},
    },
)
def available_spaces(
    use_case: FindAvailableSpacesUseCaseDep,
    day_of_week: Annotated[int, Query(ge=1, le=7, description="1 = lunes … 7 = domingo")],
    start_time: Annotated[time, Query(description="Hora de inicio, `HH:MM`")],
    end_time: Annotated[time, Query(description="Hora de fin, `HH:MM`")],
    min_capacity: Annotated[
        int | None, Query(ge=1, description="Personas que tienen que caber")
    ] = None,
    space_type: Annotated[
        SpaceType | None, Query(description="Aula, laboratorio o auditorio")
    ] = None,
) -> AvailableSpacesSchema:
    """Responde qué espacios están libres en esa franja del período activo.

    Es lo que convierte la asignación de aulas de un ejercicio de memoria en una consulta: sin
    esto, la única forma de encontrar un aula libre es probar códigos contra
    `POST /admin/offerings` y coleccionar rechazos.

    El período no se puede elegir: es siempre el activo. Uno copiado de otro semestre devolvería
    disponibilidad de un período cerrado, y el error solo se notaría al abrir el grupo.
    """
    espacios = use_case.execute(
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        min_capacity=min_capacity,
        space_type=space_type,
    )

    return AvailableSpacesSchema(
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        total=len(espacios),
        items=[
            SpaceSchema(
                id=e.id,
                code=e.code,
                name=e.name,
                space_type=e.space_type.value,
                capacity=e.capacity,
                campus=e.campus,
                building=e.building,
            )
            for e in espacios
        ],
    )


@router.get(
    "/reports/enrollments",
    response_model=EnrollmentReportSchema,
    status_code=status.HTTP_200_OK,
    summary="Reporte de inscripciones del período activo",
    responses={
        404: {"model": ErrorResponseSchema, "description": "No hay período activo"},
    },
)
def enrollment_report(use_case: GenerateEnrollmentReportUseCaseDep) -> EnrollmentReportSchema:
    """Devuelve las cifras de matrícula del período activo, calculadas en vivo.

    No se cachea: es el reporte que se consulta MIENTRAS la matrícula ocurre, y una cifra de
    hace treinta segundos que parece actual es peor que no tener reporte.
    """
    reporte = use_case.execute()

    return EnrollmentReportSchema(
        period_code=reporte.period_code,
        generated_at=reporte.generated_at,
        totals=ReportTotalsSchema(
            total_enrollments=reporte.totals.total_enrollments,
            unique_students=reporte.totals.unique_students,
            active_offerings=reporte.totals.active_offerings,
        ),
        by_program=[
            ProgramEnrollmentsSchema(
                program_code=p.program_code,
                program_name=p.program_name,
                enrollments=p.enrollments,
                students=p.students,
            )
            for p in reporte.by_program
        ],
    )


@router.get(
    "/reports/occupancy",
    response_model=OccupancyReportSchema,
    status_code=status.HTTP_200_OK,
    summary="Reporte de ocupación por grupo",
    responses={
        404: {"model": ErrorResponseSchema, "description": "No hay período activo"},
    },
)
def occupancy_report(
    use_case: GenerateOccupancyReportUseCaseDep,
    page: Annotated[int, Query(ge=1, description="Número de página")] = 1,
    size: Annotated[
        int, Query(ge=1, le=MAX_PAGE_SIZE, description="Grupos por página")
    ] = DEFAULT_PAGE_SIZE,
) -> OccupancyReportSchema:
    """Devuelve la ocupación de los grupos del período, del más lleno al más vacío.

    El orden no es cosmético: la primera página contiene los grupos a punto de llenarse, que
    son sobre los que hay que decidir si se amplía el cupo o se abre otro grupo.
    """
    reporte = use_case.execute(page=page, size=size)

    return OccupancyReportSchema(
        period_code=reporte.period_code,
        generated_at=reporte.generated_at,
        offerings=[
            OfferingOccupancySchema(
                offering_id=o.offering_id,
                course_code=o.course_code,
                course_name=o.course_name,
                group_number=o.group_number,
                total_capacity=o.total_capacity,
                enrolled_count=o.enrolled_count,
                available_slots=o.available_slots,
                occupancy_rate=o.occupancy_rate,
            )
            for o in reporte.offerings
        ],
        total=reporte.total,
        page=reporte.page,
        size=reporte.size,
    )
