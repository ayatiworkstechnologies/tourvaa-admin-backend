# syntax=docker/dockerfile:1.7

FROM python:3.14-slim AS builder
WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --prefix=/install -r requirements.txt

FROM python:3.14-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    WEB_CONCURRENCY=1 \
    RUN_MIGRATIONS=true \
    STORAGE_ROOT=/data/storage

# libgomp is required by the ONNX runtime used for chatbot embeddings.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 tourvaa \
    && useradd --system --uid 1001 --gid tourvaa --create-home tourvaa \
    && mkdir -p /data/storage /data/private-docs \
    && chown -R tourvaa:tourvaa /data

COPY --from=builder /install /usr/local
COPY --chown=tourvaa:tourvaa app ./app
COPY --chown=tourvaa:tourvaa alembic ./alembic
COPY --chown=tourvaa:tourvaa alembic.ini ./
COPY --chown=tourvaa:tourvaa docker-entrypoint.sh /usr/local/bin/tourvaa-entrypoint
RUN chmod 0755 /usr/local/bin/tourvaa-entrypoint

USER tourvaa
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

ENTRYPOINT ["tourvaa-entrypoint"]

