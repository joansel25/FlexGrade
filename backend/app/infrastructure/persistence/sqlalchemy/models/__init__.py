"""Modelos ORM: el mapeo de las tablas descritas en el DDL de `docs/DATA_MODEL.md`.

Contendrá un módulo por grupo de tablas: usuarios y perfiles (`users`, `students`,
`administrators`, `programs`), catálogo (`courses`, `course_prerequisites`, `program_courses`,
`professors`), oferta del semestre (`enrollment_periods`, `course_offerings`,
`schedule_blocks`), inscripciones (`enrollments`) e historial académico (`academic_history`).

Aquí se declaran columnas, restricciones e índices, incluidos los que sostienen el requisito no
funcional central: `course_offerings.version` (bloqueo optimista) y el
`CHECK (enrolled_count <= total_capacity)`.

Estos modelos son solo persistencia: no contienen lógica de negocio y no son las entidades del
dominio. Los repositorios traducen entre modelo ORM y entidad.
"""
