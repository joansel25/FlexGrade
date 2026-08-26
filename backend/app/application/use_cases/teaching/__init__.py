"""Casos de uso de la actividad docente (Fase 9).

El docente entra aquí como ACTOR, no como el dato del catálogo que era hasta la Fase 8. Quien
tiene las notas es quien dicta la clase, y el único camino alternativo —que Registro Académico
las teclee todas— concentra el trabajo justo donde no está la información.

Existentes:

- `list_professor_offerings.py`: ListProfessorOfferingsUseCase, la carga docente del período
  activo. Es el cimiento de la 9.2: calificar se hace sobre un grupo, así que primero hay que
  poder decir cuáles son suyos.

En todos, el docente sale del TOKEN y nunca de la ruta. Es la misma regla que separa
`GET /students/me/study-plan` de `GET /admin/programs/{id}/plan`: no hay parámetro con el que
pedir la carga de otra persona porque no existe tal parámetro.
"""
