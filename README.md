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
- Segmented networking per project with VLAN-backed isolation.
- AD-only authentication and auditable access.
- Clear operational workflows for staff oversight.

## Non-goals (v1)
- Public, internet-facing PaaS at scale.
- Multi-region disaster recovery.
- Kubernetes-first runtime (planned later).
- Commercial billing or multi-tenant public onboarding.

## Feature Scope
### MVP (LXC-first)
- Repo connection via GitHub App/webhooks.
- GitHub Actions-first build pipeline with artifact upload and commit status checks.
- Self-hosted Actions runners inside the VPN.
- Preview environments per PR and production deploys per main branch.
- Per-project network segmentation and VLAN allocation.
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
TBD uses three planes to keep the platform maintainable and secure:

1) Control Plane
- Web UI + API
- Auth/RBAC + audit
- Project, env, and policy management
- Proxmox adapter + network allocator

2) Build Plane
- GitHub Actions runners (self-hosted) triggered by webhooks
- Build artifact storage (NFS)
- Status reporting to GitHub Checks

3) Runtime Plane (v1)
- LXC containers on Proxmox
- Per-env VLAN tagging
- NFS-backed volumes for persistent data

### Component Map (v1)
- Web UI: developer-facing dashboard and staff/admin console
- API Service: orchestration, policies, and workflow engine
- Proxmox Adapter: LXC lifecycle, snapshots, and resource allocation
- Build Coordinator: accepts GitHub Actions artifacts and triggers deploys
- Network Service: VLAN allocation and subnet mapping
- Secrets Service: encrypted env vars and scoped access
- Ingress/DNS Service: routes app traffic and manages wildcard records
- Observability Stack: logs, metrics, and audit trails

## Proxmox Integration (LXC First)
- Workloads run as LXC containers on Proxmox hosts.
- Proxmox API manages container lifecycle, snapshots, and resource limits.
- Each environment is mapped to a VLAN for network segmentation.
- Fast provisioning enables preview environments per PR.

## Repository Integration and Deploy Flow
GitHub is the primary integration point in v1.

1) Developer connects GitHub repo.
2) Webhook triggers GitHub Actions on push/PR.
3) Actions runner builds via buildpacks or Dockerfile.
4) Artifact is uploaded to the platform using a short-lived token.
5) Platform posts build and deploy status back to GitHub.
6) LXC is provisioned or updated.
7) Deploy is promoted on successful health checks.

## Build and Deploy Strategy (Actions-first)
- GitHub App installs webhooks and checks on connected repos.
- Self-hosted Actions runners run inside the VPN with access to NFS and Proxmox.
- Buildpacks are the default using `pack` with a standard builder image.
- OCI images are pushed to an internal registry and tagged by commit SHA.
- Platform pulls OCI images, unpacks to LXC rootfs, and deploys with systemd units.
- Platform validates the artifact, deploys to LXC, and publishes preview URLs.

### Example GitHub Actions Workflow (MVP)
```yaml
name: TBD Deploy

on:
  push:
    branches: [main]
  pull_request:

jobs:
  build-and-deploy:
    runs-on: [self-hosted, tbd-runner]
    steps:
      - uses: actions/checkout@v4
      - name: Build OCI image with buildpacks
        run: |
          pack build "$IMAGE" --builder paketobuildpacks/builder:base
      - name: Push image to internal registry
        run: |
          docker push "$IMAGE"
      - name: Trigger TBD deploy
        run: |
          curl -X POST "$TBD_API/deploys" \
            -H "Authorization: Bearer $TBD_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"project":"my-app","env":"preview","image":"'"$IMAGE"'"}'
```

Environment variables used by the workflow:
- `IMAGE` (e.g., `registry.sdc.cpp/tbd/my-app:${{ github.sha }}`)
- `TBD_API` (platform API URL inside the VPN)
- `TBD_TOKEN` (short-lived deploy token)

## Runtime Packaging Strategy
- Default to buildpacks with auto-detection for common stacks.
- Optional Dockerfile builds for advanced or custom needs.
- Runtime contract: bind to `$PORT`, emit logs to stdout/stderr, and expose a `/health` endpoint.
- Secrets are injected as environment variables at runtime.
- Artifact format is OCI image stored in the internal registry.

