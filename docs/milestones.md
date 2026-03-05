# Milestone Timeline

Phased delivery plan for TBD, from foundations through Kubernetes adoption.

## Audience
- **Developers**: understand when features become available.
- **Staff/Faculty**: understand infrastructure work, dependencies, and capacity planning.

## ASCII Timeline

```
 Week   1    2    3    4    5    6    7    8    9   10   11   12   13   14
       |----|----|----|----|----|----|----|----|----|----|----|----|----|----|
  M0   [==========]
  M1              [===============]
  M2                        [===============]
  M3                                  [===============]
  M4                                            [==========]
  M5                                                  [==========]
  M6                                                        [===============]

  M0: Foundations (registry, runners, Nginx)
  M1: Control Plane MVP (API, auth, RBAC, projects)
  M2: Build & Deploy (GitHub App, coordinator, checks)
  M3: Runtime Plane (OCI→LXC, systemd, health checks)
  M4: Networking (VLAN allocator, DNS registration)
  M5: Secrets & Observability (encrypted store, logs, metrics)
  M6: UX (Web UI for developers and staff)
```

## Mermaid Gantt Chart

```mermaid
gantt
    title TBD Platform - MVP Delivery Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  Week %W

    section M0 Foundations
    Stand up registry:2 on NFS           :m0a, 2026-03-09, 3d
    Registry basic auth + GC policy      :m0a2, after m0a, 2d
    Configure Nginx ingress *.sdc.cpp    :m0b, after m0a, 3d
    Provision self-hosted Actions runners :m0c, after m0a, 4d
    Validate end-to-end connectivity     :m0d, after m0c, 2d

    section M1 Control Plane MVP
    API service scaffold + AD auth       :m1a, after m0d, 5d
    RBAC middleware (group-to-role)       :m1b, after m1a, 3d
    Project and environment CRUD         :m1c, after m1a, 4d
    Audit logging pipeline               :m1d, after m1b, 3d

    section M2 Build and Deploy
    GitHub App + webhook receiver        :m2a, after m1c, 4d
    Build coordinator (artifact intake)  :m2b, after m2a, 4d
    GitHub Checks status reporting       :m2c, after m2b, 3d
    Deploy trigger and queue             :m2d, after m2b, 3d

    section M3 Runtime Plane
    Ubuntu 22.04 LXC base template       :m3pre, after m2d, 2d
    OCI pull + rootfs unpack pipeline    :m3a, after m3pre, 5d
    systemd unit generation              :m3b, after m3a, 3d
    LXC provisioning via Proxmox API     :m3c, after m3b, 4d
    Bin-pack scheduler + node health     :m3s, after m3c, 3d
    Health checks + auto-rollback        :m3d, after m3c, 3d

    section M4 Networking
    VLAN allocator + subnet mapping      :m4a, after m3c, 4d
    IP reservation per environment       :m4b, after m4a, 3d
    DNS registration under *.sdc.cpp     :m4c, after m4b, 3d
    Default-deny egress + exception flow :m4d, after m4b, 3d

    section M5 Secrets and Observability
    Encrypted secrets store              :m5a, after m4b, 4d
    Env var injection into LXC           :m5b, after m5a, 3d
    Log collection pipeline              :m5c, after m5a, 4d
    Metrics collection + dashboards      :m5d, after m5c, 3d

    section M6 UX
    Developer dashboard (projects, deploys) :m6a, after m5b, 5d
    Deploy logs and status viewer           :m6b, after m6a, 4d
    Secrets and env var management UI       :m6c, after m6a, 4d
    Staff admin console                     :m6d, after m6b, 5d
```

## Milestone Details

### M0: Foundations (Weeks 1-2)
**Goal**: infrastructure prerequisites are operational.

| Ticket | Description | Depends On | Est |
|--------|-------------|-----------|-----|
| M0-1 | Deploy `registry:2` container with NFS-backed storage | NFS share | 3d |
| M0-2 | Configure basic auth (htpasswd) and weekly GC for registry | M0-1 | 2d |
| M0-3 | Configure Nginx for wildcard `*.sdc.cpp` | DNS record | 3d |
| M0-4 | Install and register self-hosted Actions runners | VPN access | 4d |
| M0-5 | Validate: push image to registry, pull from runner | M0-1, M0-4 | 2d |

**Exit criteria**: Actions runner can build an image, push to registry with auth, and Nginx resolves `*.sdc.cpp`.

---

### M1: Control Plane MVP (Weeks 2-4)
**Goal**: API service handles auth, projects, and audit.

