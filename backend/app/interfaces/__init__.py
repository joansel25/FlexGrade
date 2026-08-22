"""Capa de interfaces: los adaptadores de entrada del sistema.

Contendrá hoy el subpaquete `api` con la API REST de FastAPI. Es el nivel donde vivirían otros
puntos de entrada si el sistema los necesitara (una CLI de administración, un worker que
consume una cola), sin que ninguno de ellos duplique lógica: todos invocan casos de uso.

Esta capa traduce entre el protocolo (HTTP) y la aplicación. No contiene lógica de negocio ni
accede directamente a la base de datos.
"""