## OCI to LXC Conversion (v1)
- Actions builds OCI images and pushes to the internal registry.
- Platform pulls images, unpacks to a rootfs using OCI tools, and wires a systemd unit.
- LXC containers boot from the unpacked rootfs and start the app service.

### OCI to LXC Runbook (Design)
1) Pull image from registry using `skopeo` to an OCI layout.
2) Unpack OCI layout to rootfs with `umoci`.
3) Create/update LXC container with the rootfs path.
4) Generate systemd unit to run the app command.
5) Inject env vars, mount volumes, and apply VLAN tagging.
6) Run `/health` checks and promote or rollback.

## Networking Model
Network segmentation is per-project and VLAN-backed.

### Example
- VLAN 1001 -> 172.16.1.0/25
- VLAN 1025 -> 172.16.25.0/25

Rules:
- Each project gets a dedicated VLAN.
- Environments (preview/staging/prod) live inside the project VLAN.
- Routing and upstream CIDR are controlled by infrastructure staff.

## DNS and Routing
- Wildcard domain `*.sdc.cpp` points to the platform ingress inside the VPN.
- Preview environments use `pr-<num>.<project>.sdc.cpp`.
- Production uses `<project>.sdc.cpp`.

## Authentication and Authorization
- AD-only authentication via LDAP/Kerberos.
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
- VLAN segmentation per project.
- Secrets encrypted at rest and injected at runtime.
- RBAC enforced at API and UI layers.

## Operations
- Backups: scheduled backups of platform metadata and NFS volumes.
- Upgrades: rolling upgrades of control and build planes.
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
- Default deny: app VLANs cannot reach the internet or other VLANs by default.
- Per-project exceptions: staff/faculty can approve outbound internet access per project.
- Allowed by default: NFS, internal DNS, platform API, and registry traffic.

## Technical Design Appendix (v1 LXC)
### Services
- Web UI for developers and staff.
- API Service for orchestration and policy enforcement.
- Proxmox Adapter for LXC lifecycle and resource controls.
- Build Coordinator for artifact intake and deploy triggering.
- Network Allocator for VLAN/subnet mapping and IP reservation.
- Secrets Service for encrypted storage and scoped access.
- Ingress/DNS Service for `*.sdc.cpp` routing.
- Observability Stack for logs, metrics, and auditing.

### Data Model (core)
- users, groups, group_role_map
- projects, repos, environments
- builds, artifacts, deploys
- secrets, vlans, quotas
- audit_log

### Core APIs (examples)
- `POST /integrations/github/install`
- `POST /webhooks/github`
- `GET/POST /projects`
- `GET/POST /projects/{id}/environments`
- `POST /projects/{id}/deploys`
- `POST /projects/{id}/secrets`
- `POST /deploys/{id}/rollback`
- `GET /networks/vlans`
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
- Attach VLAN-tagged NICs per environment.
- Mount NFS volumes and inject environment variables.
- Generate systemd units for app startup and health checks.
- Snapshot before deploy and rollback on failure.
- Gate promotion on health checks.

### Network Allocator
- Map VLAN to subnet based on staff-defined rules.
- Reserve VLANs per project and allocate IPs per environment.
- Register DNS entries under `*.sdc.cpp`.

### Security Model
- AD-only authentication with group-to-role mapping.
- API tokens scoped to project and environment.
- Secrets encrypted at rest with audited access.
- Full audit log for deploys, config changes, and admin actions.

### Observability
- Centralized logs per project and environment.
- Metrics for CPU/RAM/IO and request latency.
- Build and deploy timing dashboards.

### Operations
- Backups for metadata DB and NFS volumes.
- Rolling upgrades for control and build planes.
- Quotas and alerts for capacity planning.

## Implementation Guide (Design-Only)
### Prerequisites
- Proxmox cluster reachable from the control plane.
- NFS share for artifacts and persistent volumes.
- Internal DNS with wildcard `*.sdc.cpp`.
- AD/LDAP endpoints and group mappings.

