"""OCI-to-LXC conversion service.

Handles the pipeline of converting OCI container images from the registry
into unpacked rootfs directories suitable for LXC container provisioning:

1. skopeo copy  — pull OCI image from registry to local OCI layout
2. umoci unpack — unpack OCI layout to rootfs directory
3. umoci stat   — extract OCI config (CMD, ENV, EXPOSE, WorkingDir)

Per docs/oci-lxc-conversion.md.
"""

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# Base directories for OCI work
OCI_WORK_DIR = Path(settings.oci_work_dir)
OCI_LAYOUTS_DIR = OCI_WORK_DIR / "oci"
ROOTFS_DIR = OCI_WORK_DIR / "rootfs"


@dataclass
class OCIConfig:
    """Extracted OCI image configuration."""

    entrypoint: list[str] = field(default_factory=list)
    cmd: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    exposed_ports: list[int] = field(default_factory=list)
    working_dir: str = "/app"

    @property
    def exec_command(self) -> str:
        """Build the full execution command from entrypoint + cmd.

        Priority: ENTRYPOINT + CMD, or just CMD, or fallback to 'node server.js'.
        """
        parts = self.entrypoint + self.cmd
        if not parts:
            return "node server.js"
        return " ".join(parts)

    @property
    def primary_port(self) -> int:
        """The primary exposed port, defaulting to 3000.

        Prefers the explicit PORT env var over EXPOSE directives, because
        base images can contribute EXPOSE values the app doesn't actually
        listen on (e.g. nginx:alpine exposes 80 even when the Dockerfile
        sets PORT=3000 and the config listens on $PORT).
        """
        if "PORT" in self.env:
            try:
                return int(self.env["PORT"])
            except ValueError:
                pass
        if self.exposed_ports:
            return self.exposed_ports[0]
        return 3000


async def _run_command(
    cmd: list[str],
    timeout: float,
    description: str,
) -> tuple[int, str, str]:
    """Run a subprocess command with timeout.

    Returns (return_code, stdout, stderr).
    Raises TimeoutError if the command exceeds the timeout.
    """
    logger.info("Running: %s (timeout=%.0fs)", description, timeout)
    logger.debug("Command: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(
            f"{description} timed out after {timeout}s"
        )

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")

    if proc.returncode != 0:
        logger.error(
            "%s failed (rc=%d): %s", description, proc.returncode, stderr[:500]
        )
    else:
        logger.info("%s completed successfully", description)

    return proc.returncode, stdout, stderr


class OCIConversionError(Exception):
    """Raised when OCI conversion fails at any stage."""

    def __init__(self, stage: str, message: str, details: str = ""):
        self.stage = stage
        self.message = message
        self.details = details
        super().__init__(f"OCI conversion failed at {stage}: {message}")


async def pull_image(image_ref: str, tag: str) -> Path:
    """Step 1: Pull an OCI image from the registry using skopeo.

    Args:
        image_ref: Full image reference (e.g. registry.sdc.cpp/tbd/my-app:abc123)
        tag: Tag identifier for local storage naming

    Returns:
        Path to the local OCI layout directory

    Raises:
        OCIConversionError: If pull fails after retries
    """
    layout_dir = OCI_LAYOUTS_DIR / tag
    layout_dir.parent.mkdir(parents=True, exist_ok=True)

    # Clean up any previous layout
    if layout_dir.exists():
        shutil.rmtree(layout_dir)

    # Build skopeo command
    # docker:// source -> oci:// destination
    src = f"docker://{image_ref}"
    dst = f"oci:{layout_dir}:latest"

    cmd = [
        "skopeo", "copy",
        "--src-tls-verify=false",  # Internal registry, no TLS
        src, dst,
    ]

    # Add registry credentials if configured
    if settings.registry_username and settings.registry_password:
        cmd.insert(2, f"--src-creds={settings.registry_username}:{settings.registry_password}")

    # Retry logic: 3 attempts with backoff per docs
    max_retries = 3
    stderr = ""
    for attempt in range(1, max_retries + 1):
        try:
            rc, stdout, stderr = await _run_command(
                cmd,
                timeout=120.0,  # 2 min timeout per docs
                description=f"skopeo copy (attempt {attempt}/{max_retries})",
            )
            if rc == 0:
                logger.info("Image pulled to %s", layout_dir)
                return layout_dir
        except TimeoutError:
            if attempt == max_retries:
                raise OCIConversionError(
                    stage="pull",
                    message=f"Image pull timed out after {max_retries} attempts",
                    details=f"image_ref={image_ref}",
                )
            logger.warning("Pull attempt %d timed out, retrying...", attempt)

        if attempt < max_retries:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s

    raise OCIConversionError(
        stage="pull",
        message="Image pull failed after all retries",
        details=stderr[:500],
    )


