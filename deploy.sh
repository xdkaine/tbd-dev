#!/usr/bin/env bash
#
# TBD Platform — Production Deploy Script
#
# Usage:
#   ./deploy.sh              Full deploy (interactive, generates secrets)
#   ./deploy.sh --no-prompt  Skip interactive prompts (uses .env as-is)
#   ./deploy.sh --rebuild    Force rebuild all images (no cache)
#   ./deploy.sh --down       Tear down the stack
#   ./deploy.sh --status     Show service status and health
#   ./deploy.sh --cleanup    Prune unused Docker images, build cache, and volumes
#   ./deploy.sh --install    Install systemd service for auto-start on reboot
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$SCRIPT_DIR/infra"
ENV_FILE="$INFRA_DIR/.env"
ENV_EXAMPLE="$INFRA_DIR/.env.example"
REGISTRY_AUTH_DIR="$INFRA_DIR/registry/auth"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ---------- Flags ----------
NO_PROMPT=false
REBUILD=false
DOWN=false
STATUS=false
CLEANUP=false
INSTALL_SERVICE=false

for arg in "$@"; do
  case $arg in
    --no-prompt) NO_PROMPT=true ;;
    --rebuild)   REBUILD=true ;;
    --down)      DOWN=true ;;
    --status)    STATUS=true ;;
    --cleanup)   CLEANUP=true ;;
    --install)   INSTALL_SERVICE=true ;;
    --help|-h)
      echo "Usage: ./deploy.sh [--no-prompt] [--rebuild] [--down] [--status] [--cleanup] [--install]"
      exit 0
      ;;
    *) echo "Unknown flag: $arg"; exit 1 ;;
  esac
done

# ---------- Helpers ----------

log()  { echo -e "${GREEN}[TBD]${NC} $*"; }
warn() { echo -e "${YELLOW}[TBD]${NC} $*"; }
err()  { echo -e "${RED}[TBD]${NC} $*" >&2; }
header() { echo -e "\n${CYAN}${BOLD}==> $*${NC}"; }

command_exists() { command -v "$1" &>/dev/null; }

check_prereq() {
  local cmd="$1"
  local name="${2:-$1}"
  if ! command_exists "$cmd"; then
    err "$name is required but not installed."
    return 1
  fi
}

# Generate a random string (alphanumeric, $1 = length, default 48)
random_string() {
  local len="${1:-48}"
  # Use /dev/urandom if available, otherwise openssl, otherwise python
  if [ -f /dev/urandom ]; then
    tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c "$len" || true
  elif command_exists openssl; then
    openssl rand -base64 "$((len * 3 / 4 + 1))" | tr -dc 'A-Za-z0-9' | head -c "$len"
  elif command_exists python3; then
    python3 -c "import secrets; print(secrets.token_urlsafe($len)[:$len])"
  else
    err "Cannot generate random string — install openssl or python3"
    exit 1
  fi
}

# Generate a Fernet key using Python (required for secrets encryption)
generate_fernet_key() {
  if command_exists python3; then
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || \
    docker run --rm python:3.11-slim python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || \
    echo ""
  else
    docker run --rm python:3.11-slim python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || \
    echo ""
  fi
}

# Set a value in the .env file (key=value). If key exists, replace; otherwise append.
env_set() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    # Use a temp file for portability (BSD/GNU sed differ)
    local tmp
    tmp=$(mktemp)
    awk -v k="$key" -v v="$value" '{
      if (index($0, k"=") == 1) print k"="v
      else print
    }' "$ENV_FILE" > "$tmp"
    mv "$tmp" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

# Read a value from .env file
env_get() {
  local key="$1"
  grep "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2-
}

