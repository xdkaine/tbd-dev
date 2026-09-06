"""Build and publish OCI images without a Docker daemon or host socket."""
import base64
import json
import os
from pathlib import Path
import tarfile
import tempfile


def build_command(repo_dir, context, dockerfile, output, labels):
    root = Path(repo_dir).resolve()
    ctx = (root / context).resolve()
    df = (root / dockerfile).resolve() if dockerfile else ctx / "Dockerfile"
    if not ctx.is_relative_to(root) or not df.is_relative_to(root):
        raise ValueError("Build paths must remain inside the repository")
    args = ["buildctl", "--addr", os.environ["BUILDKIT_HOST"],
            "--tlscacert", "/etc/buildkit/client/ca.crt",
            "--tlscert", "/etc/buildkit/client/tls.crt",
            "--tlskey", "/etc/buildkit/client/tls.key", "build",
            "--progress", "plain", "--frontend", "dockerfile.v0",
            "--local", f"context={ctx}", "--local", f"dockerfile={df.parent}",
            "--opt", f"filename={df.name}", "--output", f"type=oci,dest={output}"]
    for name, value in labels.items():
        args.extend(["--opt", f"label:{name}={value}"])
    return args


def archive_identity(archive):
    # Read only the OCI index/manifest; never extract arbitrary archive paths.
    with tarfile.open(archive) as tf:
        index = json.load(tf.extractfile("index.json"))
        descriptor = index["manifests"][0]
        digest = descriptor["digest"]
        algorithm, value = digest.split(":", 1)
        if algorithm != "sha256" or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("Invalid OCI manifest digest")
        manifest = json.load(tf.extractfile(f"blobs/sha256/{value}"))
        return manifest["config"]["digest"], sum(layer["size"] for layer in manifest["layers"])


async def build_and_publish(run_cmd, *, repo_dir, context, dockerfile, image_tag,
                            latest_tag, labels, registry_url, username, password,
                            log_lines):
    with tempfile.TemporaryDirectory(prefix=".tbd-oci-", dir=Path(repo_dir).parent) as work:
        # Buildctl forwards credentials through its authenticated session for
        # private FROM images. Keep configuration outside the uploaded context.
        authfile = Path(work) / "config.json"
        host = registry_url.removeprefix("https://").removeprefix("http://").rstrip("/")
        auth = base64.b64encode(f"{username}:{password}".encode()).decode()
        fd = os.open(authfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"auths": {host: {"auth": auth}}}, stream)
        archive = str(Path(work) / "image.tar")
        cmd = build_command(repo_dir, context, dockerfile, archive, labels)
        rc, _ = await run_cmd(cmd, cwd=repo_dir, env={"DOCKER_CONFIG": work},
                              log_lines=log_lines)
        if rc:
            raise RuntimeError(f"BuildKit build failed (exit {rc})")
        digest, size = archive_identity(archive)
        for tag in (image_tag, latest_tag):
            cmd = ["skopeo", "copy", "--authfile", str(authfile)]
            # Preserve the configured HTTP development registry contract only.
            if registry_url.startswith("http://"):
                cmd.append("--dest-tls-verify=false")
            cmd.extend([f"oci-archive:{archive}", f"docker://{tag}"])
            rc, _ = await run_cmd(cmd, log_lines=log_lines)
            if rc:
                raise RuntimeError(f"Registry push failed (exit {rc})")
        return digest, size
