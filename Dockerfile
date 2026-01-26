# Django conversations

# ---- base image to inherit from ----
FROM python:3.13.3-alpine AS base

# Upgrade system packages to install security updates
RUN apk update && \
  apk upgrade

# ---- Back-end builder image ----
FROM base AS back-builder


ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

# Install Rust and Cargo using Alpine's package manager
RUN apk add --no-cache \
  build-base \
  libffi-dev \
  libxml2-dev \
  libxslt-dev \
  rust \
  cargo

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=src/backend/uv.lock,target=uv.lock \
    --mount=type=bind,source=src/backend/pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY src/backend /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---- mails ----
FROM node:24 AS mail-builder

COPY ./src/mail /mail/app

WORKDIR /mail/app

RUN yarn install --frozen-lockfile && \
    yarn build


# ---- static link collector ----
FROM base AS link-collector
ARG CONVERSATIONS_STATIC_ROOT=/data/static

# Install pango & rdfind
RUN apk add \
  pango \
  rdfind

WORKDIR /app

# Copy the application from the builder
COPY --from=back-builder /app /app

ENV PATH="/app/.venv/bin:$PATH"

# Copy conversations application (see .dockerignore)
COPY ./src/backend /app/

# collectstatic
RUN DJANGO_CONFIGURATION=Build \
    python manage.py collectstatic --noinput

# Replace duplicated file by a symlink to decrease the overall size of the
# final image
RUN rdfind -makesymlinks true -followsymlinks true -makeresultsfile false ${CONVERSATIONS_STATIC_ROOT}

# ---- Core application image ----
FROM base AS core

ENV PYTHONUNBUFFERED=1

# Install required system libs
RUN apk add \
  cairo \
  file \
  font-noto \
  font-noto-emoji \
  gettext \
  gdk-pixbuf \
  libffi-dev \
  libxml2 \
  libxslt \
  pango \
  shared-mime-info

RUN wget https://svn.apache.org/repos/asf/httpd/httpd/trunk/docs/conf/mime.types -O /etc/mime.types

# Copy entrypoint
COPY ./docker/files/usr/local/bin/entrypoint /usr/local/bin/entrypoint

# Give the "root" group the same permissions as the "root" user on /etc/passwd
# to allow a user belonging to the root group to add new users; typically the
# docker user (see entrypoint).
RUN chmod g=u /etc/passwd


# Copy the application from the builder
COPY --from=back-builder /app /app

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

# Generate compiled translation messages
RUN DJANGO_CONFIGURATION=Build \
    python manage.py compilemessages --ignore=".venv/**/*"


# We wrap commands run in this container by the following entrypoint that
# creates a user on-the-fly with the container user ID (see USER) and root group
# ID.
ENTRYPOINT [ "/usr/local/bin/entrypoint" ]

# ---- Development image ----
FROM core AS backend-development

# Switch back to the root user to install development dependencies
USER root:root

# Install psql
RUN apk add postgresql-client

 # Install development dependencies
RUN --mount=from=ghcr.io/astral-sh/uv:0.9.26,source=/uv,target=/bin/uv \
    uv sync --all-extras --locked

# Restore the un-privileged user running the application
ARG DOCKER_USER
USER ${DOCKER_USER}

# Target database host (e.g. database engine following docker compose services
# name) & port
ENV DB_HOST=postgresql \
    DB_PORT=5432

# Run django development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---- Production image ----
FROM core AS backend-production

# Remove apk cache, we don't need it anymore
RUN rm -rf /var/cache/apk/*

ARG CONVERSATIONS_STATIC_ROOT=/data/static

# Gunicorn - not used by default but configuration file is provided
RUN mkdir -p /usr/local/etc/gunicorn
COPY docker/files/usr/local/etc/gunicorn/conversations.py /usr/local/etc/gunicorn/conversations.py

# Un-privileged user running the application
ARG DOCKER_USER
USER ${DOCKER_USER}

# Copy statics
COPY --from=link-collector ${CONVERSATIONS_STATIC_ROOT} ${CONVERSATIONS_STATIC_ROOT}

# Copy conversations mails
COPY --from=mail-builder /mail/backend/core/templates/mail /app/core/templates/mail

# The default command runs uvicorn ASGI server in conversations's main module
# WEB_CONCURRENCY: number of workers to run <=> --workers=4
ENV WEB_CONCURRENCY=4
CMD [\
    "uvicorn",\
    "--app-dir=/app",\
    "--host=0.0.0.0",\
    "--timeout-graceful-shutdown=300",\
    "--limit-max-requests=20000",\
    "--lifespan=off",\
    "conversations.asgi:application"\
]

# To run using gunicorn WSGI server use this instead:
#CMD ["gunicorn", "-c", "/usr/local/etc/gunicorn/conversations.py", "conversations.wsgi:application"]
