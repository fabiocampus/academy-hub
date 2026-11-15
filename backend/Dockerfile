# syntax=docker/dockerfile:1
# Immagine del backend: build con uv, runtime minimo con utente non root.
# Python 3.11 come il runtime di Databricks Apps (ADR-0001).
# Il frontend arriva dal contesto con nome "frontend" (compose: additional_contexts;
# a mano: docker build --build-context frontend=../frontend backend) e la sua build
# statica è servita da FastAPI nello stesso processo (ADR-0009 §14).

FROM ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 AS uv

FROM --platform=$BUILDPLATFORM node:26.13.1-trixie-slim@sha256:e6bedef217677b276c591795e169840edd9096dbf13f29df8ef8d1856b8820bc AS build-frontend
WORKDIR /frontend
COPY --from=frontend package.json package-lock.json .npmrc ./
RUN --mount=type=cache,target=/root/.npm npm ci --ignore-scripts
COPY --from=frontend . .
RUN npm run build

FROM python:3.11.18-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Prima le sole dipendenze, così lo strato resta in cache se cambia solo il codice.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.11.18-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535 AS runtime
# Patch di sicurezza Debian non ancora nell'immagine base; pip e setuptools
# non servono a runtime (l'ambiente è già in .venv) e portano CVE vendorizzate.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip setuptools \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=build --chown=app:app /app/.venv /app/.venv
COPY --from=build-frontend --chown=app:app /frontend/dist /app/static
ENV PATH="/app/.venv/bin:$PATH" \
    ACADEMY_FRONTEND_DIR=/app/static \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000
USER app
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uvicorn", "academy_hub.main:app", "--no-access-log"]
