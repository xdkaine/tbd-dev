"""DNS hostname helpers.

Utilities for generating deploy URLs under the domain scheme:
    <deployid>-<username>.dev.sdc.cpp          (immutable per-deploy URL)
    <project-slug>-<username>.dev.sdc.cpp      (persistent production URL)

Where:
- deployid  = first 8 chars of the Deploy UUID
- username  = AD username of the project owner, sanitized for DNS
- slug      = project slug (already DNS-safe from creation validation)
- suffix    = DEPLOY_DOMAIN_SUFFIX setting (default: dev.sdc.cpp)

Uses a hyphen (not dot) between components so the hostname
is a single-level subdomain under dev.sdc.cpp.  This way a standard
DNS wildcard *.dev.sdc.cpp resolves all deploy URLs.
"""

import re
import uuid

from app.config import settings


def sanitize_username(username: str) -> str:
    """Sanitize an AD username for use as a DNS label.

    Rules (per RFC 1123):
    - Lowercase
    - Only a-z, 0-9, and hyphens
    - No leading/trailing hyphens
    - Collapse consecutive hyphens to one
    - Max 63 chars (DNS label limit)
    """
    label = username.lower()
    label = re.sub(r"[^a-z0-9-]", "-", label)
    label = re.sub(r"-{2,}", "-", label)
    label = label.strip("-")
    return label[:63] or "unknown"


def deploy_hostname(deploy_id: uuid.UUID, owner_username: str) -> str:
    """Build the full hostname for a deploy (immutable per-deploy URL).

    Returns e.g. 'a1b2c3d4-jsmith.dev.sdc.cpp'
    """
    short_id = str(deploy_id).replace("-", "")[:8]
    safe_user = sanitize_username(owner_username)
    return f"{short_id}-{safe_user}.{settings.deploy_domain_suffix}"


def deploy_url(deploy_id: uuid.UUID, owner_username: str) -> str:
    """Build the full HTTPS URL for a deploy (immutable per-deploy URL).

    Returns e.g. 'https://a1b2c3d4-jsmith.dev.sdc.cpp'
    """
    return f"https://{deploy_hostname(deploy_id, owner_username)}"


def production_hostname(project_slug: str, owner_username: str) -> str:
    """Build the persistent production hostname for a project.

    This URL always points to the current active production deploy
    and auto-switches when a new deploy is promoted.

    Returns e.g. 'my-app-jsmith.dev.sdc.cpp'
    """
    safe_user = sanitize_username(owner_username)
    return f"{project_slug}-{safe_user}.{settings.deploy_domain_suffix}"


def production_url(project_slug: str, owner_username: str) -> str:
    """Build the full HTTPS persistent production URL for a project.

    Returns e.g. 'https://my-app-jsmith.dev.sdc.cpp'
    """
    return f"https://{production_hostname(project_slug, owner_username)}"
