"""Deploy notification service — sends webhook POSTs on deploy events.

When a project has a ``webhook_url`` configured, this service fires an
HTTP POST with a JSON payload describing the deploy event (success,
failure, rollback, etc.).  The call is fire-and-forget with a short
timeout so it never blocks the deploy pipeline.
"""

import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# Hard timeout for webhook delivery — must never slow down a deploy
_WEBHOOK_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


async def send_deploy_notification(
    webhook_url: str,
    *,
    project_slug: str,
    deploy_id: str,
    deploy_url: str | None = None,
    status: str,
    stage: str | None = None,
    message: str | None = None,
    node: str | None = None,
    vmid: int | None = None,
) -> None:
    """POST a deploy event to the project's webhook URL.

    This is intentionally fire-and-forget: failures are logged but never
    raised, and the call is bounded by a short timeout.
    """
    payload = {
        "event": "deploy",
        "project": project_slug,
        "deploy_id": deploy_id,
        "deploy_url": deploy_url,
        "status": status,
        "stage": stage,
        "message": message,
        "node": node,
        "vmid": vmid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT) as client:
            resp = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json", "User-Agent": "TBD-Platform/1.0"},
            )
        logger.info(
            "Deploy notification sent to %s (status=%d, deploy=%s, event=%s)",
            webhook_url, resp.status_code, deploy_id[:8], status,
        )
    except httpx.TimeoutException:
        logger.warning(
            "Deploy notification timed out for %s (deploy=%s)",
            webhook_url, deploy_id[:8],
        )
    except Exception as e:
        logger.warning(
            "Deploy notification failed for %s (deploy=%s): %s",
            webhook_url, deploy_id[:8], e,
        )
