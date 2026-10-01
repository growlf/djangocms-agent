# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Non-root runtime user (fixed uid so volume ownership is predictable).
RUN groupadd --system --gid 1000 app && useradd --system --uid 1000 --gid app --home-dir /app --no-create-home app

WORKDIR /app

# Dependencies first so this layer is cached until requirements.txt changes.
# psycopg[binary] bundles libpq, so no apt packages or compiler are needed.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x docker/entrypoint.sh \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app/staticfiles /app/media

# Collect static at build time with a throwaway key (build-only env, not persisted in the image).
# The entrypoint collects again at start so the named volume always matches the code.
RUN DJANGO_SECRET_KEY=build-only-not-a-secret python manage.py collectstatic --noinput \
    && chown -R app:app /app/staticfiles

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=4)" || exit 1

ENTRYPOINT ["docker/entrypoint.sh"]
