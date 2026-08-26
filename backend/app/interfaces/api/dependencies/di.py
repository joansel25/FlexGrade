"""Contenedor de inyección de dependencias de FastAPI.

Es el único lugar donde las abstracciones de `application/ports/` se resuelven a
implementaciones concretas de `infrastructure/`. Los routers y los casos de uso
reciben interfaces y nunca saben qué adaptador hay detrás; cambiar PostgreSQL o
el proveedor de tokens se hace aquí, sin tocar el resto del sistema.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.ports.auth_service import AuthService
from app.application.ports.cache_service import CacheService
from app.application.ports.document_service import ReceiptRenderer
from app.application.ports.repositories.academic_history_repository import AcademicHistoryReader
from app.application.ports.repositories.course_repository import CourseRepository
from app.application.ports.repositories.enrollment_repository import EnrollmentRepository
from app.application.ports.repositories.offering_repository import OfferingRepository
from app.application.ports.repositories.period_repository import PeriodRepository
from app.application.ports.repositories.professor_repository import ProfessorReader
from app.application.ports.repositories.program_repository import ProgramRepository
from app.application.ports.repositories.report_repository import ReportReader
from app.application.ports.repositories.space_repository import SpaceReader, SpaceRepository
from app.application.ports.repositories.student_repository import StudentRepository
from app.application.ports.repositories.user_repository import UserRepository
from app.application.ports.unit_of_work import UnitOfWork
from app.application.use_cases.admin.activate_enrollment_period import (
    ActivateEnrollmentPeriodUseCase,
)
from app.application.use_cases.admin.adjust_offering_capacity import AdjustOfferingCapacityUseCase
from app.application.use_cases.admin.create_course import CreateCourseUseCase
from app.application.use_cases.admin.create_course_offering import CreateCourseOfferingUseCase
from app.application.use_cases.admin.create_enrollment_period import CreateEnrollmentPeriodUseCase
from app.application.use_cases.admin.find_available_spaces import FindAvailableSpacesUseCase
from app.application.use_cases.admin.generate_enrollment_report import (
    GenerateEnrollmentReportUseCase,
)
from app.application.use_cases.admin.generate_occupancy_report import GenerateOccupancyReportUseCase
from app.application.use_cases.admin.list_enrollment_periods import ListEnrollmentPeriodsUseCase
from app.application.use_cases.admin.manage_spaces import CreateSpaceUseCase, ListSpacesUseCase
from app.application.use_cases.admin.manage_study_plan import (
    GetProgramStudyPlanUseCase,
    RemovePlanCourseUseCase,
    RemoveRequirementUseCase,
    SetPlanCourseUseCase,
    SetRequirementUseCase,
)
from app.application.use_cases.auth.authenticate_user import AuthenticateUserUseCase
from app.application.use_cases.auth.refresh_token import RefreshTokenUseCase
from app.application.use_cases.catalog.get_course_detail import GetCourseDetailUseCase
from app.application.use_cases.catalog.get_course_offerings import GetCourseOfferingsUseCase
from app.application.use_cases.catalog.get_current_period import GetCurrentPeriodUseCase
from app.application.use_cases.catalog.get_offering_detail import GetOfferingDetailUseCase
from app.application.use_cases.catalog.get_study_plan import GetStudyPlanUseCase
from app.application.use_cases.catalog.list_courses import ListCoursesUseCase
from app.application.use_cases.enrollment.cancel_enrollment import CancelEnrollmentUseCase
from app.application.use_cases.enrollment.enroll_student import EnrollStudentUseCase
from app.application.use_cases.enrollment.generate_receipt import GenerateReceiptUseCase
from app.application.use_cases.enrollment.get_student_schedule import GetStudentScheduleUseCase
from app.application.use_cases.enrollment.list_student_enrollments import (
    ListStudentEnrollmentsUseCase,
)
from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.cache.client import get_redis_client
from app.infrastructure.cache.redis_cache_service import RedisCacheService
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.documents.pdf_receipt_renderer import PdfReceiptRenderer
from app.infrastructure.persistence.sqlalchemy.repositories.academic_history_repository import (
    SQLAlchemyAcademicHistoryRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.course_repository import (
    SQLAlchemyCourseRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.enrollment_repository import (
    SQLAlchemyEnrollmentRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.offering_repository import (
    SQLAlchemyOfferingRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.period_repository import (
    SQLAlchemyPeriodRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.professor_repository import (
    SQLAlchemyProfessorRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.program_repository import (
    SQLAlchemyProgramRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.report_repository import (
    SQLAlchemyReportRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.space_repository import (
    SQLAlchemySpaceRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.student_repository import (
    SQLAlchemyStudentRepository,
)
from app.infrastructure.persistence.sqlalchemy.repositories.user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.persistence.sqlalchemy.session import get_session
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SQLAlchemyUnitOfWork

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_auth_service(settings: SettingsDep) -> AuthService:
    """Resuelve el puerto de autenticación al adaptador JWT + bcrypt."""
    return JWTAuthService(settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_user_repository(session: SessionDep) -> UserRepository:
    """Resuelve el puerto de usuarios al adaptador de SQLAlchemy."""
    return SQLAlchemyUserRepository(session)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_student_repository(session: SessionDep) -> StudentRepository:
    """Resuelve el puerto de estudiantes al adaptador de SQLAlchemy."""
    return SQLAlchemyStudentRepository(session)


StudentRepositoryDep = Annotated[StudentRepository, Depends(get_student_repository)]


def get_program_repository(session: SessionDep) -> ProgramRepository:
    """Resuelve el puerto de programas al adaptador de SQLAlchemy."""
    return SQLAlchemyProgramRepository(session)


ProgramRepositoryDep = Annotated[ProgramRepository, Depends(get_program_repository)]


def get_course_repository(session: SessionDep) -> CourseRepository:
    """Resuelve el puerto del catálogo de materias al adaptador de SQLAlchemy."""
    return SQLAlchemyCourseRepository(session)


CourseRepositoryDep = Annotated[CourseRepository, Depends(get_course_repository)]


def get_offering_repository(session: SessionDep) -> OfferingRepository:
    """Resuelve el puerto de grupos al adaptador de SQLAlchemy."""
    return SQLAlchemyOfferingRepository(session)


OfferingRepositoryDep = Annotated[OfferingRepository, Depends(get_offering_repository)]


def get_professor_reader(session: SessionDep) -> ProfessorReader:
    """Resuelve el puerto de docentes al adaptador de SQLAlchemy."""
    return SQLAlchemyProfessorRepository(session)


ProfessorReaderDep = Annotated[ProfessorReader, Depends(get_professor_reader)]


def get_space_repository(session: SessionDep) -> SpaceRepository:
    """Resuelve el puerto de espacios físicos al adaptador de SQLAlchemy."""
    return SQLAlchemySpaceRepository(session)


SpaceRepositoryDep = Annotated[SpaceRepository, Depends(get_space_repository)]
SpaceReaderDep = Annotated[SpaceReader, Depends(get_space_repository)]


def get_period_repository(session: SessionDep) -> PeriodRepository:
    """Resuelve el puerto de períodos de matrícula al adaptador de SQLAlchemy."""
    return SQLAlchemyPeriodRepository(session)


PeriodRepositoryDep = Annotated[PeriodRepository, Depends(get_period_repository)]


def get_report_reader(session: SessionDep) -> ReportReader:
    """Resuelve el puerto de reportes al adaptador de SQLAlchemy."""
    return SQLAlchemyReportRepository(session)


ReportReaderDep = Annotated[ReportReader, Depends(get_report_reader)]


def get_enrollment_repository(session: SessionDep) -> EnrollmentRepository:
    """Resuelve el puerto de inscripciones al adaptador de SQLAlchemy."""
    return SQLAlchemyEnrollmentRepository(session)


EnrollmentRepositoryDep = Annotated[EnrollmentRepository, Depends(get_enrollment_repository)]


def get_academic_history_reader(session: SessionDep) -> AcademicHistoryReader:
    """Resuelve el puerto del historial académico al adaptador de SQLAlchemy."""
    return SQLAlchemyAcademicHistoryRepository(session)


AcademicHistoryReaderDep = Annotated[AcademicHistoryReader, Depends(get_academic_history_reader)]


def get_unit_of_work(session: SessionDep) -> UnitOfWork:
    """Resuelve la frontera transaccional sobre la sesión de la petición.

    Recibe la MISMA `SessionDep` que los repositorios, y de ahí depende que funcione: si
    abriera una sesión propia, sus escrituras quedarían en otra transacción y el `commit` no
    guardaría nada de lo que el caso de uso creyó escribir. FastAPI cachea el resultado de
    `get_session` dentro de una misma petición, así que la sesión es una sola.
    """
    return SQLAlchemyUnitOfWork(session)


UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_unit_of_work)]


@lru_cache
def get_cache_service() -> CacheService:
    """Resuelve el puerto de caché al adaptador de Redis.

    Devuelve SIEMPRE la misma instancia, y eso no es una optimización menor: el adaptador
    lleva dentro el cortacircuitos que desactiva Redis tras varios fallos seguidos. Construir
    uno nuevo en cada petición descartaría ese estado antes de que sirviera de nada, y durante
    una caída de Redis cada petición volvería a pagar el tiempo de espera completo —que es
    justo lo que el cortacircuitos existe para evitar—.

    A diferencia de los repositorios, que dependen de la sesión de la petición y por eso se
    construyen en cada una, el adaptador de caché solo depende del cliente de Redis, que ya es
    único por proceso y seguro de compartir.
    """
    return RedisCacheService(get_redis_client())


CacheServiceDep = Annotated[CacheService, Depends(get_cache_service)]


# ---------------------------------------------------------------------------
# Casos de uso del catálogo
# ---------------------------------------------------------------------------


def get_list_courses_use_case(
    course_repository: CourseRepositoryDep,
    cache: CacheServiceDep,
    settings: SettingsDep,
) -> ListCoursesUseCase:
    """Construye el caso de uso del listado del catálogo."""
    return ListCoursesUseCase(course_repository, cache, settings.catalog_cache_ttl_seconds)


def get_course_detail_use_case(
    course_repository: CourseRepositoryDep,
    cache: CacheServiceDep,
    settings: SettingsDep,
) -> GetCourseDetailUseCase:
    """Construye el caso de uso del detalle de una materia."""
    return GetCourseDetailUseCase(course_repository, cache, settings.catalog_cache_ttl_seconds)


def get_course_offerings_use_case(
    course_repository: CourseRepositoryDep,
    offering_repository: OfferingRepositoryDep,
    period_repository: PeriodRepositoryDep,
) -> GetCourseOfferingsUseCase:
    """Construye el caso de uso de los grupos de una materia.

    Sin caché: cada grupo de la respuesta lleva su `enrolled_count`, y refrescarlos todos
    costaría tanto como la consulta original. Cachear la lista entera está descartado, porque
    serviría cupos con antigüedad.
    """
    return GetCourseOfferingsUseCase(course_repository, offering_repository, period_repository)


def get_offering_detail_use_case(
    offering_repository: OfferingRepositoryDep,
    cache: CacheServiceDep,
    settings: SettingsDep,
) -> GetOfferingDetailUseCase:
    """Construye el caso de uso del detalle de un grupo."""
    return GetOfferingDetailUseCase(offering_repository, cache, settings.catalog_cache_ttl_seconds)


def get_current_period_use_case(period_repository: PeriodRepositoryDep) -> GetCurrentPeriodUseCase:
    """Construye el caso de uso del período vigente.

    Sin caché: la respuesta incluye una cuenta atrás en segundos, y servirla desde una entrada
    de hace treinta segundos mostraría un reloj que va atrasado y salta hacia atrás.
    """
    return GetCurrentPeriodUseCase(period_repository)


def get_study_plan_use_case(
    student_repository: StudentRepositoryDep,
    program_repository: ProgramRepositoryDep,
    course_repository: CourseRepositoryDep,
    period_repository: PeriodRepositoryDep,
    offering_repository: OfferingRepositoryDep,
    enrollment_repository: EnrollmentRepositoryDep,
    academic_history: AcademicHistoryReaderDep,
) -> GetStudyPlanUseCase:
    """Construye el caso de uso del plan de estudios.

    SIN CACHÉ, y ahora se ve por qué. El plan de una carrera cambia una vez por semestre y
    parecería el candidato ideal, pero desde la iteración 6.3 la respuesta ya no es el plan:
    es el plan CRUZADO con el historial y la matrícula de quien pregunta. Dos estudiantes de
    la misma carrera reciben cuerpos distintos, y el de cada uno cambia con cada inscripción.
    Cachearlo pediría una clave por persona que habría que invalidar en cada matrícula.

    Recibe el repositorio completo de inscripciones pero lo declara como `EnrollmentReader`:
    aquí solo se lee, y así queda escrito en la firma.
    """
    return GetStudyPlanUseCase(
        student_repository,
        program_repository,
        course_repository,
        period_repository,
        offering_repository,
        enrollment_repository,
        academic_history,
    )


GetStudyPlanUseCaseDep = Annotated[GetStudyPlanUseCase, Depends(get_study_plan_use_case)]


def get_find_available_spaces_use_case(
    space_repository: SpaceRepositoryDep,
    period_repository: PeriodRepositoryDep,
) -> FindAvailableSpacesUseCase:
    """Construye el caso de uso de disponibilidad de espacios.

    Sin caché: la ocupación cambia con cada grupo que se abre, y una respuesta de hace
    treinta segundos ofrecería un aula que otro acaba de tomar.
    """
    return FindAvailableSpacesUseCase(space_repository, period_repository)


FindAvailableSpacesUseCaseDep = Annotated[
    FindAvailableSpacesUseCase, Depends(get_find_available_spaces_use_case)
]


def get_create_space_use_case(
    space_repository: SpaceRepositoryDep, unit_of_work: UnitOfWorkDep
) -> CreateSpaceUseCase:
    """Construye el caso de uso de alta de espacios."""
    return CreateSpaceUseCase(space_repository, unit_of_work)


def get_list_spaces_use_case(space_reader: SpaceReaderDep) -> ListSpacesUseCase:
    """Construye el caso de uso del inventario de espacios."""
    return ListSpacesUseCase(space_reader)


def get_program_study_plan_use_case(
    program_repository: ProgramRepositoryDep, course_repository: CourseRepositoryDep
) -> GetProgramStudyPlanUseCase:
    """Construye el caso de uso del plan de un programa, para administración."""
    return GetProgramStudyPlanUseCase(program_repository, course_repository)


def get_set_plan_course_use_case(
    program_repository: ProgramRepositoryDep,
    course_repository: CourseRepositoryDep,
    unit_of_work: UnitOfWorkDep,
) -> SetPlanCourseUseCase:
    """Construye el caso de uso de edición del plan."""
    return SetPlanCourseUseCase(program_repository, course_repository, unit_of_work)


def get_remove_plan_course_use_case(
    course_repository: CourseRepositoryDep, unit_of_work: UnitOfWorkDep
) -> RemovePlanCourseUseCase:
    """Construye el caso de uso de retirada de una materia del plan."""
    return RemovePlanCourseUseCase(course_repository, unit_of_work)


def get_set_requirement_use_case(
    program_repository: ProgramRepositoryDep,
    course_repository: CourseRepositoryDep,
    enrollment_repository: EnrollmentRepositoryDep,
    period_repository: PeriodRepositoryDep,
    unit_of_work: UnitOfWorkDep,
) -> SetRequirementUseCase:
    """Construye el caso de uso de carga de un requisito.

    Recibe las inscripciones y los períodos, que la edición del plan no necesita, porque es la
    única operación cuyo efecto es RETROACTIVO: para saber si dejaría atrapado a alguien tiene
    que mirar quién está matriculado y si la ventana sigue abierta.
    """
    return SetRequirementUseCase(
        program_repository,
        course_repository,
        enrollment_repository,
        period_repository,
        unit_of_work,
    )


def get_remove_requirement_use_case(
    course_repository: CourseRepositoryDep, unit_of_work: UnitOfWorkDep
) -> RemoveRequirementUseCase:
    """Construye el caso de uso de retirada de un requisito.

    No necesita inscripciones ni períodos: relajar una regla no puede dejar a nadie incompleto.
    """
    return RemoveRequirementUseCase(course_repository, unit_of_work)


CreateSpaceUseCaseDep = Annotated[CreateSpaceUseCase, Depends(get_create_space_use_case)]
ListSpacesUseCaseDep = Annotated[ListSpacesUseCase, Depends(get_list_spaces_use_case)]
GetProgramStudyPlanUseCaseDep = Annotated[
    GetProgramStudyPlanUseCase, Depends(get_program_study_plan_use_case)
]
SetPlanCourseUseCaseDep = Annotated[SetPlanCourseUseCase, Depends(get_set_plan_course_use_case)]
RemovePlanCourseUseCaseDep = Annotated[
    RemovePlanCourseUseCase, Depends(get_remove_plan_course_use_case)
]
SetRequirementUseCaseDep = Annotated[SetRequirementUseCase, Depends(get_set_requirement_use_case)]
RemoveRequirementUseCaseDep = Annotated[
    RemoveRequirementUseCase, Depends(get_remove_requirement_use_case)
]


ListCoursesUseCaseDep = Annotated[ListCoursesUseCase, Depends(get_list_courses_use_case)]
GetCourseDetailUseCaseDep = Annotated[GetCourseDetailUseCase, Depends(get_course_detail_use_case)]
GetCourseOfferingsUseCaseDep = Annotated[
    GetCourseOfferingsUseCase, Depends(get_course_offerings_use_case)
]
GetOfferingDetailUseCaseDep = Annotated[
    GetOfferingDetailUseCase, Depends(get_offering_detail_use_case)
]
GetCurrentPeriodUseCaseDep = Annotated[
    GetCurrentPeriodUseCase, Depends(get_current_period_use_case)
]


def get_authenticate_user_use_case(
    user_repository: UserRepositoryDep,
    auth_service: AuthServiceDep,
) -> AuthenticateUserUseCase:
    """Construye el caso de uso de inicio de sesión con sus dependencias."""
    return AuthenticateUserUseCase(user_repository, auth_service)


def get_refresh_token_use_case(
    user_repository: UserRepositoryDep,
    auth_service: AuthServiceDep,
) -> RefreshTokenUseCase:
    """Construye el caso de uso de renovación de sesión."""
    return RefreshTokenUseCase(user_repository, auth_service)


AuthenticateUserUseCaseDep = Annotated[
    AuthenticateUserUseCase, Depends(get_authenticate_user_use_case)
]
RefreshTokenUseCaseDep = Annotated[RefreshTokenUseCase, Depends(get_refresh_token_use_case)]


# ---------------------------------------------------------------------------
# Casos de uso de inscripción
# ---------------------------------------------------------------------------


def get_enroll_student_use_case(
    enrollment_repository: EnrollmentRepositoryDep,
    offering_repository: OfferingRepositoryDep,
    period_repository: PeriodRepositoryDep,
    course_repository: CourseRepositoryDep,
    student_repository: StudentRepositoryDep,
    academic_history: AcademicHistoryReaderDep,
    unit_of_work: UnitOfWorkDep,
    cache: CacheServiceDep,
) -> EnrollStudentUseCase:
    """Construye el caso de uso de inscripción con sus dependencias.

    Todas son abstracciones (`ARCHITECTURE.md` sección 5, principio D): el caso de uso no sabe
    que detrás hay PostgreSQL ni Redis, y cambiar cualquiera de los dos se hace aquí.

    Los dos servicios de dominio no se inyectan: no tienen estado ni dependencias, así que el
    propio caso de uso los construye. Inyectarlos solo añadiría ruido al cableado.
    """
    return EnrollStudentUseCase(
        enrollment_repository,
        offering_repository,
        period_repository,
        course_repository,
        student_repository,
        academic_history,
        unit_of_work,
        cache,
    )


EnrollStudentUseCaseDep = Annotated[EnrollStudentUseCase, Depends(get_enroll_student_use_case)]


def get_cancel_enrollment_use_case(
    enrollment_repository: EnrollmentRepositoryDep,
    offering_repository: OfferingRepositoryDep,
    course_repository: CourseRepositoryDep,
    student_repository: StudentRepositoryDep,
    unit_of_work: UnitOfWorkDep,
    cache: CacheServiceDep,
) -> CancelEnrollmentUseCase:
    """Construye el caso de uso de cancelación.

    Necesita el catálogo y el estudiante desde la iteración 6.2.1: cancelar dejó de ser una
    operación sin reglas académicas cuando aparecieron los correquisitos, y para aplicarlas hay
    que saber el plan de estudios de quien cancela y qué materias exigen a la que se va.
    """
    return CancelEnrollmentUseCase(
        enrollment_repository,
        offering_repository,
        course_repository,
        student_repository,
        unit_of_work,
        cache,
    )


def get_student_schedule_use_case(
    enrollment_repository: EnrollmentRepositoryDep,
    offering_repository: OfferingRepositoryDep,
    course_repository: CourseRepositoryDep,
    period_repository: PeriodRepositoryDep,
) -> GetStudentScheduleUseCase:
    """Construye el caso de uso del horario.

    Recibe el repositorio completo de inscripciones pero lo declara como `EnrollmentReader`:
    es de solo lectura y así queda escrito en su firma.
    """
    return GetStudentScheduleUseCase(
        enrollment_repository, offering_repository, course_repository, period_repository
    )


def get_list_student_enrollments_use_case(
    enrollment_repository: EnrollmentRepositoryDep,
    offering_repository: OfferingRepositoryDep,
    course_repository: CourseRepositoryDep,
    period_repository: PeriodRepositoryDep,
    student_repository: StudentRepositoryDep,
    academic_history: AcademicHistoryReaderDep,
) -> ListStudentEnrollmentsUseCase:
    """Construye el caso de uso del listado de inscripciones.

    Sin caché: cada inscripción lleva su grupo, y los grupos cambian de cupo constantemente
    durante la ventana. Además es el listado desde el que se cancela, así que servirlo
    desactualizado ofrecería cancelar algo que ya no existe.
    """
    return ListStudentEnrollmentsUseCase(
        enrollment_repository,
        offering_repository,
        course_repository,
        period_repository,
        student_repository,
        academic_history,
    )


ListStudentEnrollmentsUseCaseDep = Annotated[
    ListStudentEnrollmentsUseCase, Depends(get_list_student_enrollments_use_case)
]

CancelEnrollmentUseCaseDep = Annotated[
    CancelEnrollmentUseCase, Depends(get_cancel_enrollment_use_case)
]
GetStudentScheduleUseCaseDep = Annotated[
    GetStudentScheduleUseCase, Depends(get_student_schedule_use_case)
]


# ---------------------------------------------------------------------------
# Casos de uso de administración
# ---------------------------------------------------------------------------


def get_create_enrollment_period_use_case(
    period_repository: PeriodRepositoryDep,
    unit_of_work: UnitOfWorkDep,
) -> CreateEnrollmentPeriodUseCase:
    """Construye el caso de uso de creación de ventanas de matrícula."""
    return CreateEnrollmentPeriodUseCase(period_repository, unit_of_work)


CreateEnrollmentPeriodUseCaseDep = Annotated[
    CreateEnrollmentPeriodUseCase, Depends(get_create_enrollment_period_use_case)
]


def get_activate_enrollment_period_use_case(
    period_repository: PeriodRepositoryDep,
    unit_of_work: UnitOfWorkDep,
) -> ActivateEnrollmentPeriodUseCase:
    """Construye el caso de uso de activación de ventanas."""
    return ActivateEnrollmentPeriodUseCase(period_repository, unit_of_work)


def get_list_enrollment_periods_use_case(
    period_repository: PeriodRepositoryDep,
) -> ListEnrollmentPeriodsUseCase:
    """Construye el caso de uso del listado de ventanas."""
    return ListEnrollmentPeriodsUseCase(period_repository)


ActivateEnrollmentPeriodUseCaseDep = Annotated[
    ActivateEnrollmentPeriodUseCase, Depends(get_activate_enrollment_period_use_case)
]
ListEnrollmentPeriodsUseCaseDep = Annotated[
    ListEnrollmentPeriodsUseCase, Depends(get_list_enrollment_periods_use_case)
]


def get_create_course_use_case(
    course_repository: CourseRepositoryDep,
    unit_of_work: UnitOfWorkDep,
) -> CreateCourseUseCase:
    """Construye el caso de uso de alta de materias."""
    return CreateCourseUseCase(course_repository, unit_of_work)


def get_create_course_offering_use_case(
    offering_repository: OfferingRepositoryDep,
    course_repository: CourseRepositoryDep,
    period_repository: PeriodRepositoryDep,
    professor_reader: ProfessorReaderDep,
    space_reader: SpaceReaderDep,
    unit_of_work: UnitOfWorkDep,
) -> CreateCourseOfferingUseCase:
    """Construye el caso de uso de apertura de grupos."""
    return CreateCourseOfferingUseCase(
        offering_repository,
        course_repository,
        period_repository,
        professor_reader,
        space_reader,
        unit_of_work,
    )


def get_adjust_offering_capacity_use_case(
    offering_repository: OfferingRepositoryDep,
    unit_of_work: UnitOfWorkDep,
    cache: CacheServiceDep,
) -> AdjustOfferingCapacityUseCase:
    """Construye el caso de uso de ajuste de cupo.

    Recibe la caché porque es la única operación de administración que invalida una entrada:
    `catalog:v1:offering:{id}` guarda `total_capacity`, y servirlo caducado junto a un
    `enrolled_count` fresco daría unos cupos disponibles que no cuadran.
    """
    return AdjustOfferingCapacityUseCase(offering_repository, unit_of_work, cache)


CreateCourseUseCaseDep = Annotated[CreateCourseUseCase, Depends(get_create_course_use_case)]
CreateCourseOfferingUseCaseDep = Annotated[
    CreateCourseOfferingUseCase, Depends(get_create_course_offering_use_case)
]
AdjustOfferingCapacityUseCaseDep = Annotated[
    AdjustOfferingCapacityUseCase, Depends(get_adjust_offering_capacity_use_case)
]


def get_enrollment_report_use_case(
    reports: ReportReaderDep,
    period_repository: PeriodRepositoryDep,
) -> GenerateEnrollmentReportUseCase:
    """Construye el caso de uso del reporte de inscripciones.

    Sin caché y sin `UnitOfWork`: solo lee, y sus cifras tienen que ser las de este instante.
    """
    return GenerateEnrollmentReportUseCase(reports, period_repository)


def get_occupancy_report_use_case(
    reports: ReportReaderDep,
    period_repository: PeriodRepositoryDep,
) -> GenerateOccupancyReportUseCase:
    """Construye el caso de uso del reporte de ocupación."""
    return GenerateOccupancyReportUseCase(reports, period_repository)


GenerateEnrollmentReportUseCaseDep = Annotated[
    GenerateEnrollmentReportUseCase, Depends(get_enrollment_report_use_case)
]
GenerateOccupancyReportUseCaseDep = Annotated[
    GenerateOccupancyReportUseCase, Depends(get_occupancy_report_use_case)
]


def get_receipt_renderer() -> ReceiptRenderer:
    """Resuelve el puerto del comprobante al adaptador de ReportLab.

    Sin estado y sin dependencias: se construye en cada petición sin coste apreciable, a
    diferencia del adaptador de caché, que guarda el cortacircuitos y por eso es único.
    """
    return PdfReceiptRenderer()


ReceiptRendererDep = Annotated[ReceiptRenderer, Depends(get_receipt_renderer)]


def get_generate_receipt_use_case(
    enrollment_repository: EnrollmentRepositoryDep,
    offering_repository: OfferingRepositoryDep,
    course_repository: CourseRepositoryDep,
    period_repository: PeriodRepositoryDep,
    student_repository: StudentRepositoryDep,
    program_repository: ProgramRepositoryDep,
    academic_history: AcademicHistoryReaderDep,
    renderer: ReceiptRendererDep,
) -> GenerateReceiptUseCase:
    """Construye el caso de uso del comprobante.

    Recibe el caso de uso del listado ya montado en vez de sus repositorios sueltos: es lo
    que garantiza que el PDF diga exactamente lo mismo que la pantalla «Mis materias»,
    incluida la suma de créditos. El precio de esa garantía es que el comprobante arrastra
    las dependencias del listado aunque no use todo lo que calcula: los correquisitos
    pendientes no se imprimen. Se acepta a cambio de que las dos cifras no puedan divergir,
    que es justo lo que se evitaba al compartir el caso de uso.
    """
    listado = ListStudentEnrollmentsUseCase(
        enrollment_repository,
        offering_repository,
        course_repository,
        period_repository,
        student_repository,
        academic_history,
    )

    return GenerateReceiptUseCase(listado, student_repository, program_repository, renderer)


GenerateReceiptUseCaseDep = Annotated[
    GenerateReceiptUseCase, Depends(get_generate_receipt_use_case)
]