# Prompt for a value (with default). Usage: prompt_value "Display Name" "ENV_KEY" "default_value"
prompt_value() {
  local display="$1"
  local key="$2"
  local default="$3"
  local current
  current="$(env_get "$key")"

  if [ "$NO_PROMPT" = true ]; then
    # In no-prompt mode, keep current value or use default
    if [ -z "$current" ] || [ "$current" = "$default" ]; then
      env_set "$key" "$default"
    fi
    return
  fi

  local prompt_str="  ${display}"
  if [ -n "$current" ] && [ "$current" != "$default" ]; then
    prompt_str+=" [current: ${current}]"
  elif [ -n "$default" ]; then
    prompt_str+=" [${default}]"
  fi
  prompt_str+=": "

  read -rp "$prompt_str" value
  value="${value:-${current:-$default}}"
  env_set "$key" "$value"
}

# ---------- Detect docker compose variant (needed before --down / --status) ----------

if docker compose version &>/dev/null; then
  COMPOSE_CMD="docker compose"
  COMPOSE_BASE="docker compose -f $INFRA_DIR/docker-compose.yml --env-file $ENV_FILE"
elif command_exists docker-compose; then
  COMPOSE_CMD="docker-compose"
  # v1 doesn't support --env-file; it reads .env from --project-directory
  COMPOSE_BASE="docker-compose --project-directory $INFRA_DIR -f $INFRA_DIR/docker-compose.yml"
else
  COMPOSE_CMD=""
  COMPOSE_BASE=""
fi

# ---------- Handle --down ----------

if [ "$DOWN" = true ]; then
  if [ -z "$COMPOSE_BASE" ]; then
    err "docker compose is required but not found."
    exit 1
  fi
  header "Tearing down TBD stack"
  $COMPOSE_BASE down
  log "Stack stopped. Volumes preserved. Use '$COMPOSE_CMD -f infra/docker-compose.yml down -v' to also remove data."
  exit 0
fi

# ---------- Handle --status ----------

if [ "$STATUS" = true ]; then
  if [ -z "$COMPOSE_BASE" ]; then
    err "docker compose is required but not found."
    exit 1
  fi
  header "TBD Platform Status"
  $COMPOSE_BASE ps
  echo ""

  # Health checks
  log "Checking service health..."

  api_health=$(curl -sf http://localhost:8000/health 2>/dev/null || echo "unreachable")
  if echo "$api_health" | grep -q '"ok"'; then
    echo -e "  API:      ${GREEN}healthy${NC}"
  else
    echo -e "  API:      ${RED}$api_health${NC}"
  fi

  web_health=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:3000/ 2>/dev/null || echo "000")
  if [ "$web_health" = "200" ] || [ "$web_health" = "307" ]; then
    echo -e "  Web UI:   ${GREEN}healthy (HTTP $web_health)${NC}"
  else
    echo -e "  Web UI:   ${RED}HTTP $web_health${NC}"
  fi

  registry_health=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/v2/ 2>/dev/null || echo "000")
  if [ "$registry_health" = "200" ] || [ "$registry_health" = "401" ]; then
    echo -e "  Registry: ${GREEN}healthy (HTTP $registry_health)${NC}"
  else
    echo -e "  Registry: ${RED}HTTP $registry_health${NC}"
  fi

  grafana_health=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:3001/api/health 2>/dev/null || echo "000")
  if [ "$grafana_health" = "200" ]; then
    echo -e "  Grafana:  ${GREEN}healthy${NC}"
  else
    echo -e "  Grafana:  ${RED}HTTP $grafana_health${NC}"
  fi

  exit 0
fi

# ---------- Handle --cleanup ----------