async def unpack_rootfs(layout_dir: Path, tag: str) -> Path:
    """Step 2: Unpack an OCI layout to a rootfs directory using umoci.

    Args:
        layout_dir: Path to OCI layout (from pull_image)
        tag: Tag identifier for rootfs naming

    Returns:
        Path to the unpacked rootfs directory

    Raises:
        OCIConversionError: If unpack fails
    """
    rootfs_dir = ROOTFS_DIR / tag
    rootfs_dir.parent.mkdir(parents=True, exist_ok=True)

    # Clean up previous rootfs
    if rootfs_dir.exists():
        shutil.rmtree(rootfs_dir)

    cmd = [
        "umoci", "unpack",
        "--image", f"{layout_dir}:latest",
        rootfs_dir.as_posix(),
    ]

    # 1 retry per docs
    max_retries = 2
    stderr = ""
    for attempt in range(1, max_retries + 1):
        try:
            rc, stdout, stderr = await _run_command(
                cmd,
                timeout=300.0,  # 5 min timeout per docs
                description=f"umoci unpack (attempt {attempt}/{max_retries})",
            )
            if rc == 0:
                logger.info("Rootfs unpacked to %s", rootfs_dir)
                return rootfs_dir
        except TimeoutError:
            if attempt == max_retries:
                raise OCIConversionError(
                    stage="unpack",
                    message=f"Rootfs unpack timed out after {max_retries} attempts",
                    details=f"layout_dir={layout_dir}",
                )

        if attempt < max_retries:
            # Clean up failed unpack
            if rootfs_dir.exists():
                shutil.rmtree(rootfs_dir)
            await asyncio.sleep(2)

    raise OCIConversionError(
        stage="unpack",
        message="Rootfs unpack failed after all retries",
        details=stderr[:500],
    )


def _resolve_oci_blob(layout_dir: Path, digest: str) -> Path:
    if ":" not in digest:
        raise ValueError(f"Invalid OCI digest: {digest}")
    algo, hex_digest = digest.split(":", 1)
    return layout_dir / "blobs" / algo / hex_digest


def _select_manifest_descriptor(manifests: list[dict]) -> dict:
    for manifest in manifests:
        platform = manifest.get("platform") or {}
        if platform.get("os") == "linux" and platform.get("architecture") in {
            "amd64",
            "x86_64",
        }:
            return manifest
    return manifests[0]


def _extract_config_from_layout(layout_dir: Path) -> OCIConfig:
    index_path = layout_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Missing OCI index.json at {index_path}")

    index = json.loads(index_path.read_text())
    manifests = index.get("manifests") or []
    if not manifests:
        raise ValueError("OCI index.json has no manifests")

    manifest_desc = _select_manifest_descriptor(manifests)
    manifest_path = _resolve_oci_blob(layout_dir, manifest_desc["digest"])
    manifest = json.loads(manifest_path.read_text())

    config_desc = manifest.get("config") or {}
    config_digest = config_desc.get("digest")
    if not config_digest:
        raise ValueError("OCI manifest missing config digest")

    config_path = _resolve_oci_blob(layout_dir, config_digest)
    config_data = json.loads(config_path.read_text())
    return _parse_oci_stat(config_data)


