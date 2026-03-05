"""Firewall rules service for project VLAN segmentation.

Manages per-project firewall rules via the Proxmox firewall API:
- Default-deny egress for all app VLANs
- Allow-list for essential platform services
- Per-project egress exceptions (approved by staff/faculty)

Per docs/network-dns.md firewall policy:
  ALLOW: Nginx ingress IP -> project VLAN (HTTP)
  ALLOW: Platform API IP -> project VLAN (health check, SSH)
  ALLOW: NFS server IP -> project VLAN (NFS)
  ALLOW: Internal DNS IP -> project VLAN (DNS)
  ALLOW: registry.sdc.cpp IP -> project VLAN (registry pull)
  DENY:  project VLAN -> other project VLANs
  DENY:  project VLAN -> internet (default)
"""

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.audit import write_audit_log
from app.services.proxmox_adapter import ProxmoxAdapter, get_proxmox_adapter

logger = logging.getLogger(__name__)


class FirewallAction(str, Enum):
    ACCEPT = "ACCEPT"
    DROP = "DROP"
    REJECT = "REJECT"


class FirewallDirection(str, Enum):
    IN = "in"
    OUT = "out"


@dataclass
class FirewallRule:
    """A single firewall rule."""

    action: FirewallAction
    direction: FirewallDirection
    source: str = ""       # CIDR or empty
    dest: str = ""         # CIDR or empty
    proto: str = ""        # tcp, udp, icmp, or empty (any)
    dport: str = ""        # Destination port or range
    sport: str = ""        # Source port or range
    comment: str = ""
    enable: bool = True

    def to_proxmox_dict(self) -> dict:
        """Convert to Proxmox firewall API parameter format."""
        rule: dict = {
            "action": self.action.value,
            "type": self.direction.value,
            "enable": 1 if self.enable else 0,
        }
        if self.source:
            rule["source"] = self.source
        if self.dest:
            rule["dest"] = self.dest
        if self.proto:
            rule["proto"] = self.proto
        if self.dport:
            rule["dport"] = self.dport
        if self.sport:
            rule["sport"] = self.sport
        if self.comment:
            rule["comment"] = self.comment
        return rule


@dataclass
class ProjectFirewallPolicy:
    """Complete firewall policy for a project's VLAN."""

    project_id: str
    project_slug: str
    vlan_subnet: str  # e.g. 172.16.1.0/25
    rules: list[FirewallRule] = field(default_factory=list)
    egress_exceptions: list[str] = field(default_factory=list)  # Approved egress CIDRs


def build_default_rules(
    vlan_subnet: str,
    project_slug: str,
) -> list[FirewallRule]:
    """Build the default firewall rules for a project VLAN.

    Per docs/network-dns.md:
    - Default-deny egress
    - Allow essential platform services inbound
    """
    rules = []

    # --- INBOUND ALLOW rules ---

    # 1. Allow Nginx ingress -> project VLAN (HTTP)
    rules.append(FirewallRule(
        action=FirewallAction.ACCEPT,
        direction=FirewallDirection.IN,
        source=settings.nginx_ingress_ip,
        dest=vlan_subnet,
        proto="tcp",
        dport="80,443",
        comment=f"[TBD] Allow Nginx ingress to {project_slug}",
    ))

    # 2. Allow Platform API -> project VLAN (health check + management)
    rules.append(FirewallRule(
        action=FirewallAction.ACCEPT,
        direction=FirewallDirection.IN,
        source=settings.platform_api_ip,
        dest=vlan_subnet,
        proto="tcp",
        comment=f"[TBD] Allow platform API to {project_slug}",
    ))

    # 3. Allow NFS server -> project VLAN
    if settings.nfs_server_ip:
        rules.append(FirewallRule(
            action=FirewallAction.ACCEPT,
            direction=FirewallDirection.IN,
            source=settings.nfs_server_ip,
            dest=vlan_subnet,
            proto="tcp",
            dport="2049",
            comment=f"[TBD] Allow NFS to {project_slug}",
        ))

    # 4. Allow internal DNS -> project VLAN
    if settings.internal_dns_ip:
        rules.append(FirewallRule(
            action=FirewallAction.ACCEPT,
            direction=FirewallDirection.IN,
            source=settings.internal_dns_ip,
            dest=vlan_subnet,
            proto="udp",
            dport="53",
            comment=f"[TBD] Allow DNS to {project_slug}",
        ))
        # Also allow TCP DNS
        rules.append(FirewallRule(
            action=FirewallAction.ACCEPT,
            direction=FirewallDirection.IN,
            source=settings.internal_dns_ip,
            dest=vlan_subnet,
            proto="tcp",
            dport="53",
            comment=f"[TBD] Allow DNS (TCP) to {project_slug}",
        ))

    # 5. Allow registry -> project VLAN (image pulls)
    if settings.registry_ip:
        rules.append(FirewallRule(
            action=FirewallAction.ACCEPT,
            direction=FirewallDirection.IN,
            source=settings.registry_ip,
            dest=vlan_subnet,
            proto="tcp",
            dport="5000",
            comment=f"[TBD] Allow registry to {project_slug}",
        ))

    # --- OUTBOUND rules ---

    # Allow outbound to essential services (DNS, NFS, registry)
    if settings.internal_dns_ip:
        rules.append(FirewallRule(
            action=FirewallAction.ACCEPT,
            direction=FirewallDirection.OUT,
            source=vlan_subnet,
            dest=settings.internal_dns_ip,
            proto="udp",
            dport="53",
            comment=f"[TBD] Allow DNS egress from {project_slug}",
        ))

    if settings.nfs_server_ip:
        rules.append(FirewallRule(
            action=FirewallAction.ACCEPT,
            direction=FirewallDirection.OUT,
            source=vlan_subnet,
            dest=settings.nfs_server_ip,
            proto="tcp",
            dport="2049",
            comment=f"[TBD] Allow NFS egress from {project_slug}",
        ))

    # Allow response traffic to Nginx (established connections)
    rules.append(FirewallRule(
        action=FirewallAction.ACCEPT,
        direction=FirewallDirection.OUT,
        source=vlan_subnet,
        dest=settings.nginx_ingress_ip,
        proto="tcp",
        comment=f"[TBD] Allow response to Nginx from {project_slug}",
    ))

    # Allow response traffic to platform API
    rules.append(FirewallRule(
        action=FirewallAction.ACCEPT,
        direction=FirewallDirection.OUT,
        source=vlan_subnet,
        dest=settings.platform_api_ip,
        proto="tcp",
        comment=f"[TBD] Allow response to API from {project_slug}",
    ))

    # --- DEFAULT DENY egress ---
    rules.append(FirewallRule(
        action=FirewallAction.DROP,
        direction=FirewallDirection.OUT,
        source=vlan_subnet,
        comment=f"[TBD] Default deny egress for {project_slug}",
    ))

    return rules