if [ "$CLEANUP" = true ]; then
  header "Docker Cleanup"

  # Show current disk usage
  log "Current Docker disk usage:"
  docker system df
  echo ""

  # Prune dangling images (untagged intermediate layers)
  log "Removing dangling images..."
  DANGLING=$(docker image prune -f 2>/dev/null | tail -1)
  log "  $DANGLING"

  # Prune build cache
  log "Removing build cache..."
  BUILDCACHE=$(docker builder prune -f 2>/dev/null | tail -1)
  log "  $BUILDCACHE"

  # Remove stopped containers (excluding our stack)
  log "Removing stopped containers..."
  STOPPED=$(docker container prune -f 2>/dev/null | tail -1)
  log "  $STOPPED"

  # Remove images not used by any container (older than 24h to avoid race with active builds)
  log "Removing unused images (older than 24h)..."
  UNUSED=$(docker image prune -a -f --filter "until=24h" 2>/dev/null | tail -1)
  log "  $UNUSED"

  # Remove anonymous volumes not used by any container
  log "Removing unused anonymous volumes..."
  VOLS=$(docker volume prune -f 2>/dev/null | tail -1)
  log "  $VOLS"

  echo ""
  log "Docker disk usage after cleanup:"
  docker system df

  exit 0
fi

# ---------- Handle --install ----------

if [ "$INSTALL_SERVICE" = true ]; then
  header "Installing TBD Platform systemd service"

  if [ "$(id -u)" != "0" ]; then
    err "Must run as root to install systemd service"
    exit 1
  fi

  # Detect the compose command for the service file
  if docker compose version &>/dev/null; then
    SVC_COMPOSE_CMD="docker compose -f $INFRA_DIR/docker-compose.yml --env-file $ENV_FILE"
  elif command_exists docker-compose; then
    SVC_COMPOSE_CMD="docker-compose --project-directory $INFRA_DIR -f $INFRA_DIR/docker-compose.yml"
  else
    err "docker compose is required but not found."
    exit 1
  fi

  cat > /etc/systemd/system/tbd-platform.service <<SVCEOF
[Unit]
Description=TBD Platform (Docker Compose)
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INFRA_DIR
ExecStart=$SVC_COMPOSE_CMD up -d
ExecStop=$SVC_COMPOSE_CMD down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
SVCEOF

  # Install cleanup timer (runs daily at 03:00)
  cat > /etc/systemd/system/tbd-cleanup.service <<SVCEOF
[Unit]
Description=TBD Platform Docker cleanup

[Service]
Type=oneshot
ExecStart=/usr/bin/docker image prune -a -f --filter "until=24h"
ExecStart=/usr/bin/docker builder prune -f
ExecStart=/usr/bin/docker container prune -f
ExecStart=/usr/bin/docker volume prune -f
SVCEOF

  cat > /etc/systemd/system/tbd-cleanup.timer <<SVCEOF
[Unit]
Description=Daily Docker cleanup for TBD Platform

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
SVCEOF

  systemctl daemon-reload
  systemctl enable docker.service
  systemctl enable tbd-platform.service
  systemctl enable tbd-cleanup.timer
  systemctl start tbd-cleanup.timer

  log "Installed and enabled:"
  log "  tbd-platform.service  — auto-starts all services on boot"
  log "  tbd-cleanup.timer     — daily Docker cleanup at 03:00"
  echo ""
  log "Verify with:"
  log "  systemctl status tbd-platform.service"
  log "  systemctl list-timers tbd-cleanup.timer"

  exit 0
fi

# ---------- Main Deploy Flow ----------

echo -e "${BOLD}"
echo "  _____ ____ ____    ____  _       _    __                      "
echo " |_   _| __ )  _ \  |  _ \| | __ _| |_ / _| ___  _ __ _ __ ___"
echo "   | | |  _ \ | | | | |_) | |/ _\` | __| |_ / _ \| '__| '_ \` _ \\"
echo "   | | | |_) | |_| | |  __/| | (_| | |_|  _| (_) | |  | | | | | |"
echo "   |_| |____/____/  |_|   |_|\__,_|\__|_|  \___/|_|  |_| |_| |_|"
echo -e "${NC}"
echo "  Production deployment script"
echo ""

# ---- Step 1: Prerequisites ----

header "Step 1/8: Checking prerequisites"

MISSING=0
for cmd in docker git curl; do
  if check_prereq "$cmd"; then
    log "$cmd: found ($(command -v "$cmd"))"
  else
    MISSING=1
  fi
done

