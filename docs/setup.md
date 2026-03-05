# Setup Guide

Step-by-step instructions to deploy the TBD platform from a fresh clone.

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Docker + Docker Compose | 24+ / v2+ | Runs all platform services |
| Git | 2.x | Clone the repository |
| A GitHub account | - | Create the GitHub App |
| (Optional) AD/LDAP server | - | Authentication; can be deferred for initial testing |

Hardware: any machine with 4 GB+ RAM and Docker installed. The platform runs entirely in containers.

## 1. Clone and Configure

```bash
git clone https://github.com/your-org/tbd-dev.git
cd tbd-dev
```

Copy the environment template and edit it:

```bash
cp infra/.env.example infra/.env
```

Open `infra/.env` and fill in each section. The file is documented inline, but here is a walkthrough of every variable:

### PostgreSQL

```env
POSTGRES_PASSWORD=tbd_dev_password
```

The password for the `tbd` database user. Change this in any non-local environment.

### Active Directory / LDAP

```env
AD_LDAP_URL=ldap://your-ad-server.example.com:389
AD_BASE_DN=DC=example,DC=com
AD_BIND_DN=CN=svc-tbd,OU=Service Accounts,DC=example,DC=com
AD_BIND_PASSWORD=your-bind-password
```

These point to your school's Active Directory server. The bind account (`svc-tbd`) needs read access to search users and groups.

If you do not have AD available yet, the API will still start, but login will fail. You can test the rest of the stack (webhooks, builds, deploys) using direct API calls with a manually-created JWT.

### API

```env
SECRET_KEY=change-me-in-production
CORS_ORIGINS=http://localhost:3000
```

- `SECRET_KEY`: used to sign JWT tokens. Generate a random 32+ character string for production.
- `CORS_ORIGINS`: comma-separated list of allowed frontend origins.

### Registry

```env
REGISTRY_URL=http://localhost:5000
```

Internal OCI image registry. When running via Docker Compose, the API container uses `http://registry:5000` (set automatically in `docker-compose.yml`). This variable is for host-level tools like `docker push`.

### GitHub App

```env
GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY=
GITHUB_WEBHOOK_SECRET=
```