async def apply_firewall_rules(
    node: str,
    vmid: int,
    rules: list[FirewallRule],
    adapter: ProxmoxAdapter | None = None,
) -> None:
    """Apply firewall rules to an LXC container via Proxmox API.

    Sets the container firewall to enabled and adds all rules.
    """
    if adapter is None:
        adapter = get_proxmox_adapter()

    # Enable firewall on the container
    await adapter.update_lxc_config(node, vmid, {"firewall": 1})

    # Apply each rule via Proxmox firewall API
    for i, rule in enumerate(rules):
        try:
            await adapter._request(
                "POST",
                f"/api2/json/nodes/{node}/lxc/{vmid}/firewall/rules",
                data=rule.to_proxmox_dict(),
            )
            logger.debug(
                "Applied firewall rule %d/%d to LXC %d: %s %s",
                i + 1, len(rules), vmid, rule.action.value, rule.comment,
            )
        except Exception as e:
            logger.error(
                "Failed to apply firewall rule %d to LXC %d: %s",
                i + 1, vmid, e,
            )
            raise

    logger.info(
        "Applied %d firewall rules to LXC %d on %s", len(rules), vmid, node,
    )


async def setup_project_firewall(
    node: str,
    vmid: int,
    vlan_subnet: str,
    project_slug: str,
    adapter: ProxmoxAdapter | None = None,
) -> list[FirewallRule]:
    """Set up the complete default firewall policy for a project LXC.

    This is the main entry point called during deploy provisioning.

    Args:
        node: Proxmox node name
        vmid: LXC container VMID
        vlan_subnet: Project's VLAN subnet (e.g. 172.16.1.0/25)
        project_slug: Project slug for rule comments
        adapter: Proxmox adapter

    Returns:
        List of applied firewall rules
    """
    rules = build_default_rules(vlan_subnet, project_slug)
    await apply_firewall_rules(node, vmid, rules, adapter)
    return rules


async def add_egress_exception(
    db: AsyncSession,
    node: str,
    vmid: int,
    vlan_subnet: str,
    dest_cidr: str,
    proto: str = "tcp",
    dport: str = "",
    project_slug: str = "",
    reason: str = "",
    actor_user_id: uuid.UUID | None = None,
    adapter: ProxmoxAdapter | None = None,
) -> FirewallRule:
    """Add an egress exception for a project (approved by staff/faculty).

    Per docs/network-dns.md:
    - Staff or faculty can approve per-project outbound exceptions
    - All egress exceptions are recorded in the audit log

    The exception rule is inserted BEFORE the default-deny egress rule.
    """
    if adapter is None:
        adapter = get_proxmox_adapter()

    rule = FirewallRule(
        action=FirewallAction.ACCEPT,
        direction=FirewallDirection.OUT,
        source=vlan_subnet,
        dest=dest_cidr,
        proto=proto,
        dport=dport,
        comment=f"[TBD] Egress exception for {project_slug}: {reason[:80]}",
    )

    # Insert the rule (Proxmox will add it; ordering is managed by position)
    await adapter._request(
        "POST",
        f"/api2/json/nodes/{node}/lxc/{vmid}/firewall/rules",
        data=rule.to_proxmox_dict(),
    )

    logger.info(
        "Added egress exception for LXC %d: %s -> %s:%s (%s)",
        vmid, vlan_subnet, dest_cidr, dport, reason,
    )

    # Audit log
    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="firewall.egress_exception",
        target_type="lxc",
        target_id=str(vmid),
        payload={
            "project_slug": project_slug,
            "dest_cidr": dest_cidr,
            "proto": proto,
            "dport": dport,
            "reason": reason,
        },
    )

    return rule
