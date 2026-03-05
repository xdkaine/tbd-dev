"""Proxmox adapter service.

Manages LXC container lifecycle on Proxmox hosts via the REST API:
- Create unprivileged LXC containers from uploaded CT templates
- Upload CT templates (rootfs tarballs) to Proxmox storage
- Start/stop/destroy containers
- Take and restore snapshots for rollback
- Attach VLAN-tagged network interfaces
- Mount NFS volumes

Per docs/oci-lxc-conversion.md and docs/network-dns.md.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ProxmoxError(Exception):
    """Raised when a Proxmox API call fails."""

    def __init__(self, message: str, status_code: int = 0, details: str = ""):
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class LXCStatus(str, Enum):
    """LXC container status values from Proxmox."""

    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


@dataclass
class LXCSpec:
    """Specification for creating an LXC container.

    Per docs/oci-lxc-conversion.md:
    - Created from uploaded CT template (OCI rootfs tarball)
    - Simple shell init script (no systemd required)
    - App runs as root inside container (Docker convention)
    """

    hostname: str
    os_template: str  # Proxmox volume ID, e.g. "local:vztmpl/my-app.tar.gz"
    cores: int = 2
    memory: int = 512  # MB
    swap: int = 256  # MB
    disk_size: int = 10  # GB
    unprivileged: bool = False  # Docker rootfs often needs privileged

    # OS type — "unmanaged" for Docker-derived images with no standard init
    ostype: str = "unmanaged"

    # Network (per docs/network-dns.md)
    vlan_tag: int | None = None
    ip_address: str | None = None  # e.g. 172.16.1.10/25
    gateway: str | None = None  # e.g. 172.16.1.1
    bridge: str = "vmbr0"

    # NFS mount
    nfs_source: str | None = None  # e.g. /mnt/nfs/my-app
    nfs_mountpoint: str = "/data"

    # Storage backend for rootfs volume (e.g. "local-lvm", "ceph-pool")
    rootfs_storage: str = ""  # Empty = use settings.proxmox_storage

    # Proxmox resource pool (e.g. "TBD_Project") — empty = no pool
    pool: str = ""

    # Tags for identification
    tags: list[str] = field(default_factory=list)

    @property
    def net0_config(self) -> str:
        """Build the net0 configuration string for Proxmox API."""
        parts = [f"name=eth0", f"bridge={self.bridge}"]
        if self.vlan_tag:
            parts.append(f"tag={self.vlan_tag}")
        if self.ip_address:
            parts.append(f"ip={self.ip_address}")
        if self.gateway:
            parts.append(f"gw={self.gateway}")
        return ",".join(parts)


@dataclass
class LXCInfo:
    """Information about an existing LXC container."""

    vmid: int
    hostname: str
    status: LXCStatus
    node: str
    ip_address: str | None = None
    uptime: int = 0
    cpu_usage: float = 0.0
    memory_used: int = 0  # MB
    memory_max: int = 0  # MB


class ProxmoxAdapter:
    """Async client for the Proxmox VE REST API.

    Manages LXC container lifecycle. Uses httpx for async HTTP.
    Authenticates via API token (PVEAPIToken header).
    """

    def __init__(self):
        self.base_url = settings.proxmox_api_url.rstrip("/")
        self.verify_ssl = settings.proxmox_verify_ssl

        # Proxmox API token auth: PVEAPIToken=user@realm!tokenid=token-secret
        self._token_header = f"PVEAPIToken={settings.proxmox_token_id}={settings.proxmox_token_secret}"

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": self._token_header},
                verify=self.verify_ssl,
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the Proxmox API.

        Returns the 'data' field from the response JSON.
        """
        client = await self._get_client()

        try:
            response = await client.request(
                method=method,
                url=path,
                data=data,
                params=params,
            )
        except httpx.HTTPError as e:
            raise ProxmoxError(
                message=f"HTTP error communicating with Proxmox: {e}",
                details=str(e),
            )

        if response.status_code >= 400:
            body = response.text
            logger.error(
                "Proxmox API error %d on %s %s: %s",
                response.status_code, method, path, body[:1000],
            )
            raise ProxmoxError(
                message=f"Proxmox API error {response.status_code} on {method} {path}: {body[:500]}",
                status_code=response.status_code,
                details=body[:500],
            )

        result = response.json()
        return result.get("data", result)

    # ------------------------------------------------------------------
    # Node discovery
    # ------------------------------------------------------------------

    async def list_nodes(self) -> list[dict[str, Any]]:
        """List all Proxmox cluster nodes with status and resource usage.

        Returns list of dicts with keys: node, status, cpu, maxcpu, mem, maxmem, uptime
        """
        data = await self._request("GET", "/api2/json/nodes")
        return data if isinstance(data, list) else []

    async def get_node_status(self, node: str) -> dict[str, Any]:
        """Get detailed status for a specific node."""
        return await self._request("GET", f"/api2/json/nodes/{node}/status")

    # ------------------------------------------------------------------
    # LXC lifecycle
    # ------------------------------------------------------------------

    async def create_lxc(
        self,
        node: str,
        vmid: int,
        spec: LXCSpec,
    ) -> str:
        """Create an LXC container on a Proxmox node.

        Per docs/oci-lxc-conversion.md Step 4:
        POST /api2/json/nodes/{node}/lxc

        The ostemplate must reference an uploaded CT template on Proxmox
        storage (e.g. "local:vztmpl/my-app-abc123.tar.gz").

        Args:
            node: Target Proxmox node name
            vmid: VM ID to assign
            spec: LXC container specification

        Returns:
            UPID of the creation task

        Raises:
            ProxmoxError: If creation fails
        """
        # Determine rootfs storage backend
        storage = spec.rootfs_storage or settings.proxmox_storage

        payload: dict[str, Any] = {
            "vmid": vmid,
            "ostemplate": spec.os_template,
            "ostype": spec.ostype,
            "hostname": spec.hostname,
            "unprivileged": 1 if spec.unprivileged else 0,
            "cores": spec.cores,
            "memory": spec.memory,
            "swap": spec.swap,
            "net0": spec.net0_config,
            "rootfs": f"{storage}:{spec.disk_size}",
            "start": 0,  # Don't auto-start, we'll start after setup
            "onboot": 1,
        }

        # Add NFS mount if configured
        if spec.nfs_source:
            payload["mp0"] = f"{spec.nfs_source}:{spec.nfs_mountpoint},mp={spec.nfs_mountpoint}"

        # Add tags for identification
        if spec.tags:
            payload["tags"] = ";".join(spec.tags)

        # Add to Proxmox resource pool if configured
        if spec.pool:
            payload["pool"] = spec.pool

        logger.info(
            "Creating LXC %d on node %s: hostname=%s, ostemplate=%s, "
            "rootfs=%s, cores=%d, mem=%dMB, net=%s",
            vmid, node, spec.hostname, spec.os_template,
            payload["rootfs"], spec.cores, spec.memory, spec.net0_config,
        )
        logger.debug("LXC create payload: %s", payload)

        result = await self._request(
            "POST",
            f"/api2/json/nodes/{node}/lxc",
            data=payload,
        )

        # Proxmox returns a UPID (task ID) for async operations
        upid = result if isinstance(result, str) else str(result)
        logger.info("LXC %d creation task started: %s", vmid, upid)
        return upid

    async def start_lxc(self, node: str, vmid: int) -> str:
        """Start an LXC container.

        POST /api2/json/nodes/{node}/lxc/{vmid}/status/start
        """
        logger.info("Starting LXC %d on node %s", vmid, node)
        result = await self._request(
            "POST",
            f"/api2/json/nodes/{node}/lxc/{vmid}/status/start",
        )
        return str(result) if result else ""

    async def stop_lxc(self, node: str, vmid: int) -> str:
        """Stop an LXC container."""
        logger.info("Stopping LXC %d on node %s", vmid, node)
        result = await self._request(
            "POST",
            f"/api2/json/nodes/{node}/lxc/{vmid}/status/stop",
        )
        return str(result) if result else ""

    async def destroy_lxc(self, node: str, vmid: int, purge: bool = True) -> str:
        """Destroy an LXC container.

        DELETE /api2/json/nodes/{node}/lxc/{vmid}
        """
        logger.warning("Destroying LXC %d on node %s (purge=%s)", vmid, node, purge)
        params = {"purge": 1} if purge else {}
        result = await self._request(
            "DELETE",
            f"/api2/json/nodes/{node}/lxc/{vmid}",
            params=params,
        )
        return str(result) if result else ""

    async def get_lxc_status(self, node: str, vmid: int) -> LXCInfo:
        """Get the current status of an LXC container."""
        data = await self._request(
            "GET",
            f"/api2/json/nodes/{node}/lxc/{vmid}/status/current",
        )

        status_str = data.get("status", "unknown")
        try:
            lxc_status = LXCStatus(status_str)
        except ValueError:
            lxc_status = LXCStatus.UNKNOWN

        return LXCInfo(
            vmid=vmid,
            hostname=data.get("name", ""),
            status=lxc_status,
            node=node,
            uptime=data.get("uptime", 0),
            cpu_usage=data.get("cpu", 0.0),
            memory_used=data.get("mem", 0) // (1024 * 1024),
            memory_max=data.get("maxmem", 0) // (1024 * 1024),
        )

    async def get_lxc_config(self, node: str, vmid: int) -> dict[str, Any]:
        """Get the full configuration of an LXC container."""
        return await self._request(
            "GET",
            f"/api2/json/nodes/{node}/lxc/{vmid}/config",
        )

    async def update_lxc_config(
        self,
        node: str,
        vmid: int,
        config: dict[str, Any],
    ) -> None:
        """Update LXC container configuration.

        PUT /api2/json/nodes/{node}/lxc/{vmid}/config
        """
        await self._request(
            "PUT",
            f"/api2/json/nodes/{node}/lxc/{vmid}/config",
            data=config,
        )
        logger.info("Updated config for LXC %d on %s: %s", vmid, node, list(config.keys()))

    # ------------------------------------------------------------------
    # Snapshots (for rollback)
    # ------------------------------------------------------------------

    async def create_snapshot(
        self,
        node: str,
        vmid: int,
        snap_name: str,
        description: str = "",
    ) -> str:
        """Create a snapshot of an LXC container for rollback.

        Per docs/deploy-state-machine.md:
        Snapshot is taken before deploy for rollback safety.
        """
        logger.info("Creating snapshot '%s' for LXC %d on %s", snap_name, vmid, node)
        result = await self._request(
            "POST",
            f"/api2/json/nodes/{node}/lxc/{vmid}/snapshot",
            data={
                "snapname": snap_name,
                "description": description or f"TBD platform snapshot: {snap_name}",
            },
        )
        return str(result) if result else ""

    async def rollback_snapshot(
        self,
        node: str,
        vmid: int,
        snap_name: str,
    ) -> str:
        """Rollback an LXC container to a previous snapshot.

        Per docs/deploy-state-machine.md:
        Proxmox adapter restores the pre-deploy LXC snapshot.
        """
        logger.warning(
            "Rolling back LXC %d on %s to snapshot '%s'", vmid, node, snap_name,
        )
        result = await self._request(
            "POST",
            f"/api2/json/nodes/{node}/lxc/{vmid}/snapshot/{snap_name}/rollback",
        )
        return str(result) if result else ""

    async def delete_snapshot(
        self,
        node: str,
        vmid: int,
        snap_name: str,
    ) -> str:
        """Delete a snapshot."""
        result = await self._request(
            "DELETE",
            f"/api2/json/nodes/{node}/lxc/{vmid}/snapshot/{snap_name}",
        )
        return str(result) if result else ""

    async def list_snapshots(
        self,
        node: str,
        vmid: int,
    ) -> list[dict[str, Any]]:
        """List all snapshots for an LXC container."""
        data = await self._request(
            "GET",
            f"/api2/json/nodes/{node}/lxc/{vmid}/snapshot",
        )
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Exec (for setup commands inside LXC)
    # ------------------------------------------------------------------

    async def exec_in_lxc(
        self,
        node: str,
        vmid: int,
        command: list[str],
    ) -> dict[str, Any]:
        """Execute a command inside a running LXC container via Proxmox API.

        Uses the lxc/exec endpoint for running setup scripts.
        """
        logger.debug("Exec in LXC %d: %s", vmid, " ".join(command))
        return await self._request(
            "POST",
            f"/api2/json/nodes/{node}/lxc/{vmid}/status/exec",
            data={"command": " ".join(command)},
        )

    # ------------------------------------------------------------------
    # Template upload
    # ------------------------------------------------------------------

    async def upload_template(
        self,
        node: str,
        tarball_path: Path,
        storage: str = "",
        filename: str = "",
    ) -> str:
        """Upload a CT template tarball to a Proxmox node's storage.

        Uses POST /api2/json/nodes/{node}/storage/{storage}/upload
        with multipart/form-data to upload the .tar.gz file.

        Proxmox stores it under /var/lib/vz/template/cache/ (for 'local'
        storage) and makes it available as {storage}:vztmpl/{filename}.

        Args:
            node: Target Proxmox node name
            tarball_path: Local path to the .tar.gz template file
            storage: Proxmox storage name (default: settings.proxmox_template_storage)
            filename: Override filename (default: use tarball_path.name)

        Returns:
            UPID of the upload task

        Raises:
            ProxmoxError: If upload fails
        """
        storage = storage or settings.proxmox_template_storage
        filename = filename or tarball_path.name

        logger.info(
            "Uploading CT template to node %s, storage %s: %s (%.1f MB)",
            node, storage, filename,
            tarball_path.stat().st_size / (1024 * 1024),
        )

        client = await self._get_client()

        # Proxmox upload endpoint requires multipart with:
        # - content: "vztmpl" (content type identifier)
        # - filename: the file data
        upload_url = f"/api2/json/nodes/{node}/storage/{storage}/upload"

        try:
            with open(tarball_path, "rb") as f:
                response = await client.post(
                    upload_url,
                    data={"content": "vztmpl"},
                    files={"filename": (filename, f, "application/gzip")},
                    timeout=httpx.Timeout(300.0, connect=30.0),  # 5 min for large uploads
                )
        except httpx.HTTPError as e:
            raise ProxmoxError(
                message=f"HTTP error uploading template to {node}: {e}",
                details=str(e),
            )

        if response.status_code >= 400:
            body = response.text
            logger.error(
                "Template upload error %d on %s: %s",
                response.status_code, upload_url, body[:1000],
            )
            raise ProxmoxError(
                message=f"Template upload failed ({response.status_code}): {body[:500]}",
                status_code=response.status_code,
                details=body[:500],
            )

        result = response.json()
        upid = result.get("data", "")
        if isinstance(upid, str):
            logger.info("Template upload task started: %s", upid[:60])
        else:
            upid = str(upid)

        return upid

    def get_template_volume_id(
        self,
        filename: str,
        storage: str = "",
    ) -> str:
        """Build the Proxmox volume ID for an uploaded template.

        After upload, templates are referenced as:
            {storage}:vztmpl/{filename}

        Args:
            filename: Template filename (e.g. "my-app-abc123.tar.gz")
            storage: Storage name (default: settings.proxmox_template_storage)

        Returns:
            Volume ID string (e.g. "local:vztmpl/my-app-abc123.tar.gz")
        """
        storage = storage or settings.proxmox_template_storage
        return f"{storage}:vztmpl/{filename}"

    # ------------------------------------------------------------------
    # VMID allocation
    # ------------------------------------------------------------------

    async def get_next_vmid(self) -> int:
        """Get the next available VMID from the Proxmox cluster.

        GET /api2/json/cluster/nextid
        """
        data = await self._request("GET", "/api2/json/cluster/nextid")
        return int(data) if data else 100

    async def list_lxc_on_node(self, node: str) -> list[dict[str, Any]]:
        """List all LXC containers on a specific node.

        Returns list of dicts with: vmid, name, status, maxmem, maxdisk, cpus, etc.
        """
        data = await self._request("GET", f"/api2/json/nodes/{node}/lxc")
        return data if isinstance(data, list) else []

    async def list_all_tbd_containers(self) -> list[dict[str, Any]]:
        """List all TBD-tagged LXC containers across all cluster nodes.

        Scans every node for containers with a 'tbd' tag and returns their
        configs (including net0 for IP extraction).

        Returns:
            List of dicts with keys: vmid, node, name, tags, net0, status
        """
        nodes = await self.list_nodes()
        results: list[dict[str, Any]] = []

        for node_info in nodes:
            node_name = node_info.get("node", "")
            if not node_name or node_info.get("status") != "online":
                continue

            try:
                containers = await self.list_lxc_on_node(node_name)
            except ProxmoxError:
                logger.warning("Failed to list containers on node %s", node_name)
                continue

            for ct in containers:
                tags = ct.get("tags", "")
                # Proxmox uses ';' as tag separator
                tag_list = [t.strip() for t in tags.split(";")] if tags else []
                if "tbd" in tag_list:
                    # Fetch config to get net0 (has IP info)
                    vmid = ct.get("vmid")
                    try:
                        config = await self.get_lxc_config(node_name, vmid)
                        ct["_config_net0"] = config.get("net0", "")
                    except ProxmoxError:
                        ct["_config_net0"] = ""
                    ct["node"] = node_name
                    ct["_tag_list"] = tag_list
                    results.append(ct)

        logger.info("Found %d TBD containers across cluster", len(results))
        return results

    # ------------------------------------------------------------------
    # Task tracking
    # ------------------------------------------------------------------

    @staticmethod
    def parse_upid_node(upid: str) -> str | None:
        """Extract the node name from a Proxmox UPID string.

        UPID format: UPID:{node}:{pid}:{pstart}:{starttime}:{type}:{id}:{user}:
        Example: UPID:gonk:00106D1D:2170691D:69A8A69E:imgcopy::uma@pve!uma-ejmis:

        Returns:
            Node name if parseable, None otherwise.
        """
        if not upid or not upid.startswith("UPID:"):
            return None
        parts = upid.split(":")
        if len(parts) >= 2:
            return parts[1]
        return None

    async def wait_for_task(
        self,
        node: str,
        upid: str,
        timeout: float = 180.0,
        poll_interval: float = 2.0,
    ) -> bool:
        """Wait for a Proxmox task to complete.

        Args:
            node: Node where the task is running (fallback — overridden
                  by the node embedded in the UPID if present)
            upid: Task UPID
            timeout: Maximum wait time in seconds (default 3 min per docs)
            poll_interval: How often to check status

        Returns:
            True if task succeeded, False if it failed

        Raises:
            TimeoutError: If task doesn't complete within timeout
        """
        # The UPID encodes the actual node that owns the task.  Proxmox
        # may redirect storage uploads to a different node than the one
        # we targeted, so always prefer the node from the UPID.
        upid_node = self.parse_upid_node(upid)
        if upid_node and upid_node != node:
            logger.info(
                "UPID node (%s) differs from requested node (%s); "
                "polling on %s",
                upid_node, node, upid_node,
            )
            node = upid_node

        elapsed = 0.0
        while elapsed < timeout:
            data = await self._request(
                "GET",
                f"/api2/json/nodes/{node}/tasks/{upid}/status",
            )

            status = data.get("status", "")
            if status == "stopped":
                exit_status = data.get("exitstatus", "")
                if exit_status == "OK":
                    logger.info("Task %s completed successfully", upid[:40])
                    return True
                else:
                    logger.error("Task %s failed: %s", upid[:40], exit_status)
                    return False

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Proxmox task {upid[:40]} timed out after {timeout}s")


# Module-level singleton
_adapter: ProxmoxAdapter | None = None


def get_proxmox_adapter() -> ProxmoxAdapter:
    """Get the singleton ProxmoxAdapter instance."""
    global _adapter
    if _adapter is None:
        _adapter = ProxmoxAdapter()
    return _adapter
