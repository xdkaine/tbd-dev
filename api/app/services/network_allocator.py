"""VLAN allocator and IP reservation service.

Manages network allocation for projects:
- Auto-allocates VLANs on project creation
- Maps VLAN tags to subnets using the formula: VLAN 1000+N -> 172.16.N.0/25
- Reserves IPs per environment: .10 production, .20 staging, .100+N preview

Per docs/network-dns.md.
"""

import logging
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.environment import Environment
from app.models.network import Vlan
from app.models.project import Project
from app.services.audit import write_audit_log

logger = logging.getLogger(__name__)


# VLAN range per docs: 1001-1999 (N = 1 to 999)
VLAN_MIN = 1001
VLAN_MAX = 1999
VLAN_BASE = 1000

# Subnet template per docs
SUBNET_TEMPLATE = "172.16.{n}.0/25"
GATEWAY_TEMPLATE = "172.16.{n}.1"


class NetworkAllocationError(Exception):
    """Raised when network allocation fails."""
    pass


# ---------------------------------------------------------------------------
# VLAN allocation
# ---------------------------------------------------------------------------


def vlan_tag_to_subnet(vlan_tag: int) -> str:
    """Convert a VLAN tag to its subnet CIDR.

    Formula: VLAN tag = 1000 + N -> subnet = 172.16.N.0/25
    """
    n = vlan_tag - VLAN_BASE
    return SUBNET_TEMPLATE.format(n=n)


def vlan_tag_to_gateway(vlan_tag: int) -> str:
    """Convert a VLAN tag to its gateway IP.

    Formula: VLAN tag = 1000 + N -> gateway = 172.16.N.1
    """
    n = vlan_tag - VLAN_BASE
    return GATEWAY_TEMPLATE.format(n=n)


def subnet_to_vlan_tag(subnet_cidr: str) -> int:
    """Convert a subnet CIDR to its VLAN tag.

    Inverse of vlan_tag_to_subnet.
    """
    # Extract N from 172.16.N.0/25
    match = re.match(r"172\.16\.(\d+)\.0/25", subnet_cidr)
    if not match:
        raise ValueError(f"Invalid subnet CIDR for TBD network: {subnet_cidr}")
    n = int(match.group(1))
    return VLAN_BASE + n


