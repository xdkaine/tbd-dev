"""Deploy executor — orchestrates the full deploy pipeline.

Ties together all M3-M5 services into the end-to-end flow:

 1. Transition deploy: artifact_ready -> provisioning
 2. Resolve network — flat IP from configurable range (or VLAN fallback)
 3. OCI pull (skopeo) + unpack (umoci) + extract config
 4. Install init script into rootfs (replaces systemd — Docker images have no init)
 5. Inject secrets from DB into rootfs /etc/tbd/secrets.env
 6. Create Proxmox CT template tarball from prepared rootfs
 7. Scheduler selects target Proxmox node (bin-pack)
 8. Upload CT template to target Proxmox node
 9. Get VMID and build LXC spec (bridge, pool, tags from settings)
10. Proxmox adapter: snapshot existing LXC (if update), create LXC from template
11. Start LXC container
12. (Firewall — temporarily skipped)
13. Health check: HTTP GET /health (5 retries, 10s interval, 60s timeout)
14. Register DNS routing (Nginx upstream config + reload)
15. On success: transition provisioning -> healthy -> active
16. On failure: auto-rollback to snapshot, transition -> failed

Per docs/build-deploy-flow.md, docs/deploy-state-machine.md, docs/oci-lxc-conversion.md.
"""

import asyncio
import ipaddress
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.build import Artifact, Build
from app.models.deploy import Deploy
from app.models.environment import Environment
from app.models.network import Vlan
from app.models.project import Project
from app.services.build_coordinator import transition_deploy
from app.services.dns_routing import (
    DNSRoutingError,
    register_deploy_routing,
    register_production_routing,
)
from app.services.health_check import HealthCheckConfig, check_health
from app.services.network_allocator import resolve_deploy_network
from app.services.oci_converter import (
    OCIConversionError,
    cleanup_conversion,
    convert_image,
    create_template_tarball,
)
from app.services.proxmox_adapter import (
    LXCSpec,
    ProxmoxAdapter,
    ProxmoxError,
    get_proxmox_adapter,
)
from app.services.scheduler import SchedulingError, select_node
from app.services.secrets_injector import SecretsInjectionError, inject_secrets
from app.services.systemd_generator import (
    SystemdUnitParams,
    install_unit_to_rootfs,
)

logger = logging.getLogger(__name__)


class DeployExecutionError(Exception):
    """Raised when the deploy execution pipeline fails."""

    def __init__(self, stage: str, message: str, deploy_id: uuid.UUID | None = None):
        self.stage = stage
        self.deploy_id = deploy_id
        super().__init__(f"Deploy execution failed at {stage}: {message}")


@dataclass
class DeployContext:
    """Context for a deploy execution — carries all state through the pipeline."""

    # Core records
    deploy: Deploy
    artifact: Artifact
    build: Build
    project: Project
    environment: Environment

    # Network info (from M4 VLAN allocator)
    vlan: Vlan | None = None
    ip_address: str | None = None
    gateway: str | None = None
    port: int = 3000

    # Proxmox placement
    target_node: str | None = None
    vmid: int | None = None
    snapshot_name: str | None = None

    # Previous container info (for rollback)
    existing_vmid: int | None = None
    existing_node: str | None = None

    @property
    def tag(self) -> str:
        """Unique tag for this deploy (used for OCI layout/rootfs naming)."""
        return f"{self.project.slug}-{str(self.deploy.id)[:8]}"

    @property
    def hostname(self) -> str:
        """LXC hostname for this deploy."""
        return f"{self.project.slug}-{self.environment.name}"

    @property
    def env_type(self) -> str:
        """Environment type (production, staging, preview)."""
        return self.environment.type or "production"

    @property
    def template_filename(self) -> str:
        """Filename for the CT template tarball on Proxmox."""
        return f"tbd-{self.tag}.tar.gz"


# ---------------------------------------------------------------------------
# Flat IP allocation (temporary — bypasses VLAN system)
# ---------------------------------------------------------------------------

# Serialises flat IP allocation so two concurrent deploys never
# pick the same free IP (classic TOCTOU prevention).
_ip_allocation_lock = asyncio.Lock()


def _use_flat_ip() -> bool:
    """Check whether flat IP allocation is configured."""
    return bool(settings.deploy_ip_start and settings.deploy_ip_end)


def _parse_ip_range() -> tuple[ipaddress.IPv4Address, ipaddress.IPv4Address]:
    """Parse the configured flat IP range."""
    start = ipaddress.IPv4Address(settings.deploy_ip_start)
    end = ipaddress.IPv4Address(settings.deploy_ip_end)
    if start > end:
        raise DeployExecutionError(
            stage="network",
            message=f"deploy_ip_start ({start}) > deploy_ip_end ({end})",
        )
    return start, end