async def extract_oci_config(layout_dir: Path) -> OCIConfig:
    """Step 3: Extract OCI image configuration using OCI layout or umoci stat.

    Parses Cmd, Entrypoint, Env, ExposedPorts, and WorkingDir from
    the OCI image manifest/config.

    Args:
        layout_dir: Path to OCI layout

    Returns:
        OCIConfig with extracted values

    Raises:
        OCIConversionError: If config extraction fails
    """
    try:
        config = _extract_config_from_layout(layout_dir)
        logger.info(
            "OCI config extracted (layout): cmd=%s, workdir=%s, ports=%s, env_count=%d",
            config.exec_command,
            config.working_dir,
            config.exposed_ports,
            len(config.env),
        )
        if config.entrypoint or config.cmd or config.env or config.exposed_ports:
            return config
    except Exception as exc:
        logger.warning(
            "Failed to read OCI config from layout, falling back to umoci stat: %s",
            exc,
        )

    cmd = [
        "umoci", "stat",
        "--image", f"{layout_dir}:latest",
        "--json",
    ]

    rc, stdout, stderr = await _run_command(
        cmd,
        timeout=30.0,
        description="umoci stat (config extraction)",
    )

    if rc != 0:
        raise OCIConversionError(
            stage="config_extract",
            message="Failed to extract OCI config",
            details=stderr[:500],
        )

    try:
        stat_data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise OCIConversionError(
            stage="config_extract",
            message=f"Invalid JSON from umoci stat: {e}",
            details=stdout[:500],
        )

    config = _parse_oci_stat(stat_data)
    logger.info(
        "OCI config extracted (umoci): cmd=%s, workdir=%s, ports=%s, env_count=%d",
        config.exec_command,
        config.working_dir,
        config.exposed_ports,
        len(config.env),
    )
    return config


def _parse_oci_stat(stat_data: dict) -> OCIConfig:
    """Parse the JSON output of 'umoci stat --json'.

    Handles both direct config format and nested OCI manifest format.
    """
    # Try to find the image config
    img_config = {}

    if "config" in stat_data:
        cfg = stat_data["config"]
        if "config" in cfg:
            img_config = cfg["config"]
        else:
            img_config = cfg
    elif "image" in stat_data:
        cfg = stat_data["image"]
        if "config" in cfg:
            img_config = cfg["config"]

    # Extract entrypoint
    entrypoint = img_config.get("Entrypoint") or img_config.get("entrypoint") or []
    if isinstance(entrypoint, str):
        entrypoint = [entrypoint]

    # Extract cmd
    cmd = img_config.get("Cmd") or img_config.get("cmd") or []
    if isinstance(cmd, str):
        cmd = [cmd]

    # Extract environment variables
    env_list = img_config.get("Env") or img_config.get("env") or []
    env_dict = {}
    for entry in env_list:
        if "=" in entry:
            key, _, value = entry.partition("=")
            env_dict[key] = value

    # Extract exposed ports
    # OCI format: {"ExposedPorts": {"3000/tcp": {}, "8080/tcp": {}}}
    exposed = img_config.get("ExposedPorts") or img_config.get("exposedPorts") or {}
    ports = []
    if isinstance(exposed, dict):
        for port_spec in exposed:
            # Parse "3000/tcp" -> 3000
            port_str = port_spec.split("/")[0]
            try:
                ports.append(int(port_str))
            except ValueError:
                pass
    elif isinstance(exposed, list):
        for p in exposed:
            try:
                ports.append(int(str(p).split("/")[0]))
            except ValueError:
                pass

    # Extract working directory
    working_dir = (
        img_config.get("WorkingDir")
        or img_config.get("workingDir")
        or img_config.get("working_dir")
        or "/app"
    )

    return OCIConfig(
        entrypoint=entrypoint,
        cmd=cmd,
        env=env_dict,
        exposed_ports=sorted(ports),
        working_dir=working_dir,
    )


