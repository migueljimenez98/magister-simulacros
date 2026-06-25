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
# Docs (guión, plantillas) for the coach KB grounding — baked into the image
# so kb_bootstrap can ingest them at startup (no volume needed on Render).
COPY docs ./docs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
