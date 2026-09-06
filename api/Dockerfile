# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm AS base

WORKDIR /app
ARG APP_REVISION=development
ENV APP_REVISION=$APP_REVISION
LABEL org.opencontainers.image.revision=$APP_REVISION

COPY --from=moby/buildkit:v0.32.2 /usr/bin/buildctl /usr/local/bin/buildctl
RUN apt-get update && apt-get install -y --no-install-recommends \
    skopeo umoci ca-certificates git curl && rm -rf /var/lib/apt/lists/*

# Install Python deps with BuildKit cache mount (survives across builds)
COPY pyproject.toml .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install .

# Full source remains available for builder-stage validation.
FROM base AS builder
COPY . .

# Runtime deliberately includes only application and migration entry points.
FROM base AS runner
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
RUN test ! -d /app/tests \
 && test -f /app/app/release-probe.txt \
 && test -f /app/alembic/env.py

# Build work directory for cloning repos
RUN mkdir -p /var/lib/tbd/builds

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
