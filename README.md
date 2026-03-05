# TBD
Platform for developers to deploy with ease on Proxmox, replacing EC2 + Lambda without worrying about infrastructure.

## Vision
TBD is a Vercel-like internal platform for a school environment that lets developers deploy apps quickly while infrastructure managers keep control and visibility. It targets Proxmox as the compute substrate, favors fast, dense LXC deployments in v1, and keeps everything on the private network (HTTPS optional).

## Personas and Roles
- Developer: connects repos, deploys, views logs/metrics, manages app settings.
- Staff (Infrastructure): full visibility, troubleshooting, approvals, and operational controls.
- Faculty (Admin): full access including policy, quotas, networking, and platform configuration.

Role-based access control is enforced via Active Directory group membership.

## Goals
- One-click deploys from GitHub with automatic preview environments.
- Proxmox-native orchestration using LXC for fast startup and high density.
- Segmented networking per project with flat IP allocation or VLAN-backed isolation.
- AD authentication with GitHub OAuth for repo access, and auditable access.
- Clear operational workflows for staff oversight.

## Non-goals (v1)
- Public, internet-facing PaaS at scale.
- Multi-region disaster recovery.
- Kubernetes-first runtime (planned later).
- Commercial billing or multi-tenant public onboarding.

## Feature Scope
### MVP (LXC-first)
- Repo connection via GitHub App/webhooks.
- Built-in build pipeline with automatic framework detection and Docker image generation.
- GitHub OAuth for account linking and repo access.
- Preview environments per PR and production deploys per main branch.
- Flat IP allocation (primary) with VLAN-backed network segmentation as fallback.
- AD-based RBAC (Developer, Staff, Faculty).
- Secrets management (encrypted at rest, scoped per project/env).
- Logs, metrics, and audit trails.
- Rollbacks to prior deploys.
- Self-service project provisioning with quotas.

### Phase 2
- Image registry and build cache optimizations.
- Blue/green or canary deploys.
- Autoscaling policies (horizontal scale based on CPU/RAM/requests).
- Advanced policy enforcement (resource limits, egress controls).

### Phase 3 (Kubernetes)
- Optional Kubernetes runtime plane on Proxmox VMs.
- GitOps workflows and Helm-based deployments.
- Advanced ingress and service mesh integrations.

## Architecture Overview
TBD uses two planes to keep the platform maintainable and secure:

1) Control Plane
- Web UI + API
- Built-in builder (framework detection, Dockerfile generation, docker build + push)
- Auth/RBAC (AD + GitHub OAuth) + audit
- Project, env, and policy management
- Proxmox adapter + network allocator
- Build coordinator + deploy queue

2) Runtime Plane (v1)
- LXC containers on Proxmox
- Flat IP allocation (primary) or per-env VLAN tagging (fallback)
- Nginx ingress with dynamic per-deploy upstream configs

### Component Map (v1)
- Web UI: Next.js developer dashboard and staff/admin console
- API Service: FastAPI orchestration, policies, and workflow engine
- Built-in Builder: clones repos, detects frameworks, generates Dockerfiles, builds and pushes OCI images
- Proxmox Adapter: LXC lifecycle, snapshots, and resource allocation
- Build Coordinator: manages artifact records and triggers deploys
- Network Allocator: flat IP allocation or VLAN/subnet mapping and IP reservation
- Secrets Service: encrypted env vars and scoped access
- Ingress/DNS Service: Nginx with dynamic upstream configs for `*.dev.sdc.cpp` routing
- Observability Stack: Prometheus, Grafana, Loki + Promtail for logs, metrics, and audit trails

## Proxmox Integration (LXC First)
- Workloads run as unprivileged LXC containers on Proxmox hosts.
- Proxmox API manages container lifecycle, snapshots, and resource limits.
- Containers are assigned flat IPs from a configurable range (primary), or VLAN-tagged IPs (fallback).
- Bin-pack scheduler selects target nodes based on available CPU/RAM.
- Fast provisioning enables preview environments per PR.

## Repository Integration and Deploy Flow
GitHub is the primary integration point.

1) Developer connects GitHub repo via the platform UI.
2) Webhook fires to the TBD API on push/PR.
3) Built-in builder clones the repo, detects the framework, and builds a Docker image.
4) Image is pushed to the internal registry.
5) Platform posts build and deploy status back to GitHub.
6) LXC is provisioned from the OCI image (skopeo + umoci + init script injection).
7) Deploy is promoted on successful health checks.

