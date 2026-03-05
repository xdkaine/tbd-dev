"""Health check service for deployed LXC containers.

Performs HTTP health checks against running containers and triggers
auto-rollback on failure.

Per docs/deploy-state-machine.md:
- Health check: HTTP GET / (any non-5xx response = healthy)
- 5 retries every 10 seconds
- 60 second total timeout
- Auto-rollback to snapshot on failure

Per docs/oci-lxc-conversion.md:
- Health check endpoint: curl -sf http://<ip>:<port>/
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Result of a health check."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"


@dataclass
class HealthCheckConfig:
    """Health check configuration per docs/deploy-state-machine.md.

    By default checks GET / and treats any response with status < 500
    as healthy (the app is running). This accommodates frameworks like
    Next.js that return 404 for unknown routes.
    """

    # Number of retry attempts
    max_retries: int = 5

    # Seconds between retries
    retry_interval: float = 10.0

    # Total timeout for the health check phase (seconds)
    total_timeout: float = 60.0

    # Per-request timeout (seconds)
    request_timeout: float = 5.0

    # Health check endpoint path
    health_path: str = "/"

    # Any response with status < this is considered healthy.
    # Default 500 means any non-server-error response counts as healthy
    # (the app is running and responding, even if the specific path 404s).
    max_healthy_status: int = 500

    # Initial delay before first check (container startup time)
    initial_delay: float = 5.0


@dataclass
class HealthCheckResult:
    """Result of a health check sequence."""

    status: HealthStatus
    attempts: int
    last_status_code: int | None = None
    last_error: str | None = None
    total_elapsed: float = 0.0

    @property
    def passed(self) -> bool:
        return self.status == HealthStatus.HEALTHY


async def check_health(
    ip_address: str,
    port: int,
    config: HealthCheckConfig | None = None,
) -> HealthCheckResult:
    """Run a health check sequence against a container.

    Performs up to max_retries HTTP GET requests to the health endpoint,
    waiting retry_interval seconds between attempts. Respects total_timeout.

    Args:
        ip_address: Container IP address (e.g. 172.16.1.10)
        port: Application port
        config: Health check configuration

    Returns:
        HealthCheckResult with status and diagnostics
    """
    if config is None:
        config = HealthCheckConfig()

    url = f"http://{ip_address}:{port}{config.health_path}"
    logger.info(
        "Starting health check for %s (max_retries=%d, interval=%.0fs, timeout=%.0fs)",
        url, config.max_retries, config.retry_interval, config.total_timeout,
    )

    # Wait for container startup
    if config.initial_delay > 0:
        logger.debug("Waiting %.1fs for container startup...", config.initial_delay)
        await asyncio.sleep(config.initial_delay)

    total_elapsed = config.initial_delay
    last_status_code = None
    last_error = None

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(config.request_timeout, connect=3.0),
    ) as client:
        for attempt in range(1, config.max_retries + 1):
            # Check total timeout
            if total_elapsed >= config.total_timeout:
                logger.warning(
                    "Health check total timeout (%.0fs) exceeded after %d attempts",
                    config.total_timeout, attempt - 1,
                )
                return HealthCheckResult(
                    status=HealthStatus.TIMEOUT,
                    attempts=attempt - 1,
                    last_status_code=last_status_code,
                    last_error=last_error,
                    total_elapsed=total_elapsed,
                )

            try:
                logger.debug(
                    "Health check attempt %d/%d: GET %s",
                    attempt, config.max_retries, url,
                )

                response = await client.get(url)
                last_status_code = response.status_code

                if response.status_code < config.max_healthy_status:
                    logger.info(
                        "Health check PASSED on attempt %d/%d (status=%d, %.1fs elapsed)",
                        attempt, config.max_retries,
                        response.status_code, total_elapsed,
                    )
                    return HealthCheckResult(
                        status=HealthStatus.HEALTHY,
                        attempts=attempt,
                        last_status_code=response.status_code,
                        total_elapsed=total_elapsed,
                    )
                else:
                    last_error = (
                        f"Server error status {response.status_code} "
                        f"(expected < {config.max_healthy_status})"
                    )
                    logger.warning(
                        "Health check attempt %d: %s", attempt, last_error,
                    )

            except httpx.ConnectError as e:
                last_error = f"Connection refused: {e}"
                logger.warning("Health check attempt %d: %s", attempt, last_error)

            except httpx.TimeoutException as e:
                last_error = f"Request timeout: {e}"
                logger.warning("Health check attempt %d: %s", attempt, last_error)

            except httpx.HTTPError as e:
                last_error = f"HTTP error: {e}"
                logger.warning("Health check attempt %d: %s", attempt, last_error)

            # Wait before next retry (unless it's the last attempt)
            if attempt < config.max_retries:
                remaining_timeout = config.total_timeout - total_elapsed
                wait_time = min(config.retry_interval, remaining_timeout)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    total_elapsed += wait_time

    # All retries exhausted
    final_status = HealthStatus.UNREACHABLE if last_status_code is None else HealthStatus.UNHEALTHY

    logger.error(
        "Health check FAILED after %d attempts (%.1fs elapsed): %s",
        config.max_retries, total_elapsed, last_error,
    )

    return HealthCheckResult(
        status=final_status,
        attempts=config.max_retries,
        last_status_code=last_status_code,
        last_error=last_error,
        total_elapsed=total_elapsed,
    )


async def check_health_with_rollback(
    ip_address: str,
    port: int,
    node: str,
    vmid: int,
    snapshot_name: str,
    config: HealthCheckConfig | None = None,
) -> HealthCheckResult:
    """Run health check and auto-rollback on failure.

    Per docs/deploy-state-machine.md:
    - Triggered when health check fails during provisioning or healthy states
    - Proxmox adapter restores the pre-deploy LXC snapshot

    Args:
        ip_address: Container IP address
        port: Application port
        node: Proxmox node name
        vmid: LXC container VMID
        snapshot_name: Snapshot to rollback to on failure
        config: Health check configuration

    Returns:
        HealthCheckResult — if unhealthy, rollback has already been triggered
    """
    from app.services.proxmox_adapter import get_proxmox_adapter

    result = await check_health(ip_address, port, config)

    if not result.passed:
        logger.warning(
            "Health check failed for LXC %d on %s — triggering auto-rollback to snapshot '%s'",
            vmid, node, snapshot_name,
        )
        try:
            adapter = get_proxmox_adapter()
            await adapter.rollback_snapshot(node, vmid, snapshot_name)
            logger.info(
                "Auto-rollback completed: LXC %d restored to snapshot '%s'",
                vmid, snapshot_name,
            )
        except Exception as e:
            logger.error(
                "Auto-rollback FAILED for LXC %d: %s. Manual intervention required.",
                vmid, e,
            )

    return result