# Verify docker compose was detected (already done above --down/--status handlers)
if [ -n "$COMPOSE_CMD" ]; then
  if [ "$COMPOSE_CMD" = "docker compose" ]; then
    log "docker compose: found ($(docker compose version --short 2>/dev/null || echo 'v2+'))"
  else
    warn "docker-compose (standalone) found — consider upgrading to Docker Compose v2"
  fi
else
  err "docker compose is required but not found."
  MISSING=1
fi

if [ "$MISSING" -ne 0 ]; then
  err "Missing prerequisites. Install them and re-run."
  exit 1
fi

# Check Docker is running
if ! docker info &>/dev/null; then
  err "Docker daemon is not running. Start it and re-run."
  exit 1
fi
log "Docker daemon: running"

# Enable BuildKit for faster, cacheable builds
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
log "BuildKit: enabled"

# Apply Docker daemon tuning if not already done
DOCKER_DAEMON_CFG="/etc/docker/daemon.json"
if [ -f "$DOCKER_DAEMON_CFG" ] && grep -q "max-concurrent-downloads" "$DOCKER_DAEMON_CFG" 2>/dev/null; then
  log "Docker daemon: already tuned"
else
  if [ -w /etc/docker ] 2>/dev/null || [ "$(id -u)" = "0" ]; then
    log "Applying Docker daemon performance config..."
    mkdir -p /etc/docker
    cat > "$DOCKER_DAEMON_CFG" <<'DEOF'
{
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  },
  "max-concurrent-downloads": 10,
  "max-concurrent-uploads": 10
}
DEOF
    # Reload docker daemon to pick up config (non-disruptive)
    if command_exists systemctl; then
      systemctl reload docker 2>/dev/null || warn "Could not reload Docker daemon — restart manually for tuning to take effect"
    fi
    log "Docker daemon: tuned (overlay2, log rotation, parallel pulls)"
  else
    warn "Cannot write $DOCKER_DAEMON_CFG (not root). Run as root for Docker daemon tuning."
  fi
fi

# ---- Step 2: Environment Configuration ----

header "Step 2/8: Configuring environment"

if [ ! -f "$ENV_FILE" ]; then
  log "Creating .env from template..."
  cp "$ENV_EXAMPLE" "$ENV_FILE"
else
  log "Existing .env found at $ENV_FILE"
fi

# Auto-generate secrets if they're still defaults
CURRENT_SECRET_KEY="$(env_get SECRET_KEY)"
if [ -z "$CURRENT_SECRET_KEY" ] || [ "$CURRENT_SECRET_KEY" = "change-me-in-production" ]; then
  NEW_SECRET=$(random_string 48)
  env_set "SECRET_KEY" "$NEW_SECRET"
  log "Generated SECRET_KEY (JWT signing)"
fi

CURRENT_FERNET="$(env_get SECRETS_ENCRYPTION_KEY)"
if [ -z "$CURRENT_FERNET" ]; then
  log "Generating SECRETS_ENCRYPTION_KEY (Fernet)..."
  FERNET_KEY=$(generate_fernet_key)
  if [ -n "$FERNET_KEY" ]; then
    env_set "SECRETS_ENCRYPTION_KEY" "$FERNET_KEY"
    log "Generated SECRETS_ENCRYPTION_KEY"
  else
    warn "Could not generate Fernet key automatically. You'll need to set SECRETS_ENCRYPTION_KEY manually."
  fi
fi

CURRENT_PG_PASS="$(env_get POSTGRES_PASSWORD)"
if [ -z "$CURRENT_PG_PASS" ] || [ "$CURRENT_PG_PASS" = "tbd_dev_password" ]; then
  if [ "$NO_PROMPT" = false ]; then
    warn "PostgreSQL password is set to the dev default."
    read -rp "  Generate a secure password? [Y/n]: " gen_pg
    if [ "${gen_pg,,}" != "n" ]; then
      PG_PASS=$(random_string 32)
      env_set "POSTGRES_PASSWORD" "$PG_PASS"
      log "Generated PostgreSQL password"
    fi
  fi
