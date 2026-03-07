"""Deploy reconciler — periodic background task that detects and repairs
infrastructure inconsistencies.

Runs alongside the lifecycle loop during application lifespan. Each cycle
performs lightweight checks against the database and filesystem, and
optionally against Proxmox, to catch:

  1. Stale Nginx configs for terminal deploys (removed automatically)
  2. Duplicate active IP assignments (logged as critical)
  3. Stuck deploys that have been in-progress for too long (failed automatically)
  4. Orphaned containers on Proxmox with no matching non-terminal deploy

Designed to be safe: every repair action is idempotent and best-effort.
Failures in one check do not block the others.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models.deploy import Deploy

logger = logging.getLogger(__name__)

# How often to run the reconciler (seconds)
_RECONCILE_INTERVAL = 300  # 5 minutes

# Deploys stuck in these states for longer than this are auto-failed
_STUCK_THRESHOLD = timedelta(minutes=30)

# Terminal statuses whose infrastructure should have been cleaned up
_TERMINAL_STATUSES = ("superseded", "rolled_back", "failed")

# Directory where Nginx upstream configs live
_UPSTREAM_DIR = Path(settings.nginx_upstream_dir)


# ---------------------------------------------------------------------------
# Individual reconciliation checks
# ---------------------------------------------------------------------------


async def _reconcile_stale_nginx_configs(db: AsyncSession) -> int:
    """Remove Nginx config files for deploys in terminal states.

    Returns the number of stale configs removed.
    """
    if not _UPSTREAM_DIR.exists():
        return 0

    # Collect all deploy-*.conf files
    deploy_confs = list(_UPSTREAM_DIR.glob("deploy-*.conf"))
    if not deploy_confs:
        return 0

    # Query ALL terminal deploys in one go (cheap — only reads id column)
    result = await db.execute(
        select(Deploy.id).where(Deploy.status.in_(_TERMINAL_STATUSES))
    )
    terminal_ids: set[str] = set()
    for (deploy_id,) in result:
        # Build the short_id the same way dns_routing.py does
        short_id = str(deploy_id).replace("-", "")[:8]
        terminal_ids.add(short_id)

    removed = 0
    for conf in deploy_confs:
        # Filename format: deploy-{short_id}.conf
        stem = conf.stem  # "deploy-e7ed1473"
        if not stem.startswith("deploy-"):
            continue
        short_id = stem[len("deploy-"):]
        if short_id in terminal_ids:
            try:
                conf.unlink()
                logger.info("Reconciler: removed stale Nginx config %s", conf.name)
                removed += 1
            except OSError as e:
                logger.warning("Reconciler: failed to remove %s: %s", conf.name, e)

    if removed > 0:
        # Signal Nginx reload
        try:
            from app.services.dns_routing import signal_nginx_reload
            await signal_nginx_reload()
        except Exception as e:
            logger.warning("Reconciler: Nginx reload signal failed: %s", e)

    return removed


async def _reconcile_duplicate_ips(db: AsyncSession) -> int:
    """Detect non-terminal deploys sharing the same container_ip.

    Returns the number of duplicate IP groups found.
    """
    result = await db.execute(
        select(Deploy.container_ip, func.count(Deploy.id).label("cnt"))
        .where(
            Deploy.container_ip.isnot(None),
            Deploy.status.notin_(_TERMINAL_STATUSES),
        )
        .group_by(Deploy.container_ip)
        .having(func.count(Deploy.id) > 1)
    )
    duplicates = result.all()

    for ip, count in duplicates:
        # Log details about which deploys share this IP
        detail_result = await db.execute(
            select(Deploy.id, Deploy.status, Deploy.created_at).where(
                Deploy.container_ip == ip,
                Deploy.status.notin_(_TERMINAL_STATUSES),
            )
        )
        deploy_details = [
            f"{row.id} ({row.status}, created {row.created_at})"
            for row in detail_result
        ]
        logger.critical(
            "DUPLICATE IP DETECTED: %s is assigned to %d non-terminal deploys: %s",
            ip, count, "; ".join(deploy_details),
        )

    return len(duplicates)


async def _reconcile_stuck_deploys(db: AsyncSession) -> int:
    """Transition deploys stuck in in-progress states to 'failed'.

    Returns the number of deploys auto-failed.
    """
    cutoff = datetime.now(timezone.utc) - _STUCK_THRESHOLD
    in_progress_states = ["building", "artifact_ready", "provisioning", "healthy"]

    result = await db.execute(
        select(Deploy).where(
            Deploy.status.in_(in_progress_states),
            Deploy.created_at < cutoff,
        ).with_for_update(skip_locked=True)
    )
    stuck_deploys = result.scalars().all()

    failed_count = 0
    for deploy in stuck_deploys:
        old_status = deploy.status
        if deploy.can_transition_to("failed"):
            deploy.status = "failed"

            # Clear container tracking if set (the IP may be stale)
            deploy.container_ip = None
            deploy.container_port = None
            deploy.container_vmid = None
            deploy.container_node = None

            failed_count += 1
            logger.warning(
                "Reconciler: auto-failed stuck deploy %s (was '%s' since %s)",
                deploy.id, old_status, deploy.created_at,
            )

    if failed_count > 0:
        await db.flush()

    return failed_count


async def _reconcile_ghost_active_deploys(db: AsyncSession) -> int:
    """Detect 'active' deploys whose container_vmid/container_node suggest
    a container should exist, and verify it actually does on Proxmox.

    For the first version, we only log warnings — we don't auto-transition
    since a transient Proxmox API error could cause false positives.

    Returns the number of ghost deploys detected.
    """
    result = await db.execute(
        select(Deploy).where(
            Deploy.status == "active",
            Deploy.container_vmid.isnot(None),
            Deploy.container_node.isnot(None),
        )
    )
    active_deploys = result.scalars().all()

    if not active_deploys:
        return 0

    try:
        from app.services.proxmox_adapter import get_proxmox_adapter
        adapter = get_proxmox_adapter()
    except Exception as e:
        logger.warning("Reconciler: could not get Proxmox adapter: %s", e)
        return 0

    ghost_count = 0
    for deploy in active_deploys:
        try:
            status = await adapter.get_lxc_status(deploy.container_node, deploy.container_vmid)
            lxc_status = status.status
            if lxc_status != "running":
                logger.warning(
                    "Reconciler: active deploy %s has container %d on %s "
                    "but status is '%s' (expected 'running')",
                    deploy.id, deploy.container_vmid, deploy.container_node, lxc_status,
                )
                ghost_count += 1
        except Exception as e:
            logger.warning(
                "Reconciler: active deploy %s — could not check container %d on %s: %s",
                deploy.id, deploy.container_vmid, deploy.container_node, e,
            )
            ghost_count += 1

    return ghost_count


# ---------------------------------------------------------------------------
# Main reconciliation cycle
# ---------------------------------------------------------------------------


async def _run_reconcile_cycle() -> dict:
    """Run one full reconciliation cycle. Returns a summary dict."""
    summary = {
        "stale_nginx_removed": 0,
        "duplicate_ips": 0,
        "stuck_failed": 0,
        "ghost_active": 0,
    }

    async with async_session_factory() as db:
        try:
            summary["stale_nginx_removed"] = await _reconcile_stale_nginx_configs(db)
        except Exception:
            logger.exception("Reconciler: stale Nginx config check failed")

        try:
            summary["duplicate_ips"] = await _reconcile_duplicate_ips(db)
        except Exception:
            logger.exception("Reconciler: duplicate IP check failed")

        try:
            summary["stuck_failed"] = await _reconcile_stuck_deploys(db)
        except Exception:
            logger.exception("Reconciler: stuck deploy check failed")

        try:
            summary["ghost_active"] = await _reconcile_ghost_active_deploys(db)
        except Exception:
            logger.exception("Reconciler: ghost active deploy check failed")

        # Commit any changes (stuck deploys marked failed, etc.)
        try:
            await db.commit()
        except Exception:
            logger.exception("Reconciler: commit failed")

    return summary


async def run_reconciler_loop() -> None:
    """Background loop that periodically reconciles deploy infrastructure.

    Designed to be launched as an asyncio task during app lifespan.
    Runs indefinitely until cancelled.
    """
    logger.info(
        "Deploy reconciler started (interval=%ds, stuck_threshold=%s)",
        _RECONCILE_INTERVAL, _STUCK_THRESHOLD,
    )

    while True:
        try:
            summary = await _run_reconcile_cycle()

            # Only log if something was found/fixed
            if any(v > 0 for v in summary.values()):
                logger.info(
                    "Reconciler cycle complete: %s",
                    ", ".join(f"{k}={v}" for k, v in summary.items() if v > 0),
                )
        except asyncio.CancelledError:
            logger.info("Deploy reconciler shutting down")
            raise
        except Exception:
            logger.exception("Error in deploy reconciler cycle")

        await asyncio.sleep(_RECONCILE_INTERVAL)