See [Section 3: GitHub App Setup](#3-github-app-setup) below for how to create these.

### Deploy Queue

```env
DEPLOY_MAX_CONCURRENT=2
DEPLOY_QUEUE_MAX_SIZE=50
```

- `DEPLOY_MAX_CONCURRENT`: max deploys running simultaneously per environment.
- `DEPLOY_QUEUE_MAX_SIZE`: max queued deploys per environment before new ones are rejected.

## 2. Start the Platform

### 2a. Create the registry htpasswd file

The OCI registry uses basic auth. Create the auth directory and htpasswd file:

```bash
mkdir -p infra/registry/auth
```

Install `htpasswd` (from `apache2-utils` on Debian/Ubuntu) or use Docker:

```bash
# Option A: htpasswd installed locally
htpasswd -Bbn tbd registry-password > infra/registry/auth/htpasswd

# Option B: use Docker
docker run --rm --entrypoint htpasswd httpd:2 -Bbn tbd registry-password \
  > infra/registry/auth/htpasswd
```

Replace `registry-password` with a real password. The `tbd` user is what the built-in builder and API use to push/pull images.

### 2b. Start Docker Compose

```bash
cd infra
docker compose up -d
```

This starts the following services:

| Service | Port | Description |
|---|---|---|
| `postgres` | 5432 | PostgreSQL 16 database |
| `registry` | 5000 | OCI image registry (registry:2) |
| `nginx` | 80 | Wildcard ingress for `*.dev.sdc.cpp` |
| `api` | 8000 | TBD Control Plane API (FastAPI) |
| `web` | 3000 | Next.js developer dashboard |
| `loki` | 3100 | Log aggregation |
| `promtail` | — | Log collector (ships to Loki) |
| `prometheus` | 9090 | Metrics scraping |
| `grafana` | 3001 | Dashboards and observability |

Verify everything is running:

```bash
docker compose ps
```

All containers should show `Up` / `healthy`.

### 2c. Run database migrations

The API auto-creates tables on first startup (development mode), but for production you should run Alembic migrations explicitly:

```bash
# From the repo root (not infra/)
cd api

# Option A: run Alembic directly (requires Python env with deps)
DATABASE_URL=postgresql+asyncpg://tbd:tbd_dev_password@localhost:5432/tbd \
  alembic upgrade head

# Option B: run inside the API container
docker exec tbd-api alembic upgrade head
```

You should see output like:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 001, Initial schema
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, Add repo fields
INFO  [alembic.runtime.migration] Running upgrade 002 -> 003, Add build pipeline fields
INFO  [alembic.runtime.migration] Running upgrade 003 -> 004, Add GitHub user fields
INFO  [alembic.runtime.migration] Running upgrade 004 -> 005, Add GitHub token
INFO  [alembic.runtime.migration] Running upgrade 005 -> 006, Add build settings
INFO  [alembic.runtime.migration] Running upgrade 006 -> 007, Add network policies
INFO  [alembic.runtime.migration] Running upgrade 007 -> 008, Add deploy logs
INFO  [alembic.runtime.migration] Running upgrade 008 -> 009, Add project members
```

### 2d. Verify the API

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok", "service": "tbd-api", "version": "0.1.0"}
```

Browse the auto-generated API docs at: http://localhost:8000/docs

### 2e. Verify the registry

```bash
curl http://localhost:5000/v2/
```

This should return `401 Unauthorized` (auth is required). Verify with credentials:

```bash
curl -u tbd:registry-password http://localhost:5000/v2/
```

Expected: `{}`

## 3. GitHub App Setup

The TBD platform uses a GitHub App to receive webhooks and post commit statuses. You need to create one in your GitHub organization (or personal account for testing).

### 3a. Create the App

1. Go to **Settings > Developer settings > GitHub Apps > New GitHub App**
   (URL: `https://github.com/settings/apps/new` for personal, or `https://github.com/organizations/YOUR-ORG/settings/apps/new` for org)

2. Fill in the form:

| Field | Value |
|---|---|
| GitHub App name | `TBD Platform` (or any unique name) |
| Homepage URL | `http://dev.sdc.cpp` (or your platform URL) |
| Webhook URL | `http://<your-server-ip>:8000/integrations/github/webhook` |
| Webhook secret | Generate a random string (save it for `.env`) |

3. Set **Permissions**:

| Permission | Access | Why |
|---|---|---|
| Contents | Read-only | Read repo contents for builds |
| Metadata | Read-only | Required by GitHub |
| Commit statuses | Read & write | Post build/deploy status checks |
| Pull requests | Read-only | Detect PR events |
| Checks | Read & write | (Optional) Create check runs |

4. Subscribe to **Events**:
   - Push
   - Pull request

5. Set **Where can this app be installed?** to "Only on this account" (or "Any account" if sharing across orgs).

6. Click **Create GitHub App**.

### 3b. Generate a Private Key

After creating the app:

1. On the app settings page, scroll to **Private keys**.
2. Click **Generate a private key**. A `.pem` file will download.
3. Convert the PEM file contents to a single-line string for the `.env` file:

```bash
# Convert newlines to literal \n for the env var
awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' your-app-name.pem
```

4. Copy the output into your `.env` file:

```env
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\nMIIEpA...\n-----END RSA PRIVATE KEY-----\n
GITHUB_WEBHOOK_SECRET=your-webhook-secret-from-step-2
```

### 3c. Install the App on a Repository

1. Go to `https://github.com/apps/YOUR-APP-NAME/installations/new`.
2. Select the organization or account.
3. Choose **Only select repositories** and pick the repo(s) you want to deploy.
4. Click **Install**.
5. Note the **installation ID** from the URL after install (e.g. `https://github.com/settings/installations/12345678` -> ID is `12345678`).

### 3d. Link a Repository to a TBD Project

After a project exists in TBD, link the GitHub repo:

```bash
# 1. Login to get a JWT token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"your-ad-user","password":"your-password"}' \
  | jq -r '.access_token')

# 2. Create a project (if not already created)
PROJECT_ID=$(curl -s -X POST http://localhost:8000/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"My App","slug":"my-app"}' \
  | jq -r '.id')

# 3. Link the GitHub repo
curl -X POST http://localhost:8000/integrations/github/install \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "'$PROJECT_ID'",
    "repo_id": "GITHUB_REPO_NUMERIC_ID",
    "repo_full_name": "your-org/your-repo",
    "install_id": "INSTALLATION_ID_FROM_STEP_3c",
    "default_branch": "main"
  }'
```

You can find the GitHub repo numeric ID via the GitHub API:
```bash
curl -s https://api.github.com/repos/your-org/your-repo | jq '.id'
```

## 4. DNS Setup

The platform uses a wildcard DNS pattern under `*.dev.sdc.cpp` (configurable via the `DEPLOY_DOMAIN_SUFFIX` env var).

- **Platform UI**: `dev.sdc.cpp`
- **Platform API**: `api.dev.sdc.cpp`
- **Registry**: `registry.dev.sdc.cpp`
- **Deploys**: `<deployid>-<username>.dev.sdc.cpp`

### Local Development (hosts file)

For local testing, add entries to your hosts file (`/etc/hosts` on Linux/Mac, `C:\Windows\System32\drivers\etc\hosts` on Windows):

```
127.0.0.1  dev.sdc.cpp
127.0.0.1  api.dev.sdc.cpp
127.0.0.1  registry.dev.sdc.cpp
# Per-deploy entries (add as needed):
127.0.0.1  a1b2c3d4.jsmith.dev.sdc.cpp
```

You will need to add entries for each deploy you want to test locally. The format is `<first-8-hex-of-deploy-id>.<username>.dev.sdc.cpp`.

### Production (Internal DNS)

Configure your internal DNS server with a wildcard A record:

```
*.dev.sdc.cpp.  300  IN  A  <nginx-server-ip>
dev.sdc.cpp.    300  IN  A  <nginx-server-ip>
```

The first record routes all deploy traffic (`<deployid>-<username>.dev.sdc.cpp`) to the Nginx ingress. The second routes the platform UI itself. Sub-domains like `api.dev.sdc.cpp` and `registry.dev.sdc.cpp` are also matched by the wildcard (or you can add explicit A records for them).

## 5. First Deploy (End-to-End Test)

Once the platform, GitHub App, and DNS are configured, test the full pipeline:

### 5a. Connect a Repository

1. In the TBD web UI, create a new project.
2. Link a GitHub repository using the GitHub integration (`POST /projects/{id}/repo`).
3. Optionally configure framework, build commands, and auto-deploy settings.

### 5b. Trigger a Build

Push a commit to the connected repo's default branch (or open a PR). You should see:

1. GitHub webhook fires to the TBD API.
2. TBD creates a build record and posts a "pending" commit status to GitHub.
3. The built-in builder clones the repo, detects the framework, and generates a Dockerfile.
4. `docker build` runs inside the API container and the image is pushed to the registry.
5. TBD records the artifact and enqueues a deploy (if `auto_deploy` is enabled).
6. The runtime plane provisions an LXC container and promotes the deploy.
7. TBD posts a "success" commit status to GitHub.

You can also trigger a build manually via:

```bash
curl -sf -X POST "http://localhost:8000/projects/$PROJECT_ID/builds/trigger" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"branch": "main"}'
```

### 5c. Verify the Deploy

Once the deploy reaches `active` state, access it at its assigned URL:

```bash
curl -s https://<deployid>-<username>.dev.sdc.cpp/health
```

The deploy URL is returned in the deploy record (`GET /projects/{id}/deploys`).

## 6. Built-in Builder

The build pipeline uses a built-in builder that runs inside the API container. No external GitHub Actions runners or buildpack CLIs are required.

The builder automatically:
- Clones the connected repo on webhook or manual trigger
- Detects the framework (Next.js, React, Python, Node.js, Go, static, Dockerfile)
- Generates a Dockerfile if none exists
- Runs `docker build` and pushes the image to the internal registry

Requirements for the API container:
- Docker socket mounted (Docker-in-Docker via `/var/run/docker.sock`)
- Network access to `registry.dev.sdc.cpp:5000`
- GitHub App credentials configured in `.env`

## 7. Verifying the Stack

Run through these checks after setup to make sure everything is working:

```bash
# 1. API health
curl -s http://localhost:8000/health | jq .

# 2. API docs load
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs
# Expected: 200

# 3. Registry auth
curl -s -u tbd:registry-password http://localhost:5000/v2/ | jq .

# 4. Database tables exist
docker exec tbd-postgres psql -U tbd -c "\dt"
# Expected: 15 tables listed

# 5. Alembic migration status
docker exec tbd-api alembic current
# Expected: 009 (head)

# 6. Nginx routing
curl -s -H "Host: api.dev.sdc.cpp" http://localhost/health | jq .
# Expected: API health response proxied through Nginx

# 7. Webhook endpoint reachable
curl -s -X POST http://localhost:8000/integrations/github/webhook \
  -H "X-GitHub-Event: ping" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: {"status":"pong"}
```

## 8. Troubleshooting

### API container won't start

```bash
docker compose logs api
```

Common causes:
- PostgreSQL not ready yet (the healthcheck dependency should handle this, but check `docker compose ps` for postgres status).
- Invalid `DATABASE_URL` — verify the password matches `POSTGRES_PASSWORD`.

### Alembic migration fails

```bash
docker exec tbd-api alembic current
docker exec tbd-api alembic history
```

If the database is ahead of or behind migrations, you may need to stamp or re-run:

```bash
# Mark current state without running migrations
docker exec tbd-api alembic stamp head

# Or re-run from scratch (destructive)
docker exec tbd-api alembic downgrade base
docker exec tbd-api alembic upgrade head
```

### Webhook signature verification fails

- Verify `GITHUB_WEBHOOK_SECRET` in `.env` matches the secret in your GitHub App settings.
- If the secret is empty, verification is skipped (dev mode). Set it for production.

### GitHub commit status not posting

- Check API logs: `docker compose logs api | grep "commit status"`
- Verify `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY` are set correctly.
- The private key must have literal `\n` characters (not actual newlines) in the `.env` file.
- Verify the app is installed on the repository and has "Commit statuses: Read & write" permission.

### Registry push/pull fails

- Verify the htpasswd file exists: `ls infra/registry/auth/htpasswd`
- Test auth: `curl -u tbd:password http://localhost:5000/v2/`
- From Docker: `docker login localhost:5000 -u tbd`

## 9. Architecture Reference

Domains (default suffix: `dev.sdc.cpp`):
- `dev.sdc.cpp` -> Nginx -> Web UI (:3000)
- `api.dev.sdc.cpp` -> Nginx -> API (:8000)
- `registry.dev.sdc.cpp` -> Nginx -> Registry (:5000)
- `<deployid>-<username>.dev.sdc.cpp` -> Nginx -> LXC container

Requests flow:
1. `*.dev.sdc.cpp` -> Nginx -> LXC containers (per-deploy routing)
2. GitHub webhooks -> API -> build records + commit statuses
3. API built-in builder -> registry (push image) -> record artifact, trigger deploy
4. API -> Proxmox (provision LXC) -> health check -> promote
