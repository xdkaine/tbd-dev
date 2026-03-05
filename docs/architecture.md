# System Architecture

TBD is organized into two planes: Control and Runtime. The Control Plane handles orchestration, builds, and policy. The Runtime Plane hosts LXC containers and supporting infrastructure. Each plane can be scaled independently.

## Audience
- **Developers**: understand where your code goes after you push.
- **Staff/Faculty**: understand what services run where and how to operate them.

## Mermaid Diagram

```mermaid
graph TB
    subgraph Developer
        GH[GitHub Repo]
    end

    subgraph Control Plane
        UI[Web UI]
        API[API Service]
        BUILDER[Built-in Builder]
        AUTH[Auth - AD/LDAP<br>+ GitHub OAuth]
        AUDIT[Audit Log]
        SEC[Secrets Service]
        NET[Network Allocator]
        BC[Build Coordinator]
        REG[registry:2<br>OCI Images]
    end

    subgraph Runtime Plane
        subgraph Proxmox Host A
            LXC1[LXC app-1]
            LXC2[LXC app-2]
        end
        subgraph Proxmox Host B
            LXC3[LXC app-3]
            LXC4[LXC app-4]
        end
        NFS[NFS Storage]
        NGINX[Nginx Ingress<br>*.dev.sdc.cpp]
        PROM[Prometheus]
        GRAF[Grafana]
        LOKI[Loki + Promtail]
    end

    GH -->|push/PR webhook| API
    API --> BUILDER
    BUILDER -->|clone repo, detect framework,<br>docker build + push| REG
    BUILDER -->|notify artifact ready| BC
    BC -->|pull image + convert| REG
    API -->|Proxmox API| LXC1
    API -->|Proxmox API| LXC2
    API -->|Proxmox API| LXC3
    API -->|Proxmox API| LXC4
    UI --> API
    API --> AUTH
    API --> AUDIT
    API --> SEC
    API --> NET
    NGINX -->|route traffic| LXC1
    NGINX -->|route traffic| LXC2
    NGINX -->|route traffic| LXC3
    NGINX -->|route traffic| LXC4
    NFS -.->|artifacts + volumes| LXC1
    NFS -.->|artifacts + volumes| LXC2
    NFS -.->|artifacts + volumes| LXC3
    NFS -.->|artifacts + volumes| LXC4
    PROM -.->|scrape metrics| LXC1
    PROM -.->|scrape metrics| LXC2
    PROM -.->|scrape metrics| LXC3
    PROM -.->|scrape metrics| LXC4
    PROM --> GRAF
    LOKI -.->|collect logs| LXC1
    LOKI -.->|collect logs| LXC2
    LOKI -.->|collect logs| LXC3
    LOKI -.->|collect logs| LXC4
```

## Component Responsibilities

| Component | Plane | Role |
|---|---|---|
| Web UI | Control | Dashboard for developers and admin console for staff |
| API Service | Control | Orchestration, RBAC, workflow engine |
| Built-in Builder | Control | Clones repos, detects frameworks, generates Dockerfiles, builds and pushes OCI images |
| Auth (AD + GitHub OAuth) | Control | LDAP/Kerberos authentication, GitHub OAuth account linking, group-to-role mapping |
| Audit Log | Control | Immutable record of all platform actions |
| Secrets Service | Control | Encrypted storage, scoped access, env injection |
| Network Allocator | Control | Flat IP allocation (primary) or VLAN reservation, subnet mapping, DNS registration |
| Build Coordinator | Control | Accepts artifacts, triggers deploys, manages deploy queue |
| Scheduler | Control | Bin-pack placement by CPU/RAM, node health checks, drain |
| registry:2 | Control | Local OCI image registry, NFS-backed, basic auth |
| Proxmox Hosts | Runtime | LXC container lifecycle (unprivileged, Ubuntu 22.04 base) |
| NFS Storage | Runtime | Artifacts, persistent volumes, registry data |
| Nginx Ingress | Runtime | Wildcard routing for `*.dev.sdc.cpp`, health checks, per-deploy upstream configs |
| Prometheus | Runtime | Metrics scraping from hosts and apps |
| Grafana | Runtime | Dashboards for metrics and alerting |
| Loki + Promtail | Runtime | Centralized log aggregation from LXC journald |