| Ticket | Description | Depends On | Est |
|--------|-------------|-----------|-----|
| M1-1 | API scaffold with AD/LDAP authentication | AD endpoint | 5d |
| M1-2 | RBAC middleware with group-to-role mapping | M1-1 | 3d |
| M1-3 | Project and environment CRUD endpoints | M1-1 | 4d |
| M1-4 | Audit log writes on all mutations | M1-2 | 3d |

**Exit criteria**: authenticated user can create a project and see audit records.

---

### M2: Build and Deploy (Weeks 4-6)
**Goal**: GitHub integration triggers builds and reports status.

| Ticket | Description | Depends On | Est |
|--------|-------------|-----------|-----|
| M2-1 | GitHub App registration + webhook endpoint | M1-3 | 4d |
| M2-2 | Build coordinator: accept image_ref, create deploy record | M2-1 | 4d |
| M2-3 | Post commit status checks to GitHub | M2-2 | 3d |
| M2-4 | Deploy queue with ordering and concurrency limits | M2-2 | 3d |

**Exit criteria**: push to connected repo triggers a build record and GitHub shows pending/success checks.

---

### M3: Runtime Plane (Weeks 6-8)
**Goal**: OCI images are converted and running as LXC containers.

| Ticket | Description | Depends On | Est |
|--------|-------------|-----------|-----|
| M3-0 | Prepare Ubuntu 22.04 LXC base template (unprivileged, systemd) | Proxmox access | 2d |
| M3-1 | OCI pull (skopeo) + rootfs unpack (umoci) pipeline | M0-1, M2-2 | 5d |
| M3-2 | systemd unit generation from OCI config | M3-1 | 3d |
| M3-3 | LXC create/update via Proxmox API (unprivileged) | M3-2 | 4d |
| M3-4 | Bin-pack scheduler with node health checks and drain | M3-3 | 3d |
| M3-5 | HTTP health check + auto-rollback on failure | M3-3 | 3d |

**Exit criteria**: push to repo results in an unprivileged LXC container placed by the scheduler that passes health check.

---

### M4: Networking (Weeks 8-10)
**Goal**: projects get isolated VLANs and routable DNS.

| Ticket | Description | Depends On | Est |
|--------|-------------|-----------|-----|
| M4-1 | VLAN allocator with tag-to-subnet mapping | M1-3 | 4d |
| M4-2 | IP reservation per environment | M4-1 | 3d |
| M4-3 | DNS registration + Nginx upstream update | M4-2, M0-3 | 3d |
| M4-4 | Default-deny egress rules + per-project exception flow | M4-2 | 3d |

**Exit criteria**: new project gets a VLAN, preview env gets a routable URL, egress is blocked by default.

---

### M5: Secrets and Observability (Weeks 9-11)
**Goal**: secrets are secure and logs/metrics are collected.

| Ticket | Description | Depends On | Est |
|--------|-------------|-----------|-----|
| M5-1 | Encrypted secrets store (DB + encryption layer) | M1-3 | 4d |
| M5-2 | Env var injection into LXC at deploy time | M5-1, M3-3 | 3d |
| M5-3 | Log forwarding from LXC journald to aggregator | M3-3 | 4d |
| M5-4 | Metrics collection + Grafana dashboards | M5-3 | 3d |

**Exit criteria**: secrets injected, logs searchable, metrics visible in dashboard.

---

### M6: UX (Weeks 11-14)
**Goal**: developers and staff have a usable web interface.

| Ticket | Description | Depends On | Est |
|--------|-------------|-----------|-----|
| M6-1 | Developer dashboard: project list, deploy history | M1-3, M2-2 | 5d |
| M6-2 | Deploy log viewer and status page | M6-1, M5-3 | 4d |
| M6-3 | Secrets and env var management UI | M6-1, M5-1 | 4d |
| M6-4 | Staff admin console: quotas, VLANs, audit viewer | M6-1, M4-1 | 5d |

**Exit criteria**: developer can deploy an app and view logs entirely through the UI.

---

## Dependency Graph (Mermaid)

```mermaid
graph LR
    M0[M0 Foundations] --> M1[M1 Control Plane]
    M1 --> M2[M2 Build & Deploy]
    M2 --> M3[M3 Runtime Plane]
    M3 --> M4[M4 Networking]
    M3 --> M5[M5 Secrets & Obs]
    M4 --> M6[M6 UX]
    M5 --> M6
```

## Future Phases (post-MVP)

| Phase | Focus | Estimated Start |
|-------|-------|----------------|
| v1.1 | Autoscaling, blue/green deploys | Week 15 |
| v1.2 | Build cache, image retention policies | Week 18 |
| v2.0 | Kubernetes runtime plane on Proxmox VMs | Week 22+ |
