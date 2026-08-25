"""Pruebas del plan de estudios y de su semáforo (iteraciones 6.1 y 6.3).

El plan responde «qué materias son las mías», que el catálogo no puede contestar, y desde la
6.3 responde además en qué punto está el estudiante con cada una.

Se comprueban dos cosas, en dos bloques: que el plan sale SOLO por la carrera del estudiante y
con los datos que no viven en la materia —semestre sugerido y obligatoriedad—, y que el estado
de cada materia coincide con lo que la inscripción decidiría. Lo segundo es la promesa de la
iteración: el semáforo pinta lo que el servidor va a aceptar, y en cuanto discrepen la pantalla
ofrecerá algo que va a fallar.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.use_cases.catalog.get_study_plan import GetStudyPlanUseCase
from app.domain.exceptions.authentication import StudentProfileNotFoundError
from app.domain.exceptions.catalog import ProgramNotFoundError
from tests.unit.doubles import (
    InMemoryAcademicHistory,
    InMemoryCourseRepository,
    InMemoryEnrollmentRepository,
    InMemoryOfferingRepository,
    InMemoryPeriodRepository,
    InMemoryProgramRepository,
    InMemoryStudentRepository,
)
from tests.unit.factories import (
    crear_estudiante,
    crear_inscripcion,
    crear_materia,
    crear_oferta,
    crear_periodo,
    crear_programa,
)


def _montar():
    """Dos carreras con planes distintos, y un estudiante en la primera.

    Física aparece en las DOS: es lo que permite comprobar que una materia compartida entre
    programas puede tener semestre distinto en cada uno, que es justo la razón de que el
    semestre viva en la relación y no en la materia.
    """
    sistemas = crear_programa(code="ISIS", name="Ingeniería de Sistemas", total_semesters=10)
    derecho = crear_programa(code="DERE", name="Derecho", total_semesters=8)

    calculo = crear_materia(code="MAT101", name="Cálculo I", credits=4)
    programacion = crear_materia(code="PRG101", name="Programación I", credits=3)
    fisica = crear_materia(code="FIS101", name="Física I", credits=3)
    constitucional = crear_materia(code="DER101", name="Derecho Constitucional", credits=4)

    materias = InMemoryCourseRepository(
        [calculo, programacion, fisica, constitucional],
        plan={
            # Desordenado a propósito: el caso de uso debe ordenarlo.
            sistemas.id: [(fisica.id, 2), (programacion.id, 1), (calculo.id, 1)],
            # Física también está en Derecho, pero en otro semestre.
            derecho.id: [(constitucional.id, 1), (fisica.id, 4)],
        },
    )

    estudiante = crear_estudiante(program_id=sistemas.id)

    # Sin período activo: estos tests son los de la 6.1 y van sobre la composición del plan,
    # no sobre el semáforo. Sin ventana abierta no se ofrece nada, que es un estado legítimo.
    caso = GetStudyPlanUseCase(
        InMemoryStudentRepository([estudiante]),
        InMemoryProgramRepository([sistemas, derecho]),
        materias,
        InMemoryPeriodRepository([]),
        InMemoryOfferingRepository([]),
        InMemoryEnrollmentRepository([]),
        InMemoryAcademicHistory({}),
    )

    return caso, estudiante, derecho


@pytest.mark.unit
def test_el_plan_trae_solo_las_materias_de_la_carrera() -> None:
    """Es el arreglo de fondo: antes el catálogo mostraba las de todas las carreras."""
    caso, estudiante, _ = _montar()

    plan = caso.execute(estudiante.id)

    codigos = [e.course.code.value for e in plan.entries]
    assert codigos == ["MAT101", "PRG101", "FIS101"]
    # Derecho Constitucional es de otra carrera y no aparece.
    assert "DER101" not in codigos


@pytest.mark.unit
def test_el_plan_llega_ordenado_por_semestre_y_luego_por_codigo() -> None:
    """Es como se lee un plan de estudios: por semestres, de primero a último."""
    caso, estudiante, _ = _montar()

    plan = caso.execute(estudiante.id)

    semestres = [e.suggested_semester for e in plan.entries]
    assert semestres == sorted(semestres)
    # Dentro del primer semestre, alfabético por código: MAT101 antes que PRG101.
    primero = [e.course.code.value for e in plan.entries if e.suggested_semester == 1]
    assert primero == ["MAT101", "PRG101"]


@pytest.mark.unit
def test_una_materia_compartida_lleva_el_semestre_de_cada_carrera() -> None:
    """Es la razón de que el semestre viva en la relación y no en la materia.

    Física es de segundo en Ingeniería y de cuarto en Derecho. Si el dato estuviera en la
    entidad `Course`, una de las dos carreras tendría que mentir.
    """
    caso, estudiante, _ = _montar()

    plan = caso.execute(estudiante.id)

    fisica = next(e for e in plan.entries if e.course.code.value == "FIS101")
    assert fisica.suggested_semester == 2


@pytest.mark.unit
def test_el_plan_suma_sus_creditos() -> None:
    caso, estudiante, _ = _montar()

    plan = caso.execute(estudiante.id)

    # 4 + 3 + 3.
    assert plan.total_credits == 10


@pytest.mark.unit
def test_el_plan_identifica_el_programa() -> None:
    caso, estudiante, _ = _montar()

    plan = caso.execute(estudiante.id)

    assert plan.program_code == "ISIS"
    assert plan.program_name == "Ingeniería de Sistemas"
    # La duración permite mostrar los semestres que aún no tienen materias cargadas.
    assert plan.total_semesters == 10


@pytest.mark.unit
def test_un_programa_sin_plan_cargado_devuelve_una_lista_vacia() -> None:
    """Es un estado legítimo mientras Registro Académico no lo carga, no un error."""
    programa = crear_programa(code="NUE", name="Programa Nuevo")
    estudiante = crear_estudiante(program_id=programa.id)

    caso = GetStudyPlanUseCase(
        InMemoryStudentRepository([estudiante]),
        InMemoryProgramRepository([programa]),
        InMemoryCourseRepository([]),
        InMemoryPeriodRepository([]),
        InMemoryOfferingRepository([]),
        InMemoryEnrollmentRepository([]),
        InMemoryAcademicHistory({}),
    )

    plan = caso.execute(estudiante.id)

    assert plan.entries == []
    assert plan.total_credits == 0


@pytest.mark.unit
def test_una_cuenta_sin_perfil_academico_no_tiene_plan() -> None:
    caso, _, _ = _montar()

    with pytest.raises(StudentProfileNotFoundError):
        caso.execute(uuid4())


@pytest.mark.unit
def test_falla_si_el_programa_del_estudiante_ya_no_existe() -> None:
    """Solo puede darse si se borra un programa con estudiantes activos.

    Se modela igualmente: dejar que el `None` llegue a la pantalla produciría un plan con el
    nombre del programa en blanco, que es peor que un error explicado.
    """
    estudiante = crear_estudiante(program_id=uuid4())

    caso = GetStudyPlanUseCase(
        InMemoryStudentRepository([estudiante]),
        InMemoryProgramRepository([]),
        InMemoryCourseRepository([]),
        InMemoryPeriodRepository([]),
        InMemoryOfferingRepository([]),
        InMemoryEnrollmentRepository([]),
        InMemoryAcademicHistory({}),
    )

    with pytest.raises(ProgramNotFoundError):
        caso.execute(estudiante.id)


# ---------------------------------------------------------------------------
# El semáforo (iteración 6.3)
# ---------------------------------------------------------------------------


class EscenarioDelSemaforo:
    """Un plan de cinco materias con el que se pueden provocar los cinco estados.

    El plan es el del seed: la cadena `MAT101` → `MAT102` → `MAT201` más el par mutuo
    `FIS101` ↔ `FIS102`, que es el que obliga a tratar el bloque aparte.

    Todo se declara con CÓDIGOS y no con identificadores. Los UUID los genera cada factoría, así
    que no se pueden escribir en el test ni compartir entre escenarios; el código es la clave
    natural y hace que cada caso se lea como la situación que describe.
    """

    def __init__(
        self,
        *,
        aprobadas: tuple[str, ...] = (),
        inscritas: tuple[str, ...] = (),
        sin_oferta: tuple[str, ...] = (),
        con_periodo: bool = True,
    ) -> None:
        self.programa = crear_programa(code="ISIS", total_semesters=10)
        self.estudiante = crear_estudiante(program_id=self.programa.id)
        self.periodo = crear_periodo(is_active=True)

        materias = [
            crear_materia(code="MAT101", credits=4),
            crear_materia(code="MAT102", credits=4),
            crear_materia(code="MAT201", credits=4),
            crear_materia(code="FIS101", credits=3),
            crear_materia(code="FIS102", credits=1),
        ]
        self.por_codigo = {m.code.value: m for m in materias}

        catalogo = InMemoryCourseRepository(
            materias,
            prerequisites={
                self.por_codigo["MAT102"].id: [self.por_codigo["MAT101"]],
                self.por_codigo["MAT201"].id: [self.por_codigo["MAT102"]],
            },
            corequisites={
                # Como en el seed, y con los dos casos que se validan distinto: `FIS102` es
                # MUTUO —se exigen en las dos direcciones, que es lo que forma bloque— y
                # `MAT101` va en un solo sentido, sin vuelta.
                self.por_codigo["FIS101"].id: [
                    self.por_codigo["FIS102"],
                    self.por_codigo["MAT101"],
                ],
                self.por_codigo["FIS102"].id: [self.por_codigo["FIS101"]],
            },
            plan={self.programa.id: [(m.id, 1) for m in materias]},
        )

        grupos = [
            crear_oferta(
                course_id=m.id,
                enrollment_period_id=self.periodo.id,
                group_number=f"{indice:02d}",
            )
            for indice, m in enumerate(materias, start=1)
            if m.code.value not in set(sin_oferta)
        ]
        por_materia = {g.course_id: g for g in grupos}

        activas = [
            crear_inscripcion(
                student_id=self.estudiante.id,
                course_offering_id=por_materia[self.por_codigo[codigo].id].id,
                enrollment_period_id=self.periodo.id,
            )
            for codigo in inscritas
        ]

        self.caso = GetStudyPlanUseCase(
            InMemoryStudentRepository([self.estudiante]),
            InMemoryProgramRepository([self.programa]),
            catalogo,
            InMemoryPeriodRepository([self.periodo] if con_periodo else []),
            InMemoryOfferingRepository(grupos),
            InMemoryEnrollmentRepository(activas),
            InMemoryAcademicHistory(
                {self.estudiante.id: {self.por_codigo[c].id for c in aprobadas}}
            ),
        )

    @property
    def plan(self):
        return self.caso.execute(self.estudiante.id)

    def estados(self) -> dict[str, str]:
        """El estado de cada materia, indexado por código."""
        return {e.course.code.value: e.status.value for e in self.plan.entries}

    def entrada(self, codigo: str):
        return next(e for e in self.plan.entries if e.course.code.value == codigo)


@pytest.mark.unit
def test_el_semaforo_distingue_los_cinco_estados_a_la_vez() -> None:
    """Un solo plan con las cinco situaciones, que es como se ve en la pantalla real."""
    escenario = EscenarioDelSemaforo(
        aprobadas=("MAT101",), inscritas=("MAT102",), sin_oferta=("MAT201",)
    )

    assert escenario.estados() == {
        "MAT101": "APPROVED",
        "MAT102": "ENROLLED",
        # MAT201 exige APROBAR MAT102, que solo está inscrita: sigue bloqueada. Cursar no es
        # aprobar, y confundirlos dejaría inscribir la cadena entera en un mismo semestre.
        "MAT201": "BLOCKED",
        "FIS101": "AVAILABLE",
        "FIS102": "AVAILABLE",
    }


@pytest.mark.unit
def test_una_materia_bloqueada_dice_que_le_falta() -> None:
    # «Bloqueada» sin más deja a la persona igual de atascada que antes.
    escenario = EscenarioDelSemaforo()

    assert escenario.entrada("MAT102").missing_prerequisites == ["MAT101"]


@pytest.mark.unit
def test_aprobar_el_prerrequisito_desbloquea_la_materia() -> None:
    assert EscenarioDelSemaforo().estados()["MAT102"] == "BLOCKED"
    assert EscenarioDelSemaforo(aprobadas=("MAT101",)).estados()["MAT102"] == "AVAILABLE"


@pytest.mark.unit
def test_una_materia_aprobada_manda_sobre_cualquier_otra_condicion() -> None:
    # Aunque no se ofrezca este período, aprobada es aprobada: no hay nada que hacer con ella.
    escenario = EscenarioDelSemaforo(aprobadas=("MAT101",), sin_oferta=("MAT101",))

    assert escenario.estados()["MAT101"] == "APPROVED"


@pytest.mark.unit
def test_una_materia_sin_grupos_no_se_ofrece_aunque_cumpla_requisitos() -> None:
    """Ofrecer inscribirla llevaría a una pantalla de grupos vacía."""
    escenario = EscenarioDelSemaforo(sin_oferta=("MAT101",))

    assert escenario.estados()["MAT101"] == "NOT_OFFERED"


@pytest.mark.unit
def test_el_bloque_mutuo_esta_disponible_aunque_ninguna_este_inscrita() -> None:
    """Es la exención que hace inscribible el bloque, y el semáforo tiene que reflejarla.

    Si el semáforo exigiera que la otra estuviera ya inscrita, pintaría bloqueadas dos materias
    que la inscripción sí acepta: exactamente la discrepancia que esta iteración evita.
    """
    estados = EscenarioDelSemaforo().estados()

    assert estados["FIS101"] == "AVAILABLE"
    assert estados["FIS102"] == "AVAILABLE"


@pytest.mark.unit
def test_un_correquisito_sin_oferta_bloquea_la_materia_que_lo_exige() -> None:
    """Cumplir los prerrequisitos no basta si lo que hay que cursar a la vez no tiene grupos.

    Sin esta comprobación el semáforo diría «disponible» y la inscripción respondería
    `COREQUISITES_NOT_MET`, que es justo la discrepancia que la iteración existe para evitar.
    """
    # Con `MAT101`, que `FIS101` exige en un solo sentido. Se prueba con esa y no con `FIS102`
    # porque el par mutuo está EXENTO por diseño: sin la exención el bloque sería inscribible
    # en teoría e imposible en la práctica.
    escenario = EscenarioDelSemaforo(sin_oferta=("MAT101",))

    assert escenario.estados()["FIS101"] == "BLOCKED"
    assert escenario.entrada("FIS101").missing_corequisites == ["MAT101"]


@pytest.mark.unit
def test_los_correquisitos_se_anuncian_aunque_la_materia_este_disponible() -> None:
    # Es una instrucción, no un impedimento: esconderla hasta que falle repetiría el error que
    # arregló la 6.1.
    entrada = EscenarioDelSemaforo().entrada("FIS101")

    assert entrada.status.value == "AVAILABLE"
    assert entrada.corequisites == ["FIS102", "MAT101"]


@pytest.mark.unit
def test_sin_periodo_activo_el_plan_sigue_respondiendo() -> None:
    """«Qué me falta para graduarme» tiene sentido todo el año.

    Hacer fallar el endpoint fuera de la ventana dejaría la pantalla inservible durante la
    mayor parte del semestre.
    """
    estados = EscenarioDelSemaforo(con_periodo=False).estados()

    assert estados["MAT101"] == "NOT_OFFERED"
    assert estados["MAT102"] == "BLOCKED"


@pytest.mark.unit
def test_el_plan_suma_los_creditos_aprobados_aparte_de_los_totales() -> None:
    # Es la cifra que responde «cuánto llevo», y se calcula en el servidor para que la pantalla
    # no tenga que decidir qué estado cuenta como avance.
    plan = EscenarioDelSemaforo(aprobadas=("MAT101", "FIS102")).plan

    assert plan.total_credits == 16
    assert plan.approved_credits == 5
