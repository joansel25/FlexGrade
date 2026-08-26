"""Dependencias de autenticación y autorización de la API.

Aquí vive el guard que protege los endpoints. La identidad del usuario sale
SIEMPRE del token, nunca del cuerpo ni de la query de la petición: aceptar un
`user_id` enviado por el cliente permitiría a cualquiera actuar en nombre de
otro (IDOR).

Los fallos se comunican con **excepciones de dominio**, no con `HTTPException`. El manejador
central de `main.py` las traduce al sobre `{"error": {code, message, details}}` que `API.md`
documenta como formato estándar. Lanzarlas aquí como `HTTPException` produciría
`{"detail": ...}` y la API tendría dos formas de error distintas según de dónde viniera el
fallo, obligando al cliente a llevar dos analizadores y dejando la autenticación sin un
`error.code` estable.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.dtos.auth_dto import TokenPayload, TokenType
from app.domain.entities.professor import Professor
from app.domain.entities.student import Student
from app.domain.exceptions.authentication import (
    AdminRequiredError,
    MissingTokenError,
    ProfessorProfileNotFoundError,
    ProfessorRequiredError,
    StudentProfileNotFoundError,
)
from app.domain.value_objects.user_role import UserRole
from app.interfaces.api.dependencies.di import (
    AuthServiceDep,
    ProfessorReaderDep,
    StudentRepositoryDep,
)

# `auto_error=False` para decidir nosotros la respuesta ante un header ausente: el 403 que
# devuelve HTTPBearer por defecto no distingue "no te has autenticado" de "no tienes permiso",
# que son cosas distintas para el cliente. Con esto, lo primero es 401 MISSING_TOKEN y lo
# segundo 403 ADMIN_REQUIRED.
_esquema_bearer = HTTPBearer(auto_error=False, description="Token JWT de acceso")


def get_current_user(
    auth_service: AuthServiceDep,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_esquema_bearer)] = None,
) -> TokenPayload:
    """Valida el token de acceso y devuelve la identidad del solicitante.

    Args:
        auth_service: servicio que verifica la firma y la vigencia del token.
        credenciales: cabecera `Authorization: Bearer <token>`, si viene.

    Returns:
        El contenido verificado del token.

    Raises:
        MissingTokenError: si la petición no trae la cabecera.
        InvalidTokenError: si el token es ilegible, tiene firma inválida o ha expirado.
    """
    if credenciales is None:
        raise MissingTokenError()

    # `decode_token` ya lanza `InvalidTokenError`, que el manejador central traduce a 401.
    # No se envuelve en `HTTPException`: eso produciría `{"detail": ...}` en vez del sobre
    # `{"error": {...}}` que `API.md` documenta como formato estándar, y obligaría al cliente
    # a distinguir dos formas de error según de dónde viniera el fallo.
    return auth_service.decode_token(credenciales.credentials, TokenType.ACCESS)


CurrentUserDep = Annotated[TokenPayload, Depends(get_current_user)]


def require_admin(current_user: CurrentUserDep) -> TokenPayload:
    """Exige que el solicitante tenga rol de administrador.

    Se aplica a todos los endpoints bajo `/admin`. La comprobación se hace en el
    backend aunque el frontend ya oculte la opción: nunca se confía en el cliente.

    Args:
        current_user: identidad ya validada por `get_current_user`.

    Returns:
        La misma identidad, si tiene permiso.

    Raises:
        AdminRequiredError: si el rol no es ADMIN. Es 403 y no 401 porque el usuario sí está
            autenticado; lo que falta es el permiso.
    """
    if current_user.role is not UserRole.ADMIN:
        raise AdminRequiredError()

    return current_user


AdminUserDep = Annotated[TokenPayload, Depends(require_admin)]


def get_current_student(
    current_user: CurrentUserDep,
    student_repository: StudentRepositoryDep,
) -> Student:
    """Resuelve la cuenta autenticada a su perfil académico.

    El token identifica una CUENTA (`user_id`), pero la inscripción y el horario se hacen sobre
    un ESTUDIANTE (`student_id`), y no son lo mismo: un administrador tiene cuenta y no tiene
    perfil académico. Esta dependencia hace esa traducción una sola vez y en un solo sitio, en
    vez de repetirla en cada router.

    Es además el punto que garantiza que nadie opere en nombre de otro: el identificador sale
    del token y no hay ningún parámetro con el que pedir otro distinto.

    Args:
        current_user: identidad ya validada por `get_current_user`.
        student_repository: acceso a los perfiles académicos.

    Returns:
        El perfil académico de quien hace la petición.

    Raises:
        StudentProfileNotFoundError: si la cuenta no tiene perfil de estudiante. Se traduce a
            404, no a 403: la cuenta es válida, lo que no existe es el perfil.
    """
    estudiante = student_repository.find_by_user_id(current_user.user_id)

    if estudiante is None:
        raise StudentProfileNotFoundError()

    return estudiante


CurrentStudentDep = Annotated[Student, Depends(get_current_student)]


def require_professor(current_user: CurrentUserDep) -> TokenPayload:
    """Exige que el solicitante tenga rol de docente.

    Se separa de `require_admin` en vez de generalizar a «uno de estos roles» porque los dos
    permisos responden preguntas distintas y se conceden por motivos distintos. Un
    administrador NO puede calificar por el hecho de ser administrador: quien conoce la nota es
    quien dictó la clase, y dejar que la ponga cualquiera con permiso amplio borra esa
    responsabilidad.

    Raises:
        ProfessorRequiredError: si el rol no es PROFESSOR. Es 403 y no 401 porque el usuario sí
            está autenticado; lo que falta es el permiso.
    """
    if current_user.role is not UserRole.PROFESSOR:
        raise ProfessorRequiredError()

    return current_user


ProfessorUserDep = Annotated[TokenPayload, Depends(require_professor)]


def get_current_professor(
    current_user: Annotated[TokenPayload, Depends(require_professor)],
    professor_repository: ProfessorReaderDep,
) -> Professor:
    """Resuelve la cuenta autenticada a su perfil docente.

    Igual que `get_current_student`, es la traducción de CUENTA a PERFIL, hecha una sola vez y
    en un solo sitio en vez de repetirla en cada router. Y es el punto que garantiza que nadie
    califique en nombre de otro: el identificador sale del token y no hay ningún parámetro con
    el que pedir otro distinto.

    Depende de `require_professor` y no de `get_current_user`: sin el rol comprobado antes, un
    administrador cuya cuenta estuviera enlazada por error a una fila de `professors` entraría
    igual.

    Raises:
        ProfessorProfileNotFoundError: si la cuenta tiene el rol pero ningún perfil asociado. Se
            traduce a 404 y no a 403: el permiso está, lo que falta es el alta.
    """
    docente = professor_repository.find_by_user_id(current_user.user_id)

    if docente is None:
        raise ProfessorProfileNotFoundError()

    return docente


CurrentProfessorDep = Annotated[Professor, Depends(get_current_professor)]