## Build and Deploy Strategy (Built-in Builder)
- GitHub App installs webhooks on connected repos.
- The API includes a built-in builder that runs as a background task.
- On webhook or manual trigger, the builder clones the repo, detects the framework, generates a Dockerfile (if none exists), and runs `docker build`.
- Supported frameworks: Next.js, React (CRA/Vite), Python, Node.js, Go, static sites, and custom Dockerfiles.
- OCI images are pushed to the internal registry and tagged by commit SHA + `latest`.
- If `auto_deploy` is enabled on the project, the platform automatically triggers a deploy after a successful build.
- Platform pulls OCI images, unpacks to LXC rootfs, injects an init script and secrets, and provisions a container.
- Deploy URLs follow the pattern `<deployid>-<username>.dev.sdc.cpp`.

## Runtime Packaging Strategy
- Built-in builder auto-detects frameworks: Next.js, React, Python, Node.js, Go, static sites.
- If the repo contains a Dockerfile, it is used directly.
- Otherwise, a Dockerfile is generated from templates based on the detected framework.
- Per-project overrides available for `install_command`, `build_command`, `output_directory`, and `root_directory`.
- Runtime contract: bind to `$PORT`, emit logs to stdout/stderr, and expose a `/health` endpoint.
- Secrets are injected as environment variables at runtime via `/etc/tbd/secrets.env`.
- Artifact format is OCI image stored in the internal registry.

## OCI to LXC Conversion (v1)
- The built-in builder creates OCI images and pushes to the internal registry.
- Platform pulls images, unpacks to a rootfs using OCI tools, and injects a custom `/sbin/init` script.
- The init script replaces systemd (which Docker images lack) and handles networking, env vars, and app startup.
- LXC containers boot from the prepared rootfs and run the app as PID 1.

### OCI to LXC Runbook
1) Pull image from registry using `skopeo` to an OCI layout.
2) Unpack OCI layout to rootfs with `umoci`.
3) Extract OCI config (CMD, ENV, EXPOSE, WorkingDir).
4) Inject `/sbin/init` script into rootfs (networking, env vars, app exec).
5) Inject secrets into `/etc/tbd/secrets.env`.
6) Package rootfs into a `.tar.gz` template tarball.
7) Upload template to Proxmox and create LXC container.
8) Run `/health` checks and promote or rollback.

## Networking Model
The platform supports two networking modes:

### Flat IP Mode (Primary)
- Containers are assigned IPs from a configurable flat range on the existing bridge.
- The deploy executor scans existing TBD containers and picks the next unused IP.
- No VLAN tagging is required; all containers share the same network segment.

### VLAN Mode (Fallback)
- Each project gets a dedicated VLAN for Layer 2 isolation.
- VLAN tag maps to subnet: VLAN `1000+N` -> `172.16.N.0/25`.
- Environments (preview/staging/prod) live inside the project VLAN.

## DNS and Routing
- Wildcard domain `*.dev.sdc.cpp` points to the platform Nginx ingress inside the VPN.
- All deploy URLs follow the pattern `<deployid>-<username>.dev.sdc.cpp` where `<deployid>` is the first 8 hex characters of the deploy UUID and `<username>` is the sanitized project owner username.
- A single wildcard DNS record resolves all deploys without per-deploy DNS registration.
- Nginx matches incoming requests against deploy hostnames and proxies to the corresponding LXC container IP.

## Authentication and Authorization
- AD authentication via LDAP/Kerberos for platform login (JWT-based sessions).
- GitHub OAuth for account linking and repo access (`/auth/github` flow).
- Group-to-role mapping:
  - Developers -> Developer role
  - Staff -> Infrastructure role
  - Faculty -> Admin role
- All actions are logged and auditable.

## Secrets Management
- Secrets are stored in an internal encrypted database.
- Access is scoped by project and environment.
- All reads and writes are recorded in the audit log.

## Storage
- NFS is the primary shared storage backend.
- Use cases:
  - Build cache and artifacts
  - Persistent volumes for runtime containers
  - Backup targets for config and metadata