### Bootstrap Order
1) Local OCI registry (`registry:2`) with NFS-backed storage.
2) Self-hosted GitHub Actions runners inside the VPN.
3) Control plane services (API, UI, build coordinator).
4) Proxmox adapter with scoped API credentials.
5) Networking allocator and Nginx ingress.
6) AD auth and RBAC mapping.
7) Secrets store and env injection.
8) First deployment from GitHub.

## API Contracts (Design-Only)
### Auth
- `POST /auth/login`
- `GET /auth/me`

### GitHub Integration
- `POST /integrations/github/install`
- `POST /webhooks/github`

### Projects
- `GET /projects`
- `POST /projects`
- `GET /projects/{id}`
- `PATCH /projects/{id}`

### Environments
- `GET /projects/{id}/environments`
- `POST /projects/{id}/environments`

### Builds
- `POST /projects/{id}/builds`
- `GET /projects/{id}/builds`

### Deploys
- `POST /projects/{id}/deploys`
- `GET /projects/{id}/deploys`
- `POST /deploys/{id}/rollback`

### Artifacts
- `POST /artifacts`
- `GET /artifacts/{id}`

### Secrets
- `GET /projects/{id}/secrets`
- `POST /projects/{id}/secrets`
- `DELETE /projects/{id}/secrets/{key}`

### Networking
- `GET /networks/vlans`
- `POST /networks/vlans/reserve`

### Audit
- `GET /audits`

## Database Schema (Design-Only)
- `users` (id, username, display_name, email, ad_dn, created_at)
- `groups` (id, name, ad_dn)
- `group_role_map` (id, group_id, role)
- `projects` (id, name, slug, repo_url, owner_id, default_env, created_at)
- `repos` (id, project_id, provider, repo_id, install_id)
- `environments` (id, project_id, name, type, vlan_id, created_at)
- `builds` (id, project_id, commit_sha, image_ref, status, started_at, finished_at)
- `artifacts` (id, build_id, image_ref, sha256, size, stored_at)
- `deploys` (id, env_id, artifact_id, status, url, created_at, promoted_at)
- `secrets` (id, project_id, scope, key, value_encrypted, created_at)
- `vlans` (id, vlan_tag, subnet_cidr, reserved_by_project_id)
- `quotas` (id, project_id, cpu_limit, ram_limit, disk_limit)
- `audit_log` (id, actor_user_id, action, target_type, target_id, payload, created_at)

## Milestone Backlog
### M0 Foundations
- Stand up local `registry:2` with NFS storage.
- Configure Nginx ingress for `*.sdc.cpp`.
- Provision self-hosted GitHub Actions runners.

### M1 Control Plane MVP
- API service with AD auth and RBAC.
- Project and environment management.
- Audit logging pipeline.

### M2 Build and Deploy
- GitHub App + webhook receiver.
- Build coordinator and deploy trigger.
- GitHub Checks reporting.

### M3 Runtime Plane
- OCI to LXC conversion using `skopeo` and `umoci`.
- systemd unit generation for app startup.
- Health checks and rollback.

### M4 Networking
- VLAN allocator with subnet mapping.
- DNS registration under `*.sdc.cpp`.

### M5 Secrets and Observability
- Encrypted secrets store with env injection.
- Logs and metrics collection.

### M6 UX
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
- [System Architecture](docs/architecture.md) — control, build, and runtime planes with component map
- [Build and Deploy Flow](docs/build-deploy-flow.md) — end-to-end workflow from git push to running app
- [OCI to LXC Conversion](docs/oci-lxc-conversion.md) — toolchain, steps, systemd unit template, and failure modes
- [Deploy State Machine](docs/deploy-state-machine.md) — state definitions, transitions, rollback behavior, and timeouts
- [Network and DNS Layout](docs/network-dns.md) — VLAN allocation, subnet mapping, DNS routing, Nginx config, and firewall policy
- [Milestone Timeline](docs/milestones.md) — phased delivery plan with Gantt chart, tickets, and dependency graph

## Getting Started

See [Setup Guide](docs/setup.md) for step-by-step instructions covering:

1. Environment configuration (`.env` file)
2. Starting the platform (`docker compose up`)
3. GitHub App creation and installation
4. DNS setup (`*.sdc.cpp`)
5. First deploy (end-to-end test)
6. Self-hosted Actions runners
7. Verification and troubleshooting
