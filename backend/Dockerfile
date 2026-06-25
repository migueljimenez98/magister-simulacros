FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl tzdata \
    && rm -rf /var/lib/apt/lists/*

# Default TZ — overridden by `TZ` env var at runtime (docker-compose sets
# Europe/Madrid for the api service). Without tzdata installed the
# container falls back to UTC silently and APScheduler cron triggers fire
# at the wrong wall-clock time.
ENV TZ=Europe/Madrid

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY start.sh ./
# Docs (guión, plantillas) for the coach KB grounding — baked into the image
# so kb_bootstrap can ingest them at startup (no volume needed on Render).
COPY docs ./docs

EXPOSE 8000

# start.sh: migra + siembra + uvicorn ($PORT). Invocado con `sh` para no
# depender del bit de ejecución (Windows no lo conserva).
CMD ["sh", "start.sh"]
