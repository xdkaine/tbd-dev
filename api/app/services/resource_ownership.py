"""Fail-closed ownership evidence for shared Proxmox resources."""
import json
import re
import uuid

from app.config import settings
from app.services.proxmox_adapter import ProxmoxError


def instance_namespace():
    value = settings.tbd_instance_namespace
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,19}", value):
        raise ProxmoxError("Invalid TBD instance namespace")
    return value


def ownership_marker(project_id, environment_id, deploy_id, attempt_id):
    return json.dumps({"manager": "tbd-v1", "instance": instance_namespace(),
        "project": str(uuid.UUID(str(project_id))),
        "environment": str(uuid.UUID(str(environment_id))),
        "deploy": str(uuid.UUID(str(deploy_id))),
        "attempt": str(uuid.UUID(str(attempt_id)))}, sort_keys=True)


def resource_hostname(project_id, environment_id):
    # Full project identity remains visible; environment hash avoids long hostnames.
    import hashlib
    suffix = hashlib.sha256(str(environment_id).encode()).hexdigest()[:8]
    return f"{instance_namespace()}-{uuid.UUID(str(project_id)).hex}-{suffix}"


async def require_owned(adapter, node, vmid, project_id, environment_id, deploy_id,
                        attempt_id=None):
    config = await adapter.get_lxc_config(node, vmid)
    try:
        actual = json.loads(config.get("description", ""))
        attempt = actual["attempt"] if attempt_id is None else str(attempt_id)
        expected = json.loads(ownership_marker(project_id, environment_id, deploy_id, attempt))
    except (ValueError, KeyError, TypeError):
        raise ProxmoxError("LXC ownership evidence missing or invalid") from None
    if actual != expected:
        raise ProxmoxError("LXC ownership evidence does not match this deployment")