async def allocate_vlan(
    db: AsyncSession,
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> Vlan:
    """Allocate the next available VLAN for a project.

    Per docs/network-dns.md allocation process:
    1. Reserve the next available VLAN tag (1001-1999)
    2. Derive subnet from the VLAN tag
    3. Register gateway and IP pool in the vlans table

    Args:
        db: Database session
        project_id: Project to allocate VLAN for
        actor_user_id: User performing the allocation

    Returns:
        The allocated Vlan record

    Raises:
        NetworkAllocationError: If allocation fails
    """
    # Check if project already has a VLAN
    existing = await db.execute(
        select(Vlan).where(Vlan.reserved_by_project_id == project_id)
    )
    existing_vlan = existing.scalar_one_or_none()
    if existing_vlan:
        logger.info(
            "Project %s already has VLAN %d", project_id, existing_vlan.vlan_tag,
        )
        return existing_vlan

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        # Find the next available VLAN tag
        max_tag_result = await db.execute(select(func.max(Vlan.vlan_tag)))
        max_tag = max_tag_result.scalar()
        next_tag = (max_tag or VLAN_BASE) + 1

        if next_tag > VLAN_MAX:
            raise NetworkAllocationError(
                f"No more VLANs available (max {VLAN_MAX - VLAN_BASE} projects)"
            )

        # Derive subnet and gateway
        subnet = vlan_tag_to_subnet(next_tag)
        gateway = vlan_tag_to_gateway(next_tag)

        # Create VLAN record in a savepoint to handle concurrent allocations
        vlan = Vlan(
            vlan_tag=next_tag,
            subnet_cidr=subnet,
            reserved_by_project_id=project_id,
        )
        db.add(vlan)
        try:
            async with db.begin_nested():
                await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            logger.warning(
                "VLAN allocation collision on tag %d (attempt %d/%d): %s",
                next_tag,
                attempt,
                max_attempts,
                exc,
            )
            continue

        logger.info(
            "Allocated VLAN %d (subnet=%s, gw=%s) for project %s",
            next_tag, subnet, gateway, project_id,
        )

        # Audit
        await write_audit_log(
            db,
            actor_user_id=actor_user_id,
            action="vlan.allocate",
            target_type="vlan",
            target_id=str(vlan.id),
            payload={
                "project_id": str(project_id),
                "vlan_tag": next_tag,
                "subnet_cidr": subnet,
                "gateway": gateway,
            },
        )

        return vlan

    raise NetworkAllocationError("Failed to allocate VLAN after multiple attempts")


async def deallocate_vlan(
    db: AsyncSession,
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> bool:
    """Deallocate a project's VLAN.

    Called when a project is deleted or VLAN needs to be freed.

    Returns True if a VLAN was deallocated, False if none was assigned.
    """
    result = await db.execute(
        select(Vlan).where(Vlan.reserved_by_project_id == project_id)
    )
    vlan = result.scalar_one_or_none()
    if vlan is None:
        return False

    vlan_tag = vlan.vlan_tag
    vlan.reserved_by_project_id = None
    await db.flush()

    logger.info("Deallocated VLAN %d from project %s", vlan_tag, project_id)

    await write_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="vlan.deallocate",
        target_type="vlan",
        target_id=str(vlan.id),
        payload={
            "project_id": str(project_id),
            "vlan_tag": vlan_tag,
        },
    )

    return True


async def get_project_vlan(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> Vlan | None:
    """Get the VLAN allocated to a project, if any."""
    result = await db.execute(
        select(Vlan).where(Vlan.reserved_by_project_id == project_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# IP reservation per environment
# ---------------------------------------------------------------------------


def get_environment_ip(
    vlan_tag: int,
    env_type: str,
    env_name: str,
) -> str:
    """Calculate the IP address for an environment within a project's VLAN.

    Per docs/network-dns.md IP assignment:
    - Production: .10
    - Staging: .20
    - Preview PR-N: .100 + N

    Args:
        vlan_tag: Project's VLAN tag (e.g. 1001)
        env_type: Environment type (production, staging, preview)
        env_name: Environment name (e.g. "production", "staging", "pr-5")

    Returns:
        IP address with CIDR notation (e.g. "172.16.1.10/25")
    """
    n = vlan_tag - VLAN_BASE

    if env_type == "production":
        host = 10
    elif env_type == "staging":
        host = 20
    elif env_type == "preview":
        # Extract PR number from env_name (e.g. "pr-5" -> 5)
        pr_match = re.match(r"pr-(\d+)", env_name)
        if pr_match:
            pr_num = int(pr_match.group(1))
            host = 100 + pr_num
            # Safety check: stay within /25 range (.2 - .126)
            if host > 126:
                logger.warning(
                    "PR number %d would exceed /25 range, capping to .126", pr_num,
                )
                host = 126
        else:
            # Fallback for non-PR preview environments
            host = 30
    else:
        # Unknown env type — use .50 range
        host = 50

    ip = f"172.16.{n}.{host}/25"
    logger.debug(
        "IP for VLAN %d env %s (%s): %s", vlan_tag, env_name, env_type, ip,
    )
    return ip


def get_gateway_for_vlan(vlan_tag: int) -> str:
    """Get the gateway IP for a VLAN."""
    return vlan_tag_to_gateway(vlan_tag)


async def resolve_deploy_network(
    db: AsyncSession,
    project_id: uuid.UUID,
    environment: Environment,
) -> tuple[Vlan | None, str | None, str | None]:
    """Resolve the full network config for a deploy.

    Returns (vlan, ip_address, gateway) or (None, None, None) if no VLAN.
    """
    vlan = await get_project_vlan(db, project_id)
    if vlan is None:
        return None, None, None

    ip_address = get_environment_ip(
        vlan.vlan_tag,
        environment.type,
        environment.name,
    )
    gateway = get_gateway_for_vlan(vlan.vlan_tag)

    return vlan, ip_address, gateway


# ---------------------------------------------------------------------------
# Auto-allocation on project create
# ---------------------------------------------------------------------------


async def auto_allocate_on_project_create(
    db: AsyncSession,
    project: Project,
    actor_user_id: uuid.UUID | None = None,
) -> Vlan:
    """Automatically allocate a VLAN when a project is created.

    This should be called from the project creation endpoint.

    Args:
        db: Database session
        project: Newly created project
        actor_user_id: User who created the project

    Returns:
        The allocated Vlan
    """
    vlan = await allocate_vlan(db, project.id, actor_user_id)

    # Link VLAN to existing production environment if present
    env_result = await db.execute(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.type == "production",
        )
    )
    prod_env = env_result.scalar_one_or_none()
    if prod_env and prod_env.vlan_id is None:
        prod_env.vlan_id = vlan.id
        await db.flush()
        logger.info(
            "Linked VLAN %d to production environment for project %s",
            vlan.vlan_tag, project.slug,
        )

    return vlan