def _extract_ips_from_net0(net0: str) -> list[str]:
    """Extract IP addresses from a Proxmox net0 config string.

    net0 format: "name=eth0,bridge=Critical,ip=10.128.30.80/24,gw=10.128.30.1"
    """
    ips: list[str] = []
    for part in net0.split(","):
        part = part.strip()
        if part.startswith("ip="):
            ip_str = part[3:]
            # Strip CIDR suffix
            if "/" in ip_str:
                ip_str = ip_str.split("/")[0]
            if ip_str and ip_str != "dhcp":
                ips.append(ip_str)
    return ips


async def _allocate_flat_ip(adapter: ProxmoxAdapter, db: AsyncSession) -> tuple[str, str]:
    """Allocate the next free IP from the flat range.

    Uses both the database (authoritative source of truth for claimed IPs)
    and a Proxmox scan (belt-and-suspenders for containers that predate
    the DB tracking columns) to build the set of used IPs.

    Returns:
        (ip_with_cidr, gateway) — e.g. ("10.128.30.80/24", "10.128.30.1")

    Raises:
        DeployExecutionError: If no free IPs remain
    """
    start, end = _parse_ip_range()
    gateway = settings.deploy_gateway
    subnet_bits = settings.deploy_subnet_bits

    # Collect IPs already in use by TBD containers
    used_ips: set[str] = set()

    # Source 1: Database — IPs claimed by non-terminal deploys.
    # This is the primary source of truth and closes the TOCTOU gap.
    try:
        db_result = await db.execute(
            select(Deploy.container_ip).where(
                Deploy.container_ip.isnot(None),
                Deploy.status.notin_(["superseded", "rolled_back", "failed"]),
            )
        )
        for (ip,) in db_result:
            used_ips.add(ip)
    except Exception as e:
        logger.warning(
            "Failed to query DB for IP dedup (proceeding with Proxmox scan only): %s", e,
        )

    # Source 2: Proxmox runtime scan — catches containers that predate
    # the DB tracking columns or were created outside the platform.
    try:
        tbd_containers = await adapter.list_all_tbd_containers()
        for ct in tbd_containers:
            net0 = ct.get("_config_net0", "")
            for ip_str in _extract_ips_from_net0(net0):
                used_ips.add(ip_str)
    except ProxmoxError as e:
        logger.warning(
            "Failed to scan existing containers for IP dedup (proceeding): %s", e,
        )

    logger.info(
        "Flat IP allocation: range %s–%s, %d IPs already in use: %s",
        start, end, len(used_ips), used_ips,
    )

    # Walk the range and pick the first free IP
    current = start
    while current <= end:
        candidate = str(current)
        if candidate not in used_ips:
            ip_cidr = f"{candidate}/{subnet_bits}"
            logger.info("Allocated flat IP: %s (gateway %s)", ip_cidr, gateway)
            return ip_cidr, gateway
        current = ipaddress.IPv4Address(int(current) + 1)

    raise DeployExecutionError(
        stage="network",
        message=f"No free IPs in range {start}–{end} ({len(used_ips)} in use)",
    )


