"""Deploy teardown service.

Centralizes all infrastructure cleanup when a deploy is destroyed,
rolled back, or superseded:

  1. Stop the LXC container on Proxmox (if running)
  2. Destroy the LXC container
  3. Remove the per-deploy Nginx upstream config
  4. Remove the production Nginx config (if this was the active deploy)
  5. Signal Nginx reload
  6. Clear the deploy URL in the database

This module is the single source of truth for "how to clean up a deploy"
so that rollback, supersede, destroy, and lifecycle cleanup all share
the same logic.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.deploy import Deploy
from app.models.environment import Environment
from app.services.dns_routing import (
    signal_nginx_reload,
    unregister_deploy_routing,
)
from app.services.proxmox_adapter import (
    ProxmoxAdapter,
    ProxmoxError,
    get_proxmox_adapter,
)

from app.services.resource_ownership import require_owned, resource_hostname

logger = logging.getLogger(__name__)


class TeardownError(Exception):
    """Raised when teardown encounters a non-recoverable error."""
    pass


async def stop_lxc_container(
    adapter: ProxmoxAdapter,
    node: str,
    vmid: int,
    *,
    ownership: tuple,
) -> bool:
    """Stop an LXC container. Returns True if stopped successfully."""
    try:
        await require_owned(adapter, node, vmid, *ownership)
        stop_upid = await adapter.stop_lxc(node, vmid)
        if stop_upid:
            if not await adapter.wait_for_task(node, stop_upid, timeout=60.0):
                return False
        logger.info("Stopped LXC %d on %s", vmid, node)
        return True
    except ProxmoxError as e:
        logger.warning("Failed to stop LXC %d on %s: %s", vmid, node, e)
        return False


async def destroy_lxc_container(
    adapter: ProxmoxAdapter,
    node: str,
    vmid: int,
    *,
    ownership: tuple,
) -> bool:
    """Stop and destroy an LXC container. Returns True on success."""
    # Stop first (destroy requires stopped state)
    if not await stop_lxc_container(adapter, node, vmid, ownership=ownership):
        return False

    try:
        await require_owned(adapter, node, vmid, *ownership)
        destroy_upid = await adapter.destroy_lxc(node, vmid)
        if destroy_upid:
            if not await adapter.wait_for_task(node, destroy_upid, timeout=60.0):
                return False
        logger.info("Destroyed LXC %d on %s", vmid, node)
        return True
    except ProxmoxError as e:
        if e.status_code == 404:
            logger.info("LXC %d on %s is already absent", vmid, node)
            return True
        logger.error("Failed to destroy LXC %d on %s: %s", vmid, node, e)
        return False


async def teardown_deploy(
    db: AsyncSession,
    deploy_id: uuid.UUID,
    *,
    remove_production_route: bool = False,
    destroy_container: bool = True,
) -> bool:
    """Full teardown of a deploy's infrastructure.

    Steps:
      1. Look up deploy + environment + project
      2. Find matching LXC container on Proxmox
      3. Stop + destroy the LXC (if destroy_container=True)
      4. Remove per-deploy Nginx config
      5. Optionally remove production Nginx config
      6. Signal Nginx reload
      7. Clear deploy.url in DB

    Args:
        db: Database session.
        deploy_id: Deploy UUID.
        remove_production_route: If True, also remove the persistent
            production URL config (only when tearing down the active deploy
            with no replacement).
        destroy_container: If True (default), stop and destroy the LXC.
            Set to False for "soft" teardown (just clean up routing).

    Returns:
        True if teardown completed, False if deploy was not found.

    Raises:
        TeardownError: If container absence cannot be proven or destruction fails.
    """
    # Load deploy with environment and project
    result = await db.execute(
        select(Deploy)
        .where(Deploy.id == deploy_id)
        .options(
            selectinload(Deploy.environment).selectinload(Environment.project),
        )
    )
    deploy = result.scalar_one_or_none()
    if deploy is None:
        logger.warning("Teardown: deploy %s not found", deploy_id)
        return False

    environment = deploy.environment
    project = environment.project if environment else None

    if not environment or not project:
        logger.warning("Teardown: deploy %s missing env/project refs", deploy_id)
        return False

    hostname = resource_hostname(project.id, environment.id)
    ownership = (project.id, environment.id, deploy.id)
    deploy_id_str = str(deploy_id)

    logger.info(
        "Tearing down deploy %s (hostname=%s, destroy_container=%s)",
        deploy_id_str[:8], hostname, destroy_container,
    )

    adapter = get_proxmox_adapter()

    # Step 1: Find and destroy LXC container
    #
    # Stored VMID/node plus exact ownership evidence are required. Display
    # names and broad cluster discovery cannot authorize destructive actions.
    if destroy_container:
        if deploy.container_vmid and deploy.container_node:
            # Precise teardown using the exact VMID persisted at creation time
            node = deploy.container_node
            vmid = deploy.container_vmid
            logger.info(
                "Teardown: targeting stored LXC %d on %s for deploy %s",
                vmid, node, deploy_id_str[:8],
            )
            destroyed = await destroy_lxc_container(adapter, node, vmid, ownership=ownership)
            if destroyed:
                logger.info("Teardown: destroyed LXC %d for deploy %s", vmid, deploy_id_str[:8])
            else:
                raise TeardownError(
                    f"Failed to destroy LXC {vmid} on {node} for deploy {deploy_id_str[:8]}"
                )
        elif deploy.container_vmid or deploy.status in {
            "provisioning",
            "healthy",
            "active",
            "superseded",
            "stopped",
        }:
            raise TeardownError(
                "Deployment lacks complete immutable container identity; manual reconciliation required"
            )
        else:
            logger.info(
                "Teardown: deploy %s has no container identity in state %s; "
                "skipping unsafe hostname scan",
                deploy_id_str[:8],
                deploy.status,
            )

    # Step 2: Remove per-deploy Nginx config
    nginx_removed = False
    try:
        nginx_removed = await unregister_deploy_routing(deploy_id_str)
        if nginx_removed:
            logger.info("Teardown: removed Nginx config for deploy %s", deploy_id_str[:8])
    except Exception as e:
        logger.warning("Teardown: failed to remove Nginx config for deploy %s: %s", deploy_id_str[:8], e)

    # Step 3: Remove production route if requested
    if remove_production_route:
        try:
            from app.services.dns_routing import unregister_production_routing
            await unregister_production_routing(project.slug)
            logger.info("Teardown: removed production Nginx config for %s", project.slug)
        except Exception as e:
            logger.warning("Teardown: failed to remove production config for %s: %s", project.slug, e)

    # Step 4: Signal Nginx reload (if anything was changed)
    if nginx_removed or remove_production_route:
        try:
            await signal_nginx_reload()
        except Exception as e:
            logger.warning("Teardown: Nginx reload signal failed: %s", e)

    # Step 5: Clear deploy URL in DB
    deploy.url = None
    await db.flush()

    logger.info("Teardown complete for deploy %s", deploy_id_str[:8])
    return True


async def teardown_deploy_by_hostname(
    hostname: str,
    *,
    adapter: ProxmoxAdapter | None = None,
) -> bool:
    """Reject legacy hostname-only cleanup; ownership must come from a deploy record."""
    raise TeardownError("Hostname-only deletion is disabled; use deployment ownership evidence")