fi

# Interactive configuration for key services (skip with --no-prompt)
if [ "$NO_PROMPT" = false ]; then
  echo ""
  log "Configure key services (press Enter to keep current/default):"
  echo ""

  echo -e "  ${BOLD}Active Directory / LDAP${NC}"
  prompt_value "AD LDAP URL" "AD_LDAP_URL" "ldap://your-ad-server.example.com:389"
  prompt_value "AD Base DN" "AD_BASE_DN" "DC=example,DC=com"
  prompt_value "AD Bind DN" "AD_BIND_DN" "CN=svc-tbd,OU=Service Accounts,DC=example,DC=com"
  prompt_value "AD Bind Password" "AD_BIND_PASSWORD" "your-bind-password"

  echo ""
  echo -e "  ${BOLD}Proxmox${NC}"
  prompt_value "Proxmox API URL" "PROXMOX_API_URL" "https://your-proxmox-host:8006"
  prompt_value "Proxmox Token ID" "PROXMOX_TOKEN_ID" "tbd@pve!tbd-api"
  prompt_value "Proxmox Token Secret" "PROXMOX_TOKEN_SECRET" ""

  echo ""
  echo -e "  ${BOLD}Networking${NC}"
  prompt_value "Nginx Ingress IP" "NGINX_INGRESS_IP" ""
  prompt_value "Platform API IP" "PLATFORM_API_IP" ""
  prompt_value "NFS Server IP" "NFS_SERVER_IP" ""
  prompt_value "Internal DNS IP" "INTERNAL_DNS_IP" ""

  echo ""
  echo -e "  ${BOLD}GitHub App (optional — configure later if needed)${NC}"
  prompt_value "GitHub App ID" "GITHUB_APP_ID" ""
  prompt_value "GitHub Webhook Secret" "GITHUB_WEBHOOK_SECRET" ""

  echo ""
  echo -e "  ${BOLD}GitHub OAuth (user account linking — optional)${NC}"
  prompt_value "GitHub Client ID" "GITHUB_CLIENT_ID" ""
  prompt_value "GitHub Client Secret" "GITHUB_CLIENT_SECRET" ""

  echo ""
  echo -e "  ${BOLD}Grafana${NC}"
  prompt_value "Grafana Admin Password" "GRAFANA_ADMIN_PASSWORD" "tbd_admin"

  echo ""
  echo -e "  ${BOLD}Domain${NC}"
  prompt_value "Deploy domain suffix" "DEPLOY_DOMAIN_SUFFIX" "dev.sdc.cpp"

  # Derive default URLs from the domain suffix
  # Frontend uses /api (same-origin proxy via nginx) — no CORS issues
  DOMAIN_SUFFIX="$(env_get DEPLOY_DOMAIN_SUFFIX)"
  DOMAIN_SUFFIX="${DOMAIN_SUFFIX:-dev.sdc.cpp}"
  DEFAULT_API_URL="/api"
  DEFAULT_UI_URL="https://${DOMAIN_SUFFIX}"
  DEFAULT_CORS="${DEFAULT_UI_URL}"

  echo ""
  echo -e "  ${BOLD}Web UI${NC}"
  prompt_value "Frontend API URL (NEXT_PUBLIC_API_URL, /api = same-origin)" "NEXT_PUBLIC_API_URL" "$DEFAULT_API_URL"
  prompt_value "CORS Origins" "CORS_ORIGINS" "$DEFAULT_CORS"
fi

log "Environment configured at $ENV_FILE"

# ---- Step 3: Registry Auth ----

header "Step 3/8: Setting up registry authentication"

if [ -f "$REGISTRY_AUTH_DIR/htpasswd" ]; then
  log "Registry htpasswd already exists"
