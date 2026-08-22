"""Pruebas unitarias: dominio y casos de uso, aisladas de la infraestructura.

Contendrá las pruebas de las entidades y value objects (invariantes de cupo, solapamiento de
bloques de horario, transiciones de estado de una inscripción), de los servicios de dominio
(validación de prerrequisitos, detección de choque de horario) y de los casos de uso con dobles
de test en lugar de repositorios reales.

No tocan base de datos, red ni reloj del sistema. Se marcan con `@pytest.mark.unit`.
"""