## Observability
- Stack: Prometheus + Grafana + Loki for MVP.
- Logs: Loki + Promtail for centralized log aggregation from LXC journald.
- Metrics: Prometheus scrapes CPU/RAM/disk and request metrics per app; Grafana dashboards.
- Audit: who deployed what, when, and from which commit (stored in platform DB).

## Security and Isolation
- Private-network first; HTTPS optional but supported.
- Network isolation via flat IP segmentation (primary) or VLAN segmentation per project (fallback).
- Per-project network policies for egress/ingress control.
- Secrets encrypted at rest and injected at runtime.
- RBAC enforced at API and UI layers.

## Operations
- Backups: scheduled backups of platform metadata and NFS volumes.
- Upgrades: rolling upgrades of control and runtime planes.
- Capacity: resource quotas per project and environment.
- Incident response: audit logs + rollback tooling.

## Registry Choice (Local)
For MVP, a local registry inside the VPN is recommended and supported.

Options:
- `registry:2`: simplest and fastest to stand up; good for MVP.
- Harbor: heavier but provides UI, RBAC, scanning, and retention policies.

Recommended MVP path:
- Start with `registry:2` on a dedicated VM or Proxmox host.
- Store registry data on NFS for durability.
- Basic auth (htpasswd) for push/pull access.
- TLS optional inside VPN; enable if needed later.
- Weekly garbage collection to reclaim unreferenced layers.
- Retention policy: keep last 10 images per project; prune older artifacts.

## Scheduling and Placement
- Bin-pack by CPU/RAM: place new LXC containers on the host with the most available resources.
- Node health checks: monitor Proxmox hosts for CPU/RAM/disk pressure and network reachability.
- Drain unhealthy nodes: migrate or reschedule containers away from failing hosts.
- Quota enforcement: reject deploys that exceed project resource limits before provisioning.

## Network Egress Policy
- Default deny: containers cannot reach the internet or other project networks by default.
- Per-project network policies managed via `/admin/network-policies` API (direction, protocol, port, destination, allow/deny).
- Staff/faculty can approve outbound internet access per project.
- Allowed by default: NFS, internal DNS, platform API, and registry traffic.

## Technical Design Appendix (v1 LXC)
### Services
- Web UI for developers and staff.
- API Service (FastAPI) for orchestration and policy enforcement.
- Built-in Builder for repo cloning, framework detection, Dockerfile generation, and `docker build` + push.
- Proxmox Adapter for LXC lifecycle and resource controls.
- Build Coordinator for artifact records and deploy triggering.
- Network Allocator for flat IP allocation (primary) or VLAN/subnet mapping and IP reservation.
- Secrets Service for encrypted storage and scoped access.
- Ingress/DNS Service for `*.dev.sdc.cpp` routing via Nginx.
- Observability Stack for logs, metrics, and auditing.

### Data Model (core)
- users, groups, group_role_map
- projects, repos, environments
- builds, artifacts, deploys
- secrets, vlans, quotas
- audit_log
- network_policies
- project_members

### Core APIs (examples)
- `POST /auth/login` and `GET /auth/me`
- `GET /auth/github` and `GET /auth/github/callback` (GitHub OAuth)
- `POST /integrations/github/install` and `POST /integrations/github/webhook`
- `GET/POST /projects` and `PATCH/DELETE /projects/{id}`
- `GET/POST /projects/{id}/environments`
- `POST /projects/{id}/builds/trigger` and `POST /projects/{id}/builds/{id}/deploy`
- `POST /projects/{id}/deploys` and `POST /deploys/{id}/rollback`
- `GET/POST/DELETE /projects/{id}/secrets`
- `GET /networks/vlans` and `POST /networks/vlans/reserve`
- `GET/POST/PATCH/DELETE /admin/network-policies`
- `GET /admin/stats` and `GET /admin/users`
- `GET /audits`

### Deployment State Machine
- queued
- building
- artifact_ready
- provisioning
- healthy
- active
- failed
- rolled_back

### Proxmox Adapter (LXC)
- Create/update LXC containers and apply resource limits.
- Attach flat IP (primary) or VLAN-tagged NICs per environment.
- Mount NFS volumes and inject environment variables.
- Inject custom `/sbin/init` script for app startup and health checks (Docker images lack systemd).
- Snapshot before deploy and rollback on failure.
- Gate promotion on health checks.

