#!/bin/sh
# Arranque del backend en producción (Render): migra, siembra datos base y
# levanta uvicorn en el puerto que inyecta la plataforma ($PORT, 8000 en local).
set -e

alembic upgrade head
python -m scripts.seed_simulacros || true

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