async def execute_deploy(
    db: AsyncSession,
    ctx: DeployContext,
) -> Deploy:
    """Execute the full deploy pipeline.

    This is the main entry point called by the build coordinator when a
    deploy transitions from artifact_ready to provisioning.

    Orchestrates: network -> OCI conversion -> init script -> secrets ->
                  tarball -> scheduler -> upload -> create LXC ->
                  health check -> firewall -> DNS -> promote

    Args:
        db: Database session
        ctx: Deploy context with all required records

    Returns:
        Updated Deploy record (either active or failed)
    """
    deploy_id = ctx.deploy.id
    logger.info(
        "Starting deploy execution for %s (project=%s, env=%s, artifact=%s)",
        deploy_id, ctx.project.slug, ctx.environment.name, ctx.artifact.image_ref,
    )

    adapter = get_proxmox_adapter()

    # --- Log accumulation (mirrors builder.py pattern) ---
    from datetime import datetime, timezone

    log_lines: list[str] = []

    def log(msg: str):
        logger.info("[deploy %s] %s", str(deploy_id)[:8], msg)
        log_lines.append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}")

    async def flush_logs():
        """Write current log_lines to the DB so the SSE endpoint returns live data."""
        ctx.deploy.logs = "\n".join(log_lines)
        await db.flush()

    log(f"Starting deploy for {ctx.project.slug} / {ctx.environment.name}")
    log(f"Artifact: {ctx.artifact.image_ref}")
    await flush_logs()

    try:
        # ---------------------------------------------------------------
        # Step 1: Transition to provisioning
        # Walk through intermediate states if needed (the deploy queue
        # may have already promoted queued -> building).
        # ---------------------------------------------------------------
        log("Step 1: Transitioning to provisioning...")
        current = ctx.deploy.status
        if current in ("queued", "building", "artifact_ready"):
            # Step through each intermediate state to reach provisioning
            steps = ["building", "artifact_ready", "provisioning"]
            for target in steps:
                if ctx.deploy.can_transition_to(target):
                    ctx.deploy = await transition_deploy(
                        db, deploy_id, target,
                        "Artifact ready" if target == "artifact_ready" else "OCI conversion starting",
                    )
        elif current != "provisioning":
            raise DeployExecutionError(
                stage="transition",
                message=f"Deploy in unexpected state: {current}",
                deploy_id=deploy_id,
            )
        await db.commit()
        log("Transitioned to provisioning")
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 2: Resolve network (flat IP or VLAN fallback)
        # ---------------------------------------------------------------
        log("Step 2: Resolving network configuration...")
        logger.info("[%s] Step 2: Resolving network config", deploy_id)

        if _use_flat_ip():
            # Flat IP mode — bypass VLAN system entirely.
            # Lock serialises allocation so two concurrent deploys
            # never scan the same set of used IPs and pick the same
            # free address (TOCTOU prevention).
            log(f"Using flat IP allocation (range {settings.deploy_ip_start}–{settings.deploy_ip_end})")
            logger.info("[%s] Using flat IP allocation (range %s–%s)",
                        deploy_id, settings.deploy_ip_start, settings.deploy_ip_end)
            async with _ip_allocation_lock:
                ctx.ip_address, ctx.gateway = await _allocate_flat_ip(adapter, db)
            ctx.vlan = None  # No VLAN in flat mode
            log(f"Network resolved: IP {ctx.ip_address}, gateway {ctx.gateway}")

            # Persist IP claim to DB immediately so the next allocation
            # (even within the same process) sees this IP as used.
            bare_ip = ctx.ip_address.split("/")[0] if "/" in ctx.ip_address else ctx.ip_address
            ctx.deploy.container_ip = bare_ip
            await db.flush()
            await db.commit()
            log(f"IP {bare_ip} claimed in database")

            logger.info(
                "[%s] Flat network resolved: IP %s, GW %s",
                deploy_id, ctx.ip_address, ctx.gateway,
            )
        else:
            # Legacy VLAN mode
            log("Using VLAN allocation...")
            vlan, ip_address, gateway = await resolve_deploy_network(
                db, ctx.project.id, ctx.environment,
            )
            ctx.vlan = vlan
            ctx.ip_address = ip_address
            ctx.gateway = gateway

            if vlan:
                log(f"Network resolved: VLAN {vlan.vlan_tag}, IP {ip_address}, gateway {gateway}")
                logger.info(
                    "[%s] Network resolved: VLAN %d, IP %s, GW %s",
                    deploy_id, vlan.vlan_tag, ip_address, gateway,
                )
            else:
                log("WARNING: No VLAN allocated — deploying without network")
                logger.warning(
                    "[%s] No VLAN allocated for project %s — deploying without network",
                    deploy_id, ctx.project.slug,
                )
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 3: OCI pull + unpack + extract config
        # ---------------------------------------------------------------
        log(f"Step 3: OCI pull + unpack for {ctx.artifact.image_ref}...")
        logger.info("[%s] Step 3: OCI conversion for %s", deploy_id, ctx.artifact.image_ref)
        try:
            rootfs_path, oci_config = await convert_image(
                image_ref=ctx.artifact.image_ref,
                tag=ctx.tag,
            )
        except OCIConversionError as e:
            log(f"ERROR: OCI conversion failed: {e}")
            await flush_logs()
            raise DeployExecutionError(
                stage=e.stage,
                message=str(e),
                deploy_id=deploy_id,
            )

        ctx.port = oci_config.primary_port
        log(f"OCI conversion complete (port={ctx.port})")

        # Persist container port to DB now that we know it
        ctx.deploy.container_port = ctx.port
        await db.flush()

        await flush_logs()

        # ---------------------------------------------------------------
        # Step 4: Install init script into rootfs
        # Docker images have no init system (no systemd, no OpenRC).
        # We inject a simple /sbin/init shell script that sets up env
        # and exec's the app command as PID 1.
        # ---------------------------------------------------------------
        log("Step 4: Installing init script into rootfs...")
        logger.info("[%s] Step 4: Installing init script into rootfs", deploy_id)
        init_params = SystemdUnitParams(
            project_name=ctx.project.name,
            project_slug=ctx.project.slug,
            env_name=ctx.environment.name,
            env_type=ctx.env_type,
            oci_config=oci_config,
            ip_address=ctx.ip_address or "",
            gateway=ctx.gateway or "",
        )
        install_unit_to_rootfs(rootfs_path, init_params)
        log("Init script installed")
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 5: Inject secrets into rootfs
        # ---------------------------------------------------------------
        log("Step 5: Injecting secrets into rootfs...")
        logger.info("[%s] Step 5: Injecting secrets into rootfs", deploy_id)
        try:
            await inject_secrets(
                db, rootfs_path, ctx.project.id, ctx.env_type,
            )
            log("Secrets injected successfully")
        except SecretsInjectionError as e:
            # Secrets injection failure is non-fatal — deploy can continue
            # with empty secrets.env (the file exists from init generator)
            log(f"WARNING: Secrets injection failed (non-fatal): {e}")
            logger.warning(
                "[%s] Secrets injection failed (non-fatal): %s", deploy_id, e,
            )
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 6: Create CT template tarball from prepared rootfs
        # This packages the rootfs (with init script + secrets) into a
        # .tar.gz that Proxmox can use as an ostemplate for LXC creation.
        # ---------------------------------------------------------------
        log("Step 6: Creating CT template tarball...")
        logger.info("[%s] Step 6: Creating CT template tarball", deploy_id)
        try:
            tarball_path = await create_template_tarball(rootfs_path, ctx.tag)
        except OCIConversionError as e:
            log(f"ERROR: Template tarball creation failed: {e}")
            await flush_logs()
            raise DeployExecutionError(
                stage="template_tarball",
                message=str(e),
                deploy_id=deploy_id,
            )
        log("Template tarball created")
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 7: Select target node (bin-pack scheduler)
        # Must happen BEFORE upload so we know which node to upload to.
        # ---------------------------------------------------------------
        log("Step 7: Selecting target Proxmox node...")
        logger.info("[%s] Step 7: Scheduling — selecting target node", deploy_id)
        try:
            # Get resource requirements from project quota or defaults.
            # Defaults must match the Quota model: cpu=2, ram=2048MB, disk=10240MB.
            required_cpus = 2
            required_memory_mb = 2048
            required_disk_mb = 10240
            if ctx.project.quota:
                required_cpus = ctx.project.quota.cpu_limit
                required_memory_mb = ctx.project.quota.ram_limit
                required_disk_mb = ctx.project.quota.disk_limit

            ctx.target_node = await select_node(
                required_cpus=required_cpus,
                required_memory_mb=required_memory_mb,
                adapter=adapter,
            )
        except SchedulingError as e:
            log(f"ERROR: Scheduling failed: {e}")
            await flush_logs()
            raise DeployExecutionError(
                stage="scheduling",
                message=str(e),
                deploy_id=deploy_id,
            )
        log(f"Selected node: {ctx.target_node}")
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 8: Upload CT template to target Proxmox node
        # ---------------------------------------------------------------
        log(f"Step 8: Uploading CT template to node {ctx.target_node}...")
        logger.info(
            "[%s] Step 8: Uploading CT template to node %s",
            deploy_id, ctx.target_node,
        )
        try:
            upload_upid = await adapter.upload_template(
                node=ctx.target_node,
                tarball_path=tarball_path,
                filename=ctx.template_filename,
            )
            # Wait for upload to complete
            if upload_upid:
                upload_success = await adapter.wait_for_task(
                    ctx.target_node, upload_upid, timeout=300.0,
                )
                if not upload_success:
                    raise ProxmoxError("Template upload task failed")
        except ProxmoxError as e:
            log(f"ERROR: Template upload failed: {e}")
            await flush_logs()
            raise DeployExecutionError(
                stage="template_upload",
                message=str(e),
                deploy_id=deploy_id,
            )

        # Build the volume ID for the uploaded template
        template_volume_id = adapter.get_template_volume_id(ctx.template_filename)
        log(f"Template uploaded: {template_volume_id}")
        logger.info(
            "[%s] Template uploaded: %s", deploy_id, template_volume_id,
        )
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 9: Get VMID and build LXC spec
        # ---------------------------------------------------------------
        log(f"Step 9: Building LXC spec on node {ctx.target_node}...")
        logger.info("[%s] Step 9: Building LXC spec on node %s", deploy_id, ctx.target_node)
        ctx.vmid = await adapter.get_next_vmid()
        log(f"VMID allocated: {ctx.vmid}")

        # Determine bridge — use configured bridge (e.g. "Critical") or default
        bridge = settings.proxmox_bridge or "vmbr0"

        # Build LXC specification — using uploaded template as ostemplate
        # disk_size is in GB; quota stores disk_limit in MB, so convert.
        required_disk_gb = max(1, required_disk_mb // 1024)
        lxc_spec = LXCSpec(
            hostname=ctx.hostname,
            os_template=template_volume_id,
            cores=required_cpus,
            memory=required_memory_mb,
            disk_size=required_disk_gb,
            bridge=bridge,
            tags=["tbd"],
        )

        # Apply resource pool if configured
        if settings.proxmox_pool:
            lxc_spec.pool = settings.proxmox_pool

        # Apply network config
        if _use_flat_ip() and ctx.ip_address:
            # Flat IP mode — no VLAN tag, use flat IP and gateway directly
            lxc_spec.ip_address = ctx.ip_address
            lxc_spec.gateway = ctx.gateway
        elif ctx.vlan:
            # Legacy VLAN mode
            n = ctx.vlan.vlan_tag - 1000
            lxc_spec.vlan_tag = ctx.vlan.vlan_tag
            lxc_spec.ip_address = ctx.ip_address
            lxc_spec.gateway = f"172.16.{n}.1"

        logger.info(
            "[%s] LXC spec: VMID %d, hostname=%s, template=%s, cores=%d, mem=%dMB, disk=%dGB",
            deploy_id, ctx.vmid, ctx.hostname, template_volume_id,
            required_cpus, required_memory_mb, required_disk_gb,
        )
        log(f"LXC spec ready: hostname={ctx.hostname}, cores={required_cpus}, mem={required_memory_mb}MB, disk={required_disk_gb}GB")
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 10: Create LXC container via Proxmox API
        #
        # IMPORTANT: We keep the existing container alive until the new
        # one passes health checks. This ensures we can rollback by
        # simply restarting the old container instead of relying on
        # snapshots that get destroyed with their parent container.
        # ---------------------------------------------------------------
        log("Step 10: Creating LXC container...")
        logger.info("[%s] Step 10: Creating LXC container", deploy_id)
        try:
            # Discover existing container (if any) for rollback purposes.
            # We do NOT destroy it yet — it stays alive until the new one
            # passes health checks.
            try:
                existing_containers = await adapter.list_lxc_on_node(ctx.target_node)
                existing = [
                    c for c in existing_containers
                    if c.get("name") == ctx.hostname
                ]
                if existing:
                    ctx.existing_vmid = existing[0].get("vmid")
                    ctx.existing_node = ctx.target_node
                    log(f"Found existing LXC {ctx.existing_vmid} — will replace after health check")
                    logger.info(
                        "[%s] Existing LXC %s found on %s — keeping for rollback",
                        deploy_id, ctx.existing_vmid, ctx.target_node,
                    )
            except ProxmoxError:
                # No existing container, that's fine
                pass

            # Create new container from uploaded template (new VMID)
            upid = await adapter.create_lxc(ctx.target_node, ctx.vmid, lxc_spec)

            # Wait for creation to complete (3 min timeout per docs)
            success = await adapter.wait_for_task(
                ctx.target_node, upid, timeout=180.0,
            )
            if not success:
                raise ProxmoxError("LXC creation task failed")

        except ProxmoxError as e:
            log(f"ERROR: LXC creation failed: {e}")
            await flush_logs()
            raise DeployExecutionError(
                stage="lxc_create",
                message=str(e),
                deploy_id=deploy_id,
            )
        log(f"LXC container {ctx.vmid} created on {ctx.target_node}")

        # Persist VMID and node to DB for teardown and reconciliation
        ctx.deploy.container_vmid = ctx.vmid
        ctx.deploy.container_node = ctx.target_node
        await db.flush()
        await db.commit()

        await flush_logs()

        # ---------------------------------------------------------------
        # Step 11: Start LXC container
        # ---------------------------------------------------------------
        log(f"Step 11: Starting LXC {ctx.vmid}...")
        logger.info("[%s] Step 11: Starting LXC %d", deploy_id, ctx.vmid)
        try:
            start_upid = await adapter.start_lxc(ctx.target_node, ctx.vmid)
            if start_upid:
                await adapter.wait_for_task(
                    ctx.target_node, start_upid, timeout=60.0,
                )
        except ProxmoxError as e:
            log(f"ERROR: LXC start failed: {e}")
            await flush_logs()
            raise DeployExecutionError(
                stage="lxc_start",
                message=str(e),
                deploy_id=deploy_id,
            )
        log(f"LXC {ctx.vmid} started")
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 12: Firewall (TEMPORARILY SKIPPED)
        # Firewall setup is skipped while using flat IP allocation.
        # The previous VLAN-based firewall had Proxmox schema errors
        # and is not applicable to the flat 10.128.30.x network.
        # ---------------------------------------------------------------
        log("Step 12: Firewall — skipped (flat IP mode)")
        logger.info(
            "[%s] Step 12: Firewall — SKIPPED (flat IP / temporary)",
            deploy_id,
        )
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 13: Health check
        # ---------------------------------------------------------------
        log("Step 13: Running health check...")
        logger.info("[%s] Step 13: Health check", deploy_id)
        health_ip = ctx.ip_address
        if health_ip and "/" in health_ip:
            health_ip = health_ip.split("/")[0]  # Strip CIDR notation

        if health_ip:
            log(f"Health check target: {health_ip}:{ctx.port}")
            await flush_logs()

            # Use per-project health check overrides if configured
            hc_path = ctx.project.health_check_path or "/"
            hc_timeout = float(ctx.project.health_check_timeout or 60)
            health_config = HealthCheckConfig(
                max_retries=5,
                retry_interval=10.0,
                total_timeout=hc_timeout,
                initial_delay=5.0,
                health_path=hc_path,
            )
            if hc_path != "/" or hc_timeout != 60.0:
                log(f"Custom health check: path={hc_path}, timeout={hc_timeout}s")
            health_result = await check_health(health_ip, ctx.port, health_config)

            if not health_result.passed:
                # Auto-rollback: destroy the new (failed) container and
                # restart the old one if it exists.
                log(f"ERROR: Health check FAILED after {health_result.attempts} attempts: {health_result.last_error}")
                logger.warning(
                    "[%s] Health check FAILED: %s (attempts=%d, elapsed=%.1fs)",
                    deploy_id, health_result.last_error,
                    health_result.attempts, health_result.total_elapsed,
                )

                # Destroy the failed new container
                if ctx.vmid and ctx.target_node:
                    log("Destroying failed container...")
                    try:
                        stop_upid = await adapter.stop_lxc(ctx.target_node, ctx.vmid)
                        if stop_upid:
                            await adapter.wait_for_task(ctx.target_node, stop_upid, timeout=60.0)
                        destroy_upid = await adapter.destroy_lxc(ctx.target_node, ctx.vmid)
                        if destroy_upid:
                            await adapter.wait_for_task(ctx.target_node, destroy_upid, timeout=60.0)
                        log(f"Destroyed failed LXC {ctx.vmid}")
                        ctx.vmid = None  # Mark as destroyed so error handler doesn't retry
                    except ProxmoxError as e:
                        log(f"WARNING: Failed to destroy new container: {e}")
                        logger.error("[%s] Failed to destroy new container %s: %s", deploy_id, ctx.vmid, e)

                # Restart the old container (the real rollback)
                if ctx.existing_vmid and ctx.existing_node:
                    log(f"Rolling back — restarting previous LXC {ctx.existing_vmid}...")
                    try:
                        start_upid = await adapter.start_lxc(ctx.existing_node, ctx.existing_vmid)
                        if start_upid:
                            await adapter.wait_for_task(ctx.existing_node, start_upid, timeout=60.0)
                        log(f"Previous LXC {ctx.existing_vmid} restarted successfully")
                    except ProxmoxError as e:
                        log(f"ERROR: Rollback failed — could not restart previous container: {e}")
                        logger.error("[%s] Rollback failed: %s", deploy_id, e)
                else:
                    log("No previous container to rollback to")

                await flush_logs()
                raise DeployExecutionError(
                    stage="health_check",
                    message=(
                        f"Health check failed after {health_result.attempts} attempts: "
                        f"{health_result.last_error}"
                    ),
                    deploy_id=deploy_id,
                )
            log(f"Health check passed ({health_result.attempts} attempt(s), {health_result.total_elapsed:.1f}s)")
        else:
            log("WARNING: No IP address for health check — skipping")
            logger.warning(
                "[%s] No IP address for health check — skipping (VLAN not yet allocated)",
                deploy_id,
            )
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 14: Promote — healthy -> active
        # ---------------------------------------------------------------
        log("Step 14: Promoting deploy to healthy...")
        logger.info("[%s] Step 14: Promoting deploy to healthy", deploy_id)
        ctx.deploy = await transition_deploy(
            db, deploy_id, "healthy", "Health check passed",
        )
        await db.commit()

        log("Promoting deploy to active...")
        logger.info("[%s] Promoting deploy to active", deploy_id)
        ctx.deploy = await transition_deploy(
            db, deploy_id, "active", "Deploy active, serving traffic",
        )
        await db.commit()
        log("Deploy promoted to active")
        await flush_logs()

        # ---------------------------------------------------------------
        # Step 14b: Clean up old container after successful promotion
        # Now that the new container is active, we can safely stop the
        # previous one. Instead of always destroying, we leave it
        # stopped so users can inspect or restart it — unless the
        # per-project container limit is exceeded (handled by the
        # transition_deploy -> supersede path in build_coordinator).
        # ---------------------------------------------------------------
        if ctx.existing_vmid and ctx.existing_node:
            log(f"Step 14b: Stopping old LXC {ctx.existing_vmid}...")
            logger.info(
                "[%s] Step 14b: Stopping old container %s on %s",
                deploy_id, ctx.existing_vmid, ctx.existing_node,
            )
            try:
                stop_upid = await adapter.stop_lxc(ctx.existing_node, ctx.existing_vmid)
                if stop_upid:
                    await adapter.wait_for_task(ctx.existing_node, stop_upid, timeout=60.0)
                log(f"Old LXC {ctx.existing_vmid} stopped")
            except ProxmoxError as e:
                # Non-fatal — old container may already be stopped
                log(f"WARNING: Failed to stop old container {ctx.existing_vmid}: {e}")
                logger.warning(
                    "[%s] Failed to stop old container %s: %s",
                    deploy_id, ctx.existing_vmid, e,
                )
            await flush_logs()

        # ---------------------------------------------------------------
        # Step 15: Register DNS routing (Nginx upstream + reload)
        # ---------------------------------------------------------------
        if health_ip and ctx.port:
            log("Step 15: Registering DNS routing...")
            logger.info("[%s] Step 15: Registering DNS routing", deploy_id)
            try:
                owner_username = ctx.project.owner.username if ctx.project.owner else "unknown"
                await register_deploy_routing(
                    deploy_id=str(deploy_id),
                    owner_username=owner_username,
                    backend_ip=health_ip,
                    backend_port=ctx.port,
                )
                log("DNS routing registered (immutable deploy URL)")

                # Also register/update the persistent production URL.
                # This overwrites the previous production config so that
                # <slug>-<username>.dev.sdc.cpp seamlessly switches to
                # the new backend container.
                #
                # RACE GUARD: If two deploys for the same project finish
                # near-simultaneously, the older deploy could overwrite
                # the newer deploy's production URL.  We check that this
                # deploy is still the current active deploy before writing.
                from app.utils.dns import production_url as build_production_url
                try:
                    # Re-check: is this deploy still the active one?
                    newest_active = (await db.execute(
                        select(Deploy)
                        .where(
                            Deploy.env_id == ctx.deploy.env_id,
                            Deploy.status == "active",
                        )
                        .order_by(Deploy.promoted_at.desc())
                        .limit(1)
                    )).scalar_one_or_none()

                    if newest_active and newest_active.id != deploy_id:
                        log(
                            f"Skipping production URL update — newer deploy "
                            f"{newest_active.id} is already active"
                        )
                    else:
                        await register_production_routing(
                            project_slug=ctx.project.slug,
                            owner_username=owner_username,
                            backend_ip=health_ip,
                            backend_port=ctx.port,
                            deploy_id=str(deploy_id),
                        )
                        prod_url = build_production_url(ctx.project.slug, owner_username)
                        ctx.project.production_url = prod_url
                        await db.flush()
                        log(f"Production URL updated: {prod_url}")
                except Exception as e:
                    log(f"WARNING: Production URL registration failed: {e}")
                    logger.warning("[%s] Production URL registration failed: %s", deploy_id, e)
            except DNSRoutingError as e:
                # DNS routing failure is non-fatal at this point — deploy is
                # already active, traffic just won't route yet
                log(f"WARNING: DNS routing registration failed: {e}")
                logger.error(
                    "[%s] DNS routing registration failed: %s", deploy_id, e,
                )
        else:
            log("Step 15: Skipping DNS routing — no IP or port")
            logger.warning(
                "[%s] Skipping DNS routing — no IP or port", deploy_id,
            )

        log("Deploy completed successfully!")
        log(f"LXC {ctx.vmid} on {ctx.target_node} (url={ctx.deploy.url})")
        await flush_logs()

        logger.info(
            "Deploy %s completed successfully: LXC %d on %s (url=%s)",
            deploy_id, ctx.vmid, ctx.target_node, ctx.deploy.url,
        )

        # Send webhook notification (fire-and-forget)
        if ctx.project.webhook_url:
            from app.services.notifications import send_deploy_notification
            await send_deploy_notification(
                ctx.project.webhook_url,
                project_slug=ctx.project.slug,
                deploy_id=str(deploy_id),
                deploy_url=ctx.deploy.url,
                status="active",
                message="Deploy completed successfully",
                node=ctx.target_node,
                vmid=ctx.vmid,
            )

        return ctx.deploy

    except DeployExecutionError as e:
        # Mark deploy as failed
        log(f"FAILED at stage '{e.stage}': {e}")
        logger.error("Deploy %s failed at stage '%s': %s", deploy_id, e.stage, e)

        # Destroy container if it was created but the deploy failed
        # (the health_check handler already destroys on its own failure
        # path and clears ctx.vmid, so this only fires for other stages)
        if ctx.vmid and ctx.target_node:
            log(f"Cleaning up: destroying failed LXC {ctx.vmid}...")
            try:
                stop_upid = await adapter.stop_lxc(ctx.target_node, ctx.vmid)
                if stop_upid:
                    await adapter.wait_for_task(ctx.target_node, stop_upid, timeout=60.0)
                destroy_upid = await adapter.destroy_lxc(ctx.target_node, ctx.vmid)
                if destroy_upid:
                    await adapter.wait_for_task(ctx.target_node, destroy_upid, timeout=60.0)
                log(f"Destroyed orphaned LXC {ctx.vmid}")
            except ProxmoxError as cleanup_err:
                log(f"WARNING: Failed to destroy orphaned container {ctx.vmid}: {cleanup_err}")
                logger.error("[%s] Failed to destroy orphaned container %s: %s", deploy_id, ctx.vmid, cleanup_err)

        try:
            # Clear container tracking columns so the IP/VMID are freed
            ctx.deploy.container_ip = None
            ctx.deploy.container_port = None
            ctx.deploy.container_vmid = None
            ctx.deploy.container_node = None

            await flush_logs()
            ctx.deploy = await transition_deploy(
                db, deploy_id, "failed", f"Failed at {e.stage}: {str(e)[:200]}",
            )
            await db.commit()
        except Exception as transition_err:
            logger.error(
                "Failed to transition deploy %s to failed: %s",
                deploy_id, transition_err,
            )

        # Send failure webhook notification (fire-and-forget)
        if ctx.project.webhook_url:
            from app.services.notifications import send_deploy_notification
            await send_deploy_notification(
                ctx.project.webhook_url,
                project_slug=ctx.project.slug,
                deploy_id=str(deploy_id),
                deploy_url=ctx.deploy.url,
                status="failed",
                stage=e.stage,
                message=str(e)[:200],
            )

        # Cleanup OCI work directory
        try:
            cleanup_conversion(ctx.tag)
        except Exception:
            pass

        return ctx.deploy

    except Exception as e:
        # Unexpected error — mark deploy as failed
        logger.exception("Unexpected error in deploy %s: %s", deploy_id, e)

        # Best-effort container cleanup
        if ctx.vmid and ctx.target_node:
            try:
                stop_upid = await adapter.stop_lxc(ctx.target_node, ctx.vmid)
                if stop_upid:
                    await adapter.wait_for_task(ctx.target_node, stop_upid, timeout=60.0)
                destroy_upid = await adapter.destroy_lxc(ctx.target_node, ctx.vmid)
                if destroy_upid:
                    await adapter.wait_for_task(ctx.target_node, destroy_upid, timeout=60.0)
            except Exception:
                pass

        try:
            # Clear container tracking columns
            ctx.deploy.container_ip = None
            ctx.deploy.container_port = None
            ctx.deploy.container_vmid = None
            ctx.deploy.container_node = None

            ctx.deploy = await transition_deploy(
                db, deploy_id, "failed", f"Unexpected error: {str(e)[:200]}",
            )
            await db.commit()
        except Exception:
            pass

        # Cleanup OCI work directory (was missing from generic handler)
        try:
            cleanup_conversion(ctx.tag)
        except Exception:
            pass

        return ctx.deploy