### Network Allocator
- Primary: allocate flat IPs from a configurable range (scans existing containers, picks next free IP).
- Fallback: map VLAN to subnet based on staff-defined rules, reserve VLANs per project, allocate IPs per environment.
- DNS resolved via wildcard `*.dev.sdc.cpp` record (no per-deploy registration needed).

### Security Model
- AD authentication with GitHub OAuth for account linking and repo access.
- API tokens scoped to project and environment.
- Secrets encrypted at rest with audited access.
- Full audit log for deploys, config changes, and admin actions.

### Observability
- Centralized logs per project and environment.
- Metrics for CPU/RAM/IO and request latency.
- Build and deploy timing dashboards.

### Operations
- Backups for metadata DB and NFS volumes.
- Rolling upgrades for control and runtime planes.
- Quotas and alerts for capacity planning.

## Implementation Guide (Design-Only)
### Prerequisites
- Proxmox cluster reachable from the control plane.
- NFS share for artifacts and persistent volumes.
- Internal DNS with wildcard `*.dev.sdc.cpp`.
- AD/LDAP endpoints and group mappings.
- GitHub App credentials for OAuth and webhook integration.

### Bootstrap Order
1) Local OCI registry (`registry:2`) with NFS-backed storage.
2) Control plane services (API with built-in builder, UI, build coordinator).
3) Proxmox adapter with scoped API credentials.
4) Networking allocator (flat IP range configuration) and Nginx ingress.
5) AD auth, GitHub OAuth, and RBAC mapping.
6) Secrets store and env injection.
7) First deployment from GitHub.

## API Contracts
### Auth
- `POST /auth/login`
- `GET /auth/me`
- `GET /auth/github` (start GitHub OAuth flow)
- `GET /auth/github/callback`
- `DELETE /auth/github/link`
- `GET /auth/github/repos`

### GitHub Integration
- `POST /integrations/github/install`
- `GET /integrations/github/repos`
- `POST /integrations/github/webhook`
- `POST /projects/{id}/repo` (connect repo)
- `DELETE /projects/{id}/repo` (disconnect repo)

### Projects
- `GET /projects`
- `POST /projects`
- `GET /projects/{id}`
- `PATCH /projects/{id}`
- `DELETE /projects/{id}`

### Members
- `GET /users/search`
- `GET /projects/{id}/members`
- `POST /projects/{id}/members`
- `DELETE /projects/{id}/members/{user_id}`

### Environments
- `GET /projects/{id}/environments`
- `POST /projects/{id}/environments`
- `DELETE /projects/{id}/environments/{env_id}`

### Builds
- `GET /projects/{id}/builds`
- `GET /projects/{id}/builds/{build_id}`
- `GET /projects/{id}/builds/{build_id}/logs`
- `GET /projects/{id}/builds/{build_id}/logs/stream` (SSE)
- `POST /projects/{id}/builds`
- `POST /projects/{id}/builds/trigger`
- `POST /projects/{id}/builds/{build_id}/artifacts`
- `POST /projects/{id}/builds/{build_id}/deploy`

### Deploys
- `GET /projects/{id}/deploys`
- `POST /projects/{id}/deploys`
- `PATCH /deploys/{id}/status`
- `POST /deploys/{id}/rollback`
- `GET /projects/{id}/environments/{env_id}/queue`
- `GET /projects/{id}/deploys/{deploy_id}/logs`
- `GET /projects/{id}/deploys/{deploy_id}/logs/stream` (SSE)

### Secrets
- `GET /projects/{id}/secrets`
- `POST /projects/{id}/secrets`
- `DELETE /projects/{id}/secrets/{key}`

### Networking
- `GET /networks/vlans`
- `POST /networks/vlans/reserve`
- `GET /networks/vlans/{project_id}`
- `DELETE /networks/vlans/{project_id}`

### Admin
- `GET /admin/stats`
- `GET /admin/users`
- `GET /admin/users/{user_id}`
- `PATCH /admin/users/{user_id}/role`
- `GET /admin/quotas`
- `GET /admin/quotas/{project_id}`
- `PATCH /admin/quotas/{project_id}`
- `GET /admin/network-policies`
- `POST /admin/network-policies`
- `PATCH /admin/network-policies/{policy_id}`
- `DELETE /admin/network-policies/{policy_id}`