async def convert_image(image_ref: str, tag: str) -> tuple[Path, OCIConfig]:
    """Full OCI conversion pipeline: pull -> unpack -> extract config.

    This is the main entry point for the conversion service.

    Args:
        image_ref: Full image reference from registry
        tag: Unique tag for this conversion (typically commit SHA or build ID)

    Returns:
        Tuple of (rootfs_path, oci_config)

    Raises:
        OCIConversionError: If any step fails
    """
    logger.info("Starting OCI conversion for %s (tag=%s)", image_ref, tag)

    # Step 1: Pull image
    layout_dir = await pull_image(image_ref, tag)

    # Step 2: Extract config (before unpack so we have it early)
    oci_config = await extract_oci_config(layout_dir)

    # Step 3: Unpack rootfs
    rootfs_path = await unpack_rootfs(layout_dir, tag)

    logger.info(
        "OCI conversion complete: rootfs=%s, cmd=%s",
        rootfs_path,
        oci_config.exec_command,
    )

    return rootfs_path, oci_config


async def create_template_tarball(rootfs_path: Path, tag: str) -> Path:
    """Create a Proxmox-compatible CT template tarball from an unpacked rootfs.

    Proxmox expects CT templates as .tar.gz (or .tar.zst) archives where
    the root of the archive IS the root filesystem (i.e. ./etc, ./bin, etc.
    — NOT rootfs/etc).

    The rootfs must already have the init script and secrets injected
    (via systemd_generator.install_unit_to_rootfs and secrets_injector).

    Args:
        rootfs_path: Path to the unpacked rootfs dir (umoci output, may
                     contain a nested rootfs/ subdirectory)
        tag: Unique tag for naming the tarball

    Returns:
        Path to the created .tar.gz file

    Raises:
        OCIConversionError: If tarball creation fails
    """
    # umoci nests the actual rootfs under rootfs_path/rootfs/
    actual_rootfs = rootfs_path / "rootfs"
    if not actual_rootfs.exists():
        actual_rootfs = rootfs_path

    tarball_path = OCI_WORK_DIR / "templates" / f"{tag}.tar.gz"
    tarball_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove old tarball if it exists
    if tarball_path.exists():
        tarball_path.unlink()

    # Use tar to create the archive from inside the rootfs directory
    # so that paths are relative (./etc, ./bin, etc.)
    cmd = [
        "tar",
        "-czf", tarball_path.as_posix(),
        "-C", actual_rootfs.as_posix(),
        ".",
    ]

    rc, stdout, stderr = await _run_command(
        cmd,
        timeout=300.0,  # 5 min — large rootfs images can be slow
        description=f"Create template tarball for {tag}",
    )

    if rc != 0:
        raise OCIConversionError(
            stage="template_tarball",
            message=f"Failed to create template tarball (rc={rc})",
            details=stderr[:500],
        )

    size_mb = tarball_path.stat().st_size / (1024 * 1024)
    logger.info(
        "Template tarball created: %s (%.1f MB)",
        tarball_path, size_mb,
    )

    return tarball_path


def cleanup_conversion(tag: str) -> None:
    """Clean up OCI layout, rootfs, and template tarball for a given tag.

    Call this after a deploy is superseded or to free disk space.
    """
    layout_dir = OCI_LAYOUTS_DIR / tag
    rootfs_dir = ROOTFS_DIR / tag
    template_dir = OCI_WORK_DIR / "templates"
    tarball = template_dir / f"{tag}.tar.gz"

    for d in (layout_dir, rootfs_dir):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            logger.info("Cleaned up %s", d)

    if tarball.exists():
        tarball.unlink()
        logger.info("Cleaned up template tarball %s", tarball)
