"""Configuración del backend leída de variables de entorno.

Este módulo es el único punto del código que lee del entorno. Los atributos usan `snake_case`
(convención de `BEST_PRACTICES.md` secciones 1 y 10) y Pydantic Settings los resuelve contra las
variables de entorno en mayúsculas sin distinguir caso: `database_url` se alimenta de
`DATABASE_URL`, y así con el resto.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Parámetros de ejecución de la aplicación.

    Las variables sin valor por defecto son obligatorias: si faltan, la aplicación falla al
    arrancar con un error explícito en vez de comportarse de forma impredecible en caliente.

    Attributes:
        database_url: DSN de PostgreSQL, en formato SQLAlchemy 2.x
            (ej. `postgresql+psycopg://usuario:clave@host:5432/base`). Obligatorio.
        redis_url: URL del servidor Redis usado como caché del catálogo. Obligatorio.
        jwt_secret: secreto de firma de los tokens. Obligatorio; nunca se versiona.
        jwt_expiration_seconds: vigencia del token de acceso, en segundos.
        jwt_refresh_expiration_seconds: vigencia del token de refresco, en segundos.
        catalog_cache_ttl_seconds: vigencia de las entradas de caché del catálogo. Corto a
            propósito (`API.md`): el catálogo apenas cambia durante el semestre, pero un TTL
            largo retrasaría la visibilidad de un grupo recién abierto. La disponibilidad de
            cupos no se cachea nunca, así que este valor no afecta a su exactitud.
        environment: ambiente de ejecución (`dev`, `staging`, `prod`).
        log_level: nivel mínimo de logging (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
        api_v1_prefix: prefijo común de los endpoints de negocio de la versión 1.
        app_version: versión de la aplicación que se reporta en `/health` y en OpenAPI.
        cors_allowed_origins: orígenes del navegador autorizados a llamar a la API, separados
            por comas. En la nube el frontend se sirve desde CloudFront, un dominio DISTINTO
            del de la API, así que sin esta lista el navegador bloquea todas las llamadas.
            Vacío por defecto: no se autoriza a nadie mientras no se diga explícitamente quién.
        db_pool_size: conexiones que cada proceso mantiene abiertas contra PostgreSQL.
        db_max_overflow: conexiones adicionales que puede abrir en un pico.
            Los dos valores son configurables porque el límite real no lo pone la aplicación
            sino RDS: `max_connections` de la instancia se reparte entre TODAS las instancias
            que levante el autoescalado. Con 10+20 por proceso, una `db.t3.micro` (~87
            conexiones) se agota con cuatro instancias, y el síntoma es la matrícula caída en
            el peor momento. Bajarlo por variable de entorno no exige volver a desplegar
            la imagen.
        docs_enabled: si se publican `/docs`, `/redoc` y `/openapi.json`. Se puede apagar en
            producción sin tocar el código.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_expiration_seconds: int = 3600
    jwt_refresh_expiration_seconds: int = 604800
    catalog_cache_ttl_seconds: int = 30
    environment: str = "dev"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    app_version: str = "0.1.0"
    # `NoDecode` desactiva el intento de Pydantic de leer la variable como JSON. Sin él,
    # `CORS_ALLOWED_ORIGINS=https://mi-frontend` revienta al arrancar con «error parsing
    # value», porque espera `["https://mi-frontend"]`. El validador de abajo la interpreta
    # como lo que la gente escribe de verdad en una consola de AWS: texto con comas.
    cors_allowed_origins: Annotated[list[str], NoDecode] = []
    db_pool_size: int = 10
    db_max_overflow: int = 20
    docs_enabled: bool = True

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _separar_origenes(cls, valor: object) -> object:
        """Acepta la lista como texto separado por comas.

        Elastic Beanstalk, `docker-compose` y `.env` solo saben de cadenas: una variable de
        entorno no puede ser una lista. Sin esta conversión habría que escribir JSON dentro de
        la variable —`["https://..."]`—, que es fácil de escribir mal y produce un error de
        arranque poco claro.
        """
        if isinstance(valor, str):
            return [origen.strip() for origen in valor.split(",") if origen.strip()]

        return valor


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración de la aplicación, resuelta una sola vez.

    El resultado se cachea porque la configuración es inmutable durante la vida del proceso:
    así se evita releer el entorno en cada request y se obtiene una única instancia compartida,
    apta para inyectarse como dependencia de FastAPI.

    Returns:
        Settings: la configuración validada a partir del entorno.
    """
    # Se construye sin argumentos a propósito: Pydantic Settings toma los valores del entorno.
    return Settings()