### Audit
- `GET /audits`

### Health
- `GET /health`
- `GET /`

## Database Schema
- `users` (id, username, display_name, email, ad_dn, created_at, github_id, github_username, github_token)
- `groups` (id, name, ad_dn)
- `group_role_map` (id, group_id, role)
- `projects` (id, name, slug, repo_url, owner_id, default_env, created_at, auto_deploy, framework, root_directory, build_command, install_command, output_directory)
- `repos` (id, project_id, provider, repo_id, install_id, repo_full_name, default_branch)
- `environments` (id, project_id, name, type, vlan_id, created_at)
- `builds` (id, project_id, commit_sha, image_ref, status, started_at, finished_at, trigger, branch, logs)
- `artifacts` (id, build_id, image_ref, sha256, size, stored_at)
- `deploys` (id, env_id, artifact_id, status, url, created_at, promoted_at, logs)
- `secrets` (id, project_id, scope, key, value_encrypted, created_at)
- `vlans` (id, vlan_tag, subnet_cidr, reserved_by_project_id)
- `quotas` (id, project_id, cpu_limit, ram_limit, disk_limit)
- `audit_log` (id, actor_user_id, action, target_type, target_id, payload, created_at)
- `network_policies` (id, project_id, name, direction, protocol, port, destination, action, enabled, created_at)
- `project_members` (id, project_id, user_id, role, created_at)

Alembic migration head: `009` (9 migrations total).

## Milestone Backlog
### M0 Foundations -- COMPLETE
- Stand up local `registry:2` with NFS storage.
- Configure Nginx ingress for `*.dev.sdc.cpp`.
- Set up Docker-in-Docker build environment inside the API container.

### M1 Control Plane MVP -- COMPLETE
- API service with AD auth, GitHub OAuth, and RBAC.
- Project and environment management.
- Audit logging pipeline.

### M2 Build and Deploy -- COMPLETE
- GitHub App + webhook receiver.
- Built-in builder with framework detection and Dockerfile generation.
- Build coordinator and deploy trigger.
- GitHub Checks reporting.

### M3 Runtime Plane -- COMPLETE
- OCI to LXC conversion using `skopeo` and `umoci`.
- Custom `/sbin/init` script injection for app startup (replaces systemd).
- Health checks and rollback.

### M4 Networking -- COMPLETE
- Flat IP allocator (primary) with VLAN allocator as fallback.
- DNS routing via wildcard `*.dev.sdc.cpp`.
- Network policies API for per-project egress/ingress rules.

### M5 Secrets and Observability -- COMPLETE
- Encrypted secrets store with env injection.
- Logs and metrics collection.

### M6 UX -- COMPLETE
- Web UI for projects, deploys, logs, and secrets.
- Staff admin views for infrastructure controls.

## Success Criteria
- Deploy time < 5 minutes for typical web apps.
- Preview environments available within 2 minutes.
- 99% of deploys do not require staff intervention.
- Clear audit trails for all deploy actions.

## Open Questions
- SLA and backup retention policy.
- Autoscaling triggers and limits.
- Kubernetes adoption timeline.

## Documentation

Detailed diagrams and workflow charts are available under `docs/`:

- [Setup Guide](docs/setup.md) — step-by-step deployment and configuration instructions
- [System Architecture](docs/architecture.md) — control and runtime planes with component map
- [Build and Deploy Flow](docs/build-deploy-flow.md) — end-to-end workflow from git push to running app
- [OCI to LXC Conversion](docs/oci-lxc-conversion.md) — toolchain, steps, init script injection, and failure modes
- [Deploy State Machine](docs/deploy-state-machine.md) — state definitions, transitions, rollback behavior, and timeouts
- [Network and DNS Layout](docs/network-dns.md) — VLAN allocation, subnet mapping, DNS routing, Nginx config, and firewall policy
- [Milestone Timeline](docs/milestones.md) — phased delivery plan with Gantt chart, tickets, and dependency graph

## Getting Started

See [Setup Guide](docs/setup.md) for step-by-step instructions covering:

1. Environment configuration (`.env` file)
2. Starting the platform (`docker compose up`)
3. GitHub App creation and installation
4. DNS setup (`*.dev.sdc.cpp`)
5. First deploy (end-to-end test)
6. Verification and troubleshooting
