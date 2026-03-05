"""Bin-pack scheduler for LXC container placement.

Selects the optimal Proxmox node for a new LXC container using
a bin-packing algorithm that considers:
- Available CPU cores
- Available RAM
- Node health status
- Drain mode (excludes drained nodes)

Per docs/milestones.md M3-4: Bin-pack scheduler with node health checks and drain.
Per docs/architecture.md: "Scheduler — Bin-pack placement by CPU/RAM, node health checks, drain"
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

from app.services.proxmox_adapter import ProxmoxAdapter, get_proxmox_adapter

logger = logging.getLogger(__name__)


class NodeStatus(str, Enum):
    """Node operational status."""

    AVAILABLE = "available"
    DRAINING = "draining"  # No new containers, existing ones stay
    OFFLINE = "offline"


@dataclass
class NodeResources:
    """Resource snapshot for a Proxmox node."""

    name: str
    status: NodeStatus = NodeStatus.AVAILABLE

    # CPU
    total_cpus: int = 0
    used_cpus: float = 0.0  # Can be fractional (usage ratio * total)

    # Memory (MB)
    total_memory_mb: int = 0
    used_memory_mb: int = 0

    # Container count
    lxc_count: int = 0

    # Proxmox health
    proxmox_online: bool = True
    uptime: int = 0  # seconds

    @property
    def available_cpus(self) -> float:
        return max(0.0, self.total_cpus - self.used_cpus)

    @property
    def available_memory_mb(self) -> int:
        return max(0, self.total_memory_mb - self.used_memory_mb)

    @property
    def cpu_utilization(self) -> float:
        """CPU utilization as a ratio 0.0 - 1.0."""
        if self.total_cpus == 0:
            return 1.0
        return self.used_cpus / self.total_cpus

    @property
    def memory_utilization(self) -> float:
        """Memory utilization as a ratio 0.0 - 1.0."""
        if self.total_memory_mb == 0:
            return 1.0
        return self.used_memory_mb / self.total_memory_mb

    def can_fit(self, required_cpus: int, required_memory_mb: int) -> bool:
        """Check if this node can fit a container with the given requirements."""
        return (
            self.status == NodeStatus.AVAILABLE
            and self.proxmox_online
            and self.available_cpus >= required_cpus
            and self.available_memory_mb >= required_memory_mb
        )


@dataclass
class SchedulerConfig:
    """Configuration for the bin-pack scheduler."""

    # Weight factors for scoring (higher = more important)
    cpu_weight: float = 0.4
    memory_weight: float = 0.4
    count_weight: float = 0.2  # Prefer nodes with fewer containers

    # Safety thresholds — don't schedule if utilization exceeds these
    max_cpu_utilization: float = 0.85  # 85%
    max_memory_utilization: float = 0.90  # 90%

    # Maximum containers per node
    max_containers_per_node: int = 50


class SchedulingError(Exception):
    """Raised when no suitable node can be found."""

    def __init__(self, message: str, required_cpus: int = 0, required_memory_mb: int = 0):
        self.required_cpus = required_cpus
        self.required_memory_mb = required_memory_mb
        super().__init__(message)


# In-memory drain state (persisted across scheduler calls within the process)
_drained_nodes: set[str] = set()


def drain_node(node_name: str) -> None:
    """Mark a node as draining — no new containers will be scheduled on it."""
    _drained_nodes.add(node_name)
    logger.warning("Node '%s' marked as DRAINING", node_name)


def undrain_node(node_name: str) -> None:
    """Remove drain status from a node."""
    _drained_nodes.discard(node_name)
    logger.info("Node '%s' drain status removed", node_name)


def is_drained(node_name: str) -> bool:
    """Check if a node is in drain mode."""
    return node_name in _drained_nodes


def get_drained_nodes() -> set[str]:
    """Get the set of currently drained node names."""
    return _drained_nodes.copy()


async def discover_nodes(adapter: ProxmoxAdapter | None = None) -> list[NodeResources]:
    """Discover all Proxmox nodes and their current resource usage.

    Queries the Proxmox API for node status and resource utilization.
    Applies drain state from the in-memory store.
    """
    if adapter is None:
        adapter = get_proxmox_adapter()

    nodes_data = await adapter.list_nodes()
    resources = []

    for node_data in nodes_data:
        name = node_data.get("node", "")
        is_online = node_data.get("status", "") == "online"

        # Determine operational status
        if name in _drained_nodes:
            status = NodeStatus.DRAINING
        elif not is_online:
            status = NodeStatus.OFFLINE
        else:
            status = NodeStatus.AVAILABLE

        # Memory is in bytes from Proxmox API
        total_mem_bytes = node_data.get("maxmem", 0)
        used_mem_bytes = node_data.get("mem", 0)

        node_res = NodeResources(
            name=name,
            status=status,
            total_cpus=node_data.get("maxcpu", 0),
            used_cpus=node_data.get("cpu", 0.0) * node_data.get("maxcpu", 0),
            total_memory_mb=total_mem_bytes // (1024 * 1024),
            used_memory_mb=used_mem_bytes // (1024 * 1024),
            proxmox_online=is_online,
            uptime=node_data.get("uptime", 0),
        )

        # Get container count for this node
        if is_online:
            try:
                containers = await adapter.list_lxc_on_node(name)
                node_res.lxc_count = len(containers)
            except Exception as e:
                logger.warning("Failed to list LXCs on %s: %s", name, e)

        resources.append(node_res)

    logger.debug(
        "Discovered %d nodes: %s",
        len(resources),
        [(n.name, n.status.value, f"cpu={n.cpu_utilization:.0%}", f"mem={n.memory_utilization:.0%}")
         for n in resources],
    )

    return resources


def score_node(
    node: NodeResources,
    required_cpus: int,
    required_memory_mb: int,
    config: SchedulerConfig | None = None,
) -> float:
    """Score a node for placement. Higher score = better placement.

    Uses a weighted bin-packing algorithm that prefers nodes with
    more available resources (best-fit decreasing).

    Score components:
    - CPU headroom after placement (weighted by cpu_weight)
    - Memory headroom after placement (weighted by memory_weight)
    - Inverse container count (weighted by count_weight) — spread

    Returns 0.0 if the node cannot fit the container.
    """
    if config is None:
        config = SchedulerConfig()

    # Can't schedule on unavailable/drained/offline nodes
    if not node.can_fit(required_cpus, required_memory_mb):
        return 0.0

    # Check safety thresholds
    projected_cpu_util = (node.used_cpus + required_cpus) / max(node.total_cpus, 1)
    projected_mem_util = (node.used_memory_mb + required_memory_mb) / max(node.total_memory_mb, 1)

    if projected_cpu_util > config.max_cpu_utilization:
        return 0.0
    if projected_mem_util > config.max_memory_utilization:
        return 0.0

    # Check container count limit
    if node.lxc_count >= config.max_containers_per_node:
        return 0.0

    # Score: prefer nodes where the container fits best (bin-packing)
    # Higher remaining resources = higher score
    cpu_score = 1.0 - projected_cpu_util
    mem_score = 1.0 - projected_mem_util

    # Container spread score — prefer fewer containers
    count_score = 1.0 - (node.lxc_count / max(config.max_containers_per_node, 1))

    total_score = (
        config.cpu_weight * cpu_score
        + config.memory_weight * mem_score
        + config.count_weight * count_score
    )

    return max(0.0, total_score)


async def select_node(
    required_cpus: int,
    required_memory_mb: int,
    config: SchedulerConfig | None = None,
    adapter: ProxmoxAdapter | None = None,
    exclude_nodes: list[str] | None = None,
) -> str:
    """Select the best node for placing a new LXC container.

    Uses bin-pack scheduling to find the node with the best fit
    for the requested resources.

    Args:
        required_cpus: Number of CPU cores needed
        required_memory_mb: Amount of RAM needed (MB)
        config: Scheduler configuration (uses defaults if None)
        adapter: Proxmox adapter (uses singleton if None)
        exclude_nodes: Node names to exclude from consideration

    Returns:
        Name of the selected node

    Raises:
        SchedulingError: If no suitable node is available
    """
    if config is None:
        config = SchedulerConfig()
    if exclude_nodes is None:
        exclude_nodes = []

    # Discover current cluster state
    nodes = await discover_nodes(adapter)

    # Filter and score nodes
    candidates: list[tuple[str, float]] = []
    for node in nodes:
        if node.name in exclude_nodes:
            continue

        node_score = score_node(node, required_cpus, required_memory_mb, config)
        if node_score > 0.0:
            candidates.append((node.name, node_score))

    if not candidates:
        # Build a diagnostic message
        reasons = []
        for node in nodes:
            if node.name in exclude_nodes:
                reasons.append(f"{node.name}: excluded")
            elif node.status == NodeStatus.DRAINING:
                reasons.append(f"{node.name}: draining")
            elif node.status == NodeStatus.OFFLINE:
                reasons.append(f"{node.name}: offline")
            elif not node.can_fit(required_cpus, required_memory_mb):
                reasons.append(
                    f"{node.name}: insufficient resources "
                    f"(avail cpu={node.available_cpus:.1f}, mem={node.available_memory_mb}MB)"
                )
            else:
                reasons.append(f"{node.name}: safety threshold exceeded")

        raise SchedulingError(
            f"No suitable node found for {required_cpus} CPUs, {required_memory_mb}MB RAM. "
            f"Node status: {'; '.join(reasons)}",
            required_cpus=required_cpus,
            required_memory_mb=required_memory_mb,
        )

    # Sort by score descending, pick the best
    candidates.sort(key=lambda x: x[1], reverse=True)
    selected_node, best_score = candidates[0]

    logger.info(
        "Scheduler selected node '%s' (score=%.3f) for %d CPUs, %dMB RAM. "
        "Candidates: %s",
        selected_node,
        best_score,
        required_cpus,
        required_memory_mb,
        [(n, f"{s:.3f}") for n, s in candidates[:5]],
    )

    return selected_node


async def check_node_health(
    node_name: str,
    adapter: ProxmoxAdapter | None = None,
) -> bool:
    """Check if a Proxmox node is healthy and reachable.

    Returns True if the node is online and responding to API calls.
    """
    if adapter is None:
        adapter = get_proxmox_adapter()

    try:
        status = await adapter.get_node_status(node_name)
        # Node is healthy if Proxmox reports it
        return bool(status)
    except Exception as e:
        logger.warning("Health check failed for node '%s': %s", node_name, e)
        return False
