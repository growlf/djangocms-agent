# syntax=docker/dockerfile:1
# Targets: `production` (the default, last stage; gunicorn, no dev packages) and `dev` (adds
# requirements-dev.txt; used by docker-compose.dev.yml with the source bind-mounted).
# The base image is pinned by digest; bin/pin-images.sh refreshes it (done at every release).
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS base

ARG APP_UID=1000
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Non-root runtime user (uid 1000 by default so volume ownership is predictable; override with APP_UID).
RUN groupadd --system --gid ${APP_UID} app && useradd --system --uid ${APP_UID} --gid app --home-dir /app --no-create-home app

WORKDIR /app

# Dependencies first so this layer is cached until requirements.txt changes.
# psycopg[binary] bundles libpq, so no apt packages or compiler are needed.
COPY requirements.txt .
RUN pip install -r requirements.txt


FROM base AS dev
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
# The media volume is mounted at /app/media over the bind-mounted source: it must exist in the image and
# belong to the app user, or Docker creates the volume root-owned and uploads fail.
RUN mkdir -p /app/media && chown app:app /app/media
USER app
EXPOSE 8000
# The source tree is bind-mounted over /app by docker-compose.dev.yml; the command comes from there.


FROM base AS production
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
