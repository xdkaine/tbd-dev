# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install system dependencies:
#   - skopeo: OCI image copy for LXC conversion
#   - umoci: OCI image unpacking for LXC rootfs
#   - git: clone repos for built-in builder
#   - docker CLI: build & push images via host Docker socket
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        skopeo ca-certificates wget git \
        apt-transport-https curl gnupg lsb-release && \
    wget -qO /usr/local/bin/umoci https://github.com/opencontainers/umoci/releases/download/v0.4.7/umoci.amd64 && \
    chmod +x /usr/local/bin/umoci && \
    # Install Docker CLI (no daemon — we use host socket)
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli && \
    # Cleanup
    apt-get purge -y wget gnupg lsb-release apt-transport-https && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps with BuildKit cache mount (survives across builds)
COPY pyproject.toml .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install .

COPY . .

# Build work directory for cloning repos
RUN mkdir -p /var/lib/tbd/builds

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
