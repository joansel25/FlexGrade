# syntax=docker/dockerfile:1
#
# Imagen del backend del Sistema de Matricula.
#
# Etapas:
#   builder  -> resuelve e instala las dependencias de runtime en un prefijo aislado.
#   dev      -> imagen de desarrollo (dependencias + herramientas [dev]); la usa docker-compose.
#   runtime  -> imagen final minima que va a DEV/STAGING/PROD. Es la ultima etapa,
#               por lo que `docker build ./backend` produce la imagen de produccion.
#
# Reglas aplicadas (CI_CD.md / @devops-engineer):
#   - Imagen base fijada (nunca `latest`).
#   - Multi-stage: el runtime no lleva compiladores ni dependencias de desarrollo.
#   - Usuario no-root antes del CMD.
#   - Cero secretos en ARG/ENV: toda la configuracion se inyecta en tiempo de ejecucion.
#   - El manifiesto de dependencias se copia antes que el codigo para reutilizar la cache.

# ---------------------------------------------------------------------------
# Etapa 1: dependencias de runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Solo el manifiesto: mientras pyproject.toml no cambie, estas capas se reutilizan
# aunque cambie todo el codigo fuente.
COPY pyproject.toml ./

# Se extraen las dependencias declaradas (una sola fuente de verdad: pyproject.toml)
# y se instalan en /install, que luego se copia tal cual a la imagen final.
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb')); print('\n'.join(d['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install --no-cache-dir --prefix=/install -r /tmp/requirements.txt


# ---------------------------------------------------------------------------
# Etapa 1b: mismas dependencias + herramientas [dev], en un prefijo aparte.
# Se resuelve todo en una sola llamada a pip para que runtime y dev queden con
# versiones transitivas coherentes. Esta etapa NO se construye cuando el destino
# es `runtime`, asi que no encarece la imagen de produccion.
# ---------------------------------------------------------------------------
FROM builder AS builder-dev

RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb')); p = d['project']; print('\n'.join(p['dependencies'] + p['optional-dependencies']['dev']))" > /tmp/requirements-dev.txt \
    && pip install --no-cache-dir --prefix=/install-dev -r /tmp/requirements-dev.txt


# ---------------------------------------------------------------------------
# Etapa 2: imagen de desarrollo (docker-compose la construye con target: dev)
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS dev

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN groupadd --system matricula \
    && useradd --system --gid matricula --create-home matricula

WORKDIR /app

COPY --from=builder-dev /install-dev /usr/local

# El codigo llega por bind mount desde docker-compose (recarga en caliente).
# Se copia igualmente para que la imagen sea utilizable sin el mount.
COPY --chown=matricula:matricula alembic.ini ./alembic.ini
COPY --chown=matricula:matricula alembic ./alembic
COPY --chown=matricula:matricula app ./app

USER matricula

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

CMD ["uvicorn", "app.interfaces.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# ---------------------------------------------------------------------------
# Etapa 3: imagen final de produccion
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN groupadd --system matricula \
    && useradd --system --gid matricula --create-home matricula

WORKDIR /app

# Solo las dependencias de runtime: sin pytest, black, mypy ni toolchain de build.
COPY --from=builder /install /usr/local

COPY --chown=matricula:matricula alembic.ini ./alembic.ini
COPY --chown=matricula:matricula alembic ./alembic
COPY --chown=matricula:matricula app ./app

USER matricula

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

CMD ["uvicorn", "app.interfaces.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
