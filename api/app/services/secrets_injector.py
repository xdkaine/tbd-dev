"""Secrets environment file generator.

Decrypts Fernet-encrypted secrets from the database and writes them
into the LXC rootfs at /etc/tbd/secrets.env for systemd EnvironmentFile
injection.

Per docs/oci-lxc-conversion.md:
- systemd unit uses EnvironmentFile=/etc/tbd/secrets.env
- Secrets are scoped by project + environment

Per README.md (secrets model):
- Secrets are stored with Fernet encryption (value_encrypted)
- Scope values: 'project', 'production', 'staging', 'preview'
- Project-scoped secrets apply to ALL environments
- Environment-scoped secrets apply only to matching environment type
"""

import logging
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.secret import Secret

logger = logging.getLogger(__name__)


class SecretsInjectionError(Exception):
    """Raised when secret injection into rootfs fails."""
    pass


def _get_fernet() -> Fernet:
    """Get the Fernet cipher for secret decryption.

    Uses the same key as the secrets service (settings.secrets_encryption_key).
    """
    key = settings.secrets_encryption_key
    if not key:
        raise SecretsInjectionError(
            "SECRETS_ENCRYPTION_KEY is not configured — cannot decrypt secrets"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def _decrypt_value(encrypted_value: str) -> str:
    """Decrypt a single Fernet-encrypted secret value.

    Args:
        encrypted_value: Base64-encoded Fernet token

    Returns:
        Decrypted plaintext value

    Raises:
        SecretsInjectionError: If decryption fails
    """
    try:
        fernet = _get_fernet()
        return fernet.decrypt(encrypted_value.encode()).decode("utf-8")
    except InvalidToken:
        raise SecretsInjectionError(
            "Failed to decrypt secret — invalid token or wrong encryption key"
        )
    except Exception as e:
        raise SecretsInjectionError(f"Secret decryption error: {e}")


async def load_secrets_for_deploy(
    db: AsyncSession,
    project_id: uuid.UUID,
    env_type: str,
) -> dict[str, str]:
    """Load and decrypt all secrets applicable to a deploy.

    Secrets are scoped per docs:
    - 'project' scope: applies to all environments
    - Environment-specific scope ('production', 'staging', 'preview'):
      applies only to matching env_type

    Args:
        db: Database session
        project_id: Project to load secrets for
        env_type: Environment type (production, staging, preview)

    Returns:
        Dict of KEY=value pairs (decrypted)
    """
    # Query secrets with matching scope
    applicable_scopes = ["project", env_type]
    result = await db.execute(
        select(Secret).where(
            Secret.project_id == project_id,
            Secret.scope.in_(applicable_scopes),
        ).order_by(Secret.key)
    )
    secrets = result.scalars().all()

    if not secrets:
        logger.info(
            "No secrets found for project %s (env_type=%s)", project_id, env_type,
        )
        return {}

    # Decrypt all values
    decrypted: dict[str, str] = {}
    for secret in secrets:
        try:
            decrypted[secret.key] = _decrypt_value(secret.value_encrypted)
        except SecretsInjectionError as e:
            logger.error(
                "Failed to decrypt secret '%s' for project %s: %s",
                secret.key, project_id, e,
            )
            # Skip individual failed secrets rather than failing the whole deploy
            continue

    logger.info(
        "Loaded %d secrets for project %s (env_type=%s, scopes=%s)",
        len(decrypted), project_id, env_type, applicable_scopes,
    )

    return decrypted


def generate_secrets_env_content(secrets: dict[str, str]) -> str:
    """Generate the contents of /etc/tbd/secrets.env.

    Format: KEY=value (one per line), suitable for systemd EnvironmentFile.

    Args:
        secrets: Dict of decrypted KEY=value pairs

    Returns:
        File content string
    """
    lines = ["# TBD Platform - injected secrets", "# Auto-generated — do not edit"]

    for key, value in sorted(secrets.items()):
        # Escape special characters for systemd EnvironmentFile format
        # systemd EnvironmentFile supports quoting with double quotes
        if any(c in value for c in [" ", '"', "'", "\n", "\t", "#", "\\", "$"]):
            # Quote the value and escape internal double quotes and backslashes
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}="{escaped}"')
        else:
            lines.append(f"{key}={value}")

    # Always end with a newline
    return "\n".join(lines) + "\n"


def write_secrets_to_rootfs(
    rootfs_path: Path,
    secrets: dict[str, str],
) -> Path:
    """Write decrypted secrets to /etc/tbd/secrets.env inside the rootfs.

    Args:
        rootfs_path: Path to the unpacked rootfs directory
        secrets: Dict of decrypted KEY=value pairs

    Returns:
        Path to the written secrets.env file

    Raises:
        SecretsInjectionError: If file write fails
    """
    # Handle umoci unpack format (rootfs may be nested)
    actual_rootfs = rootfs_path / "rootfs"
    if not actual_rootfs.exists():
        actual_rootfs = rootfs_path

    tbd_dir = actual_rootfs / "etc" / "tbd"
    tbd_dir.mkdir(parents=True, exist_ok=True)

    secrets_env_path = tbd_dir / "secrets.env"

    try:
        content = generate_secrets_env_content(secrets)
        secrets_env_path.write_text(content)

        # Restrict permissions: only readable by root and tbd-app
        secrets_env_path.chmod(0o640)

        logger.info(
            "Wrote %d secrets to %s", len(secrets), secrets_env_path,
        )
        return secrets_env_path

    except OSError as e:
        raise SecretsInjectionError(
            f"Failed to write secrets.env to {secrets_env_path}: {e}"
        )


async def inject_secrets(
    db: AsyncSession,
    rootfs_path: Path,
    project_id: uuid.UUID,
    env_type: str,
) -> Path:
    """Full pipeline: load secrets from DB, decrypt, write to rootfs.

    This is the main entry point called by the deploy executor between
    systemd unit generation and LXC container creation.

    Args:
        db: Database session
        rootfs_path: Path to the unpacked rootfs directory
        project_id: Project to load secrets for
        env_type: Environment type (production, staging, preview)

    Returns:
        Path to the written secrets.env file
    """
    secrets = await load_secrets_for_deploy(db, project_id, env_type)
    secrets_env_path = write_secrets_to_rootfs(rootfs_path, secrets)

    logger.info(
        "Injected %d secrets into rootfs for project %s (env=%s)",
        len(secrets), project_id, env_type,
    )

    return secrets_env_path