else
  log "Creating registry htpasswd file..."
  mkdir -p "$REGISTRY_AUTH_DIR"

  REG_PASS="$(env_get REGISTRY_PASSWORD)"
  if [ -z "$REG_PASS" ]; then
    REG_PASS=$(random_string 24)
    env_set "REGISTRY_PASSWORD" "$REG_PASS"
    env_set "REGISTRY_USERNAME" "tbd"
    log "Generated registry password"
  fi

  REG_USER="$(env_get REGISTRY_USERNAME)"
  REG_USER="${REG_USER:-tbd}"

  # Generate htpasswd using Docker (no local dependency needed)
  docker run --rm --entrypoint htpasswd httpd:2 -Bbn "$REG_USER" "$REG_PASS" \
    > "$REGISTRY_AUTH_DIR/htpasswd"
  log "Created $REGISTRY_AUTH_DIR/htpasswd (user: $REG_USER)"
fi

# ---- Step 4: SSL Certificates ----

header "Step 4/8: Setting up SSL certificates"

SSL_DIR="$INFRA_DIR/nginx/ssl"
SSL_CERT="$SSL_DIR/tbd.crt"
SSL_KEY="$SSL_DIR/tbd.key"

if [ -f "$SSL_CERT" ] && [ -f "$SSL_KEY" ]; then
  log "SSL certificate already exists at $SSL_DIR"
else
  log "Generating self-signed SSL certificate..."
  mkdir -p "$SSL_DIR"

  DOMAIN_SUFFIX="$(env_get DEPLOY_DOMAIN_SUFFIX)"
  DOMAIN_SUFFIX="${DOMAIN_SUFFIX:-dev.sdc.cpp}"

  openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout "$SSL_KEY" \
    -out "$SSL_CERT" \
    -subj "/CN=${DOMAIN_SUFFIX}" \
    -addext "subjectAltName=DNS:${DOMAIN_SUFFIX},DNS:*.${DOMAIN_SUFFIX},DNS:*.*.${DOMAIN_SUFFIX}" \
    2>/dev/null

  log "Generated self-signed cert for ${DOMAIN_SUFFIX} (valid 10 years)"
  log "  Cert: $SSL_CERT"
  log "  Key:  $SSL_KEY"
  warn "Browsers will show a security warning — accept/trust the cert on first visit"
fi

# ---- Step 5: Create required directories ----

header "Step 5/8: Preparing directories"

mkdir -p "$INFRA_DIR/nginx/conf.d/upstreams"
# Ensure .gitkeep exists for the upstreams dir
touch "$INFRA_DIR/nginx/conf.d/upstreams/.gitkeep"
log "Nginx upstream config directory ready"

# ---- Step 6: Build and start ----

header "Step 6/8: Building and starting services"

if [ "$REBUILD" = true ]; then
  log "Forcing full rebuild (--no-cache) — building api and web in parallel"
  # Build api and web in parallel (the two custom images), then start everything
  $COMPOSE_BASE build --no-cache api &
  BUILD_API_PID=$!
  $COMPOSE_BASE build --no-cache web &
  BUILD_WEB_PID=$!

  FAIL_BUILD=0
  wait $BUILD_API_PID || FAIL_BUILD=1
  wait $BUILD_WEB_PID || FAIL_BUILD=1
  if [ "$FAIL_BUILD" -ne 0 ]; then
    err "One or more image builds failed. Check output above."
    exit 1
  fi
  log "Parallel builds complete"

  # Clean up dangling images from the rebuild
  log "Pruning old build artifacts..."
  docker image prune -f >/dev/null 2>&1 || true
  docker builder prune -f --filter "until=24h" >/dev/null 2>&1 || true
fi

$COMPOSE_BASE up -d --build

log "Waiting for services to become healthy..."

# Wait for postgres first (other services depend on it)
MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
  PG_STATUS=$(docker inspect --format='{{.State.Health.Status}}' tbd-postgres 2>/dev/null || echo "not_found")
  if [ "$PG_STATUS" = "healthy" ]; then
    break
  fi
  sleep 2
  WAITED=$((WAITED + 2))
  echo -ne "\r  Waiting for PostgreSQL... ${WAITED}s"
