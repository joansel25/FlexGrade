"""Crea estudiantes adicionales para las pruebas de QA manual.

**Esto es un apaño de pruebas, no una pieza del producto**, y existe por un hueco real: no hay
endpoint ni pantalla para dar de alta a un estudiante. El seed crea cincuenta y punto; para
simular una ventana de matrícula disputada hacen falta más, y todos en el MISMO programa, para
que compitan por los mismos grupos.

Se ejecuta con:

    docker-compose exec backend python crear_estudiantes_qa.py 40 ISIS

Es idempotente: si el código de estudiante ya existe, esa cuenta se salta.
"""

from __future__ import annotations

import sys
from datetime import date

from sqlalchemy import select

from app.infrastructure.auth.jwt_auth_service import JWTAuthService
from app.infrastructure.config.settings import get_settings
from app.infrastructure.persistence.sqlalchemy.models.program import ProgramModel
from app.infrastructure.persistence.sqlalchemy.models.student import StudentModel
from app.infrastructure.persistence.sqlalchemy.models.user import UserModel
from app.infrastructure.persistence.sqlalchemy.session import get_session_factory

PASSWORD = "SecurePass123"
PREFIJO = "qa"


def main(cuantos: int, codigo_programa: str) -> None:
    hasher = JWTAuthService(get_settings())
    # Un solo hash reutilizado: bcrypt es lento a propósito y calcularlo cuarenta veces
    # tardaría más que todo lo demás junto. En pruebas da igual que compartan hash.
    password_hash = hasher.hash(PASSWORD)

    with get_session_factory()() as session:
        programa = session.scalar(select(ProgramModel).where(ProgramModel.code == codigo_programa))

        if programa is None:
            raise SystemExit(f"No existe el programa {codigo_programa}")

        creados = 0

        for indice in range(1, cuantos + 1):
            # SOLO DIGITOS: el value object `StudentCode` exige entre 6 y 20 digitos, y un codigo con
            # letras se acepta en la base pero revienta al LEERLO, con un 400 generico que no
            # dice que el problema esta en el dato y no en la peticion.
            codigo = f"9026{indice:04d}"

            if session.scalar(select(StudentModel).where(StudentModel.student_code == codigo)):
                continue

            correo = f"{PREFIJO}{indice:03d}@tdea.edu.co"
            usuario = UserModel(
                email=correo,
                password_hash=password_hash,
                role="STUDENT",
                is_active=True,
            )
            session.add(usuario)
            session.flush()

            session.add(
                StudentModel(
                    user_id=usuario.id,
                    student_code=codigo,
                    program_id=programa.id,
                    current_semester=1,
                    full_name=f"Estudiante QA {indice:03d}",
                    enrollment_date=date(2026, 1, 15),
                )
            )
            creados += 1

        session.commit()

    print(f"Creados {creados} estudiantes en {codigo_programa}.")
    print(f"Credenciales: {PREFIJO}001@tdea.edu.co ... {PREFIJO}{cuantos:03d}@tdea.edu.co")
    print(f"Contraseña:   {PASSWORD}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40, sys.argv[2] if len(sys.argv) > 2 else "ISIS")
