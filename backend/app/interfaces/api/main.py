"""Entrypoint de la API REST.

El contenedor arranca la aplicación con `uvicorn app.interfaces.api.main:app`.

Este módulo es el borde más externo de la arquitectura: es el único lugar, junto con las
dependencias de FastAPI, donde se resuelve la configuración concreta y se ensamblan las piezas.
Por eso puede importar de `app.infrastructure`; el dominio y la aplicación no.
"""

from fastapi import FastAPI

from app.infrastructure.config.settings import get_settings
from app.interfaces.api.routers import health

settings = get_settings()

app = FastAPI(
    title="Sistema de Matrícula Académica",
    description="API de inscripción y gestión académica.",
    version=settings.app_version,
)

# `/health` va en la raíz, fuera de `settings.api_v1_prefix`: lo consumen Docker y el ALB, no
# los clientes de la API. Los routers de negocio de las fases siguientes sí se registran con
# `prefix=settings.api_v1_prefix`.
app.include_router(health.router)