done
echo ""

if [ "$PG_STATUS" != "healthy" ]; then
  err "PostgreSQL did not become healthy within ${MAX_WAIT}s"
  err "Check logs: docker compose -f $INFRA_DIR/docker-compose.yml logs postgres"
  exit 1
fi
log "PostgreSQL: healthy"

# Wait for API
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
  API_STATUS=$(curl -sf http://localhost:8000/health 2>/dev/null || echo "")
  if echo "$API_STATUS" | grep -q '"ok"' 2>/dev/null; then
    break
  fi
  sleep 2
  WAITED=$((WAITED + 2))
  echo -ne "\r  Waiting for API... ${WAITED}s"
done
echo ""

if ! echo "$API_STATUS" | grep -q '"ok"' 2>/dev/null; then
  err "API did not become healthy within ${MAX_WAIT}s"
  err "Check logs: docker compose -f $INFRA_DIR/docker-compose.yml logs api"
  exit 1
fi
log "API: healthy"

# ---- Step 6: Database Migrations ----

header "Step 7/8: Running database migrations"

log "Running alembic upgrade head..."
if docker exec tbd-api alembic upgrade head 2>&1; then
  log "Migrations complete"
else
  MIGRATION_EXIT=$?
  err "Migration failed (exit code $MIGRATION_EXIT)"
  err "Fetching API container logs for diagnostics:"
  $COMPOSE_BASE logs --tail=40 api
  err ""
  err "You may need to inspect the database state manually:"
  err "  docker exec tbd-api alembic current"
  err "  docker exec tbd-api alembic history"
  exit 1
fi

# Verify table count
TABLE_COUNT=$(docker exec tbd-postgres psql -U tbd -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'" 2>/dev/null | tr -d ' ')
log "Database tables: $TABLE_COUNT"

# Show current migration revision
ALEMBIC_HEAD=$(docker exec tbd-api alembic current 2>/dev/null | grep -oE '[0-9]+' | tail -1 || echo "unknown")
log "Alembic revision: $ALEMBIC_HEAD"

# ---- Step 7: Final Health Check ----

header "Step 8/8: Verifying deployment"

echo ""
PASS=0
FAIL=0

# API
api_check=$(curl -sf http://localhost:8000/health 2>/dev/null || echo "")
if echo "$api_check" | grep -q '"ok"'; then
  echo -e "  ${GREEN}PASS${NC}  API           http://localhost:8000/health"
  PASS=$((PASS + 1))
else
  echo -e "  ${RED}FAIL${NC}  API           http://localhost:8000/health"
  FAIL=$((FAIL + 1))
fi

# API Docs
api_docs=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8000/docs 2>/dev/null || echo "000")
if [ "$api_docs" = "200" ]; then
  echo -e "  ${GREEN}PASS${NC}  API Docs      http://localhost:8000/docs"
  PASS=$((PASS + 1))
else
  echo -e "  ${RED}FAIL${NC}  API Docs      http://localhost:8000/docs (HTTP $api_docs)"
  FAIL=$((FAIL + 1))
fi

# Web UI
web_check=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:3000/ 2>/dev/null || echo "000")
if [ "$web_check" = "200" ] || [ "$web_check" = "307" ]; then
  echo -e "  ${GREEN}PASS${NC}  Web UI        http://localhost:3000"
  PASS=$((PASS + 1))
else
  echo -e "  ${YELLOW}WARN${NC}  Web UI        http://localhost:3000 (HTTP $web_check — may still be starting)"
  FAIL=$((FAIL + 1))
fi

# Registry
reg_check=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/v2/ 2>/dev/null || echo "000")
if [ "$reg_check" = "200" ] || [ "$reg_check" = "401" ]; then
  echo -e "  ${GREEN}PASS${NC}  Registry      http://localhost:5000/v2/"
  PASS=$((PASS + 1))
else
  echo -e "  ${RED}FAIL${NC}  Registry      http://localhost:5000/v2/ (HTTP $reg_check)"
  FAIL=$((FAIL + 1))
fi

# Alembic current
alembic_ver=$(docker exec tbd-api alembic current 2>/dev/null | grep -oE '[0-9]+' | tail -1 || echo "unknown")
alembic_head=$(docker exec tbd-api alembic heads 2>/dev/null | grep -oE '[0-9]+' | tail -1 || echo "unknown")
if [ "$alembic_ver" = "$alembic_head" ]; then
  echo -e "  ${GREEN}PASS${NC}  Migrations    at head ($alembic_ver)"
  PASS=$((PASS + 1))
else
  echo -e "  ${YELLOW}WARN${NC}  Migrations    at revision $alembic_ver (head is $alembic_head)"
fi

# Grafana
grafana_check=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:3001/api/health 2>/dev/null || echo "000")
if [ "$grafana_check" = "200" ]; then
  echo -e "  ${GREEN}PASS${NC}  Grafana       http://localhost:3001"
  PASS=$((PASS + 1))
else
  echo -e "  ${YELLOW}WARN${NC}  Grafana       http://localhost:3001 (HTTP $grafana_check — may still be starting)"
fi

# Prometheus
prom_check=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:9090/-/healthy 2>/dev/null || echo "000")
if [ "$prom_check" = "200" ]; then
  echo -e "  ${GREEN}PASS${NC}  Prometheus    http://localhost:9090"
  PASS=$((PASS + 1))
else
  echo -e "  ${YELLOW}WARN${NC}  Prometheus    http://localhost:9090 (HTTP $prom_check — may still be starting)"
fi

# ---------- Summary ----------

echo ""
echo -e "${BOLD}=================================================${NC}"
if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}  TBD Platform deployed successfully!${NC}"
else
  echo -e "${YELLOW}${BOLD}  TBD Platform deployed with $FAIL warning(s)${NC}"
fi
echo -e "${BOLD}=================================================${NC}"
echo ""
# Read domain suffix for display
DEPLOY_SUFFIX="$(env_get DEPLOY_DOMAIN_SUFFIX)"
DEPLOY_SUFFIX="${DEPLOY_SUFFIX:-dev.sdc.cpp}"

echo "  Services:"
echo "    Web UI:       https://${DEPLOY_SUFFIX}"
echo "    API (proxy):  https://${DEPLOY_SUFFIX}/api/*  (same-origin, used by frontend)"
echo "    API (direct): https://api.${DEPLOY_SUFFIX}    (Swagger docs, external clients)"
echo "    API Docs:     https://api.${DEPLOY_SUFFIX}/docs"
echo "    Registry:     https://registry.${DEPLOY_SUFFIX}"
echo "    Grafana:      http://localhost:3001"
echo "    Prometheus:   http://localhost:9090"
echo ""
echo "  Domain scheme:"
echo "    Deploys:      https://<deployid>.<username>.${DEPLOY_SUFFIX}"
echo "    DNS wildcard: *.*.${DEPLOY_SUFFIX} -> this server's IP"
echo ""
echo "  Commands:"
echo "    Status:       ./deploy.sh --status"
echo "    Logs:         docker compose -f infra/docker-compose.yml logs -f [service]"
echo "    Stop:         ./deploy.sh --down"
echo "    Rebuild:      ./deploy.sh --rebuild"
echo "    Cleanup:      ./deploy.sh --cleanup"
echo "    Auto-start:   ./deploy.sh --install   (systemd service + daily cleanup timer)"
echo ""
echo "  Next steps:"
echo "    1. Configure DNS:  *.*.${DEPLOY_SUFFIX} -> this server's IP"
echo "    2. Set up GitHub App (see docs/setup.md Section 3)"
echo "    3. Create your first project via the Web UI or API"
echo "    4. Import a GitHub repo to enable auto-build and auto-deploy"
echo ""
