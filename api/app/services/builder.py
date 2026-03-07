"""Built-in build service.

Clones a GitHub repo, detects framework, builds a Docker image,
pushes to the internal registry, and creates an artifact record.
Runs as a background task triggered by webhooks or manual builds.
"""

import asyncio
import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.build import Artifact, Build
from app.models.project import Project, Repo
from app.services.audit import write_audit_log
from app.services.github import get_owner_github_token

logger = logging.getLogger(__name__)

BUILD_WORK_DIR = "/var/lib/tbd/builds"

# ---------------------------------------------------------------------------
# Concurrency control — prevents OOM from unbounded parallel builds/deploys
# ---------------------------------------------------------------------------

_build_semaphore: asyncio.Semaphore | None = None
_deploy_semaphore: asyncio.Semaphore | None = None


def _get_build_semaphore() -> asyncio.Semaphore:
    """Lazy-initialise the build semaphore (must happen inside a running event loop)."""
    global _build_semaphore
    if _build_semaphore is None:
        _build_semaphore = asyncio.Semaphore(settings.build_max_concurrent)
    return _build_semaphore


def _get_deploy_semaphore() -> asyncio.Semaphore:
    """Lazy-initialise the deploy semaphore (must happen inside a running event loop).

    Limits concurrent deploy executions independently of builds so that
    finishing a Docker build frees the build slot immediately while deploys
    queue behind their own limit.
    """
    global _deploy_semaphore
    if _deploy_semaphore is None:
        _deploy_semaphore = asyncio.Semaphore(settings.deploy_max_concurrent)
    return _deploy_semaphore


async def launch_build(build_id: uuid.UUID) -> None:
    """Launch a build as a background task with concurrency and timeout limits.

    This is the single entry-point that all routers should use instead of
    calling ``asyncio.create_task(_launch_builder(...))`` directly.

    Guarantees:
    - At most ``settings.build_max_concurrent`` builds run simultaneously.
    - Each build is hard-killed after ``settings.build_timeout_seconds``.
    """
    async def _guarded_build() -> None:
        from app.database import async_session_factory

        sem = _get_build_semaphore()
        async with sem:
            try:
                async with async_session_factory() as db:
                    await asyncio.wait_for(
                        run_build(build_id, db),
                        timeout=settings.build_timeout_seconds,
                    )
                    await db.commit()
            except asyncio.TimeoutError:
                logger.error(
                    "Build %s timed out after %ds",
                    build_id, settings.build_timeout_seconds,
                )
                # Mark build as failed
                try:
                    async with async_session_factory() as db:
                        result = await db.execute(
                            select(Build).where(Build.id == build_id)
                        )
                        build = result.scalar_one_or_none()
                        if build and build.status not in ("success", "failed"):
                            build.status = "failed"
                            build.finished_at = datetime.now(timezone.utc)
                            timeout_msg = (
                                f"Build timed out after {settings.build_timeout_seconds}s"
                            )
                            build.logs = (
                                (build.logs or "") + f"\n[TIMEOUT] {timeout_msg}"
                            )
                            await db.commit()
                except Exception:
                    logger.exception("Failed to mark timed-out build %s as failed", build_id)
            except Exception:
                logger.exception("Background builder failed for build %s", build_id)

    asyncio.create_task(_guarded_build())


async def _launch_deploy_background(
    deploy_id: uuid.UUID,
    artifact_id: uuid.UUID,
    build_id: uuid.UUID,
    project_id: uuid.UUID,
    env_id: uuid.UUID,
) -> None:
    """Run the deploy executor as a standalone background task.

    This runs *outside* the build semaphore so that ongoing deploys do not
    block new builds.  It has its own concurrency gate (_deploy_semaphore)
    to bound resource usage.
    """
    from app.database import async_session_factory

    sem = _get_deploy_semaphore()
    async with sem:
        try:
            async with async_session_factory() as db:
                from sqlalchemy.orm import selectinload

                from app.models.build import Artifact, Build
                from app.models.deploy import Deploy
                from app.models.environment import Environment
                from app.models.project import Project
                from app.services.deploy_executor import DeployContext, execute_deploy

                # Re-load all records in this fresh session
                deploy = (
                    await db.execute(select(Deploy).where(Deploy.id == deploy_id))
                ).scalar_one()
                artifact = (
                    await db.execute(select(Artifact).where(Artifact.id == artifact_id))
                ).scalar_one()
                build = (
                    await db.execute(select(Build).where(Build.id == build_id))
                ).scalar_one()
                project = (
                    await db.execute(
                        select(Project)
                        .options(selectinload(Project.owner))
                        .where(Project.id == project_id)
                    )
                ).scalar_one()
                environment = (
                    await db.execute(select(Environment).where(Environment.id == env_id))
                ).scalar_one()

                ctx = DeployContext(
                    deploy=deploy,
                    artifact=artifact,
                    build=build,
                    project=project,
                    environment=environment,
                )
                await execute_deploy(db, ctx)
                await db.commit()
        except Exception:
            logger.exception(
                "Background deploy failed for deploy %s (build %s)",
                deploy_id, build_id,
            )


# ---------------------------------------------------------------------------
# Build context detection result
# ---------------------------------------------------------------------------

@dataclass
class BuildInfo:
    """Result of framework/build-context detection."""
    framework: str                # dockerfile, nextjs, react, python, node, go, static, unknown
    build_context: str = "."      # Relative path from repo root to build context dir
    dockerfile_path: str | None = None  # Relative path from repo root to Dockerfile (None = auto)


# ---------------------------------------------------------------------------
# Framework detection
# ---------------------------------------------------------------------------

FRAMEWORKS = {
    "nextjs": {
        "detect_files": ["next.config.js", "next.config.mjs", "next.config.ts"],
        "detect_deps": ["next"],
    },
    "react": {
        "detect_files": [],
        "detect_deps": ["react-scripts", "vite"],
    },
    "python": {
        "detect_files": ["requirements.txt", "pyproject.toml", "Pipfile", "setup.py"],
        "detect_deps": [],
    },
    "node": {
        "detect_files": ["package.json"],
        "detect_deps": [],
    },
    "go": {
        "detect_files": ["go.mod"],
        "detect_deps": [],
    },
    "static": {
        "detect_files": ["index.html"],
        "detect_deps": [],
    },
}

# Common subdirectories where app code may live
_COMMON_SUBDIRS = ["app", "src", "frontend", "backend", "web", "server", "api"]


def _detect_framework_in_dir(dir_path: Path) -> str:
    """Detect the project framework from files in a single directory.

    Returns one of: dockerfile, nextjs, react, python, node, go, static, unknown
    """
    # If there's a Dockerfile, always use it
    if (dir_path / "Dockerfile").exists():
        return "dockerfile"

    # Check package.json for JS frameworks
    pkg_json = dir_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            # Next.js
            if "next" in deps:
                return "nextjs"

            # React (CRA or Vite)
            if "react-scripts" in deps or ("vite" in deps and "react" in deps):
                return "react"

            # Generic Node.js
            return "node"
        except Exception:
            return "node"

    # Python
    for f in ["requirements.txt", "pyproject.toml", "Pipfile", "setup.py"]:
        if (dir_path / f).exists():
            return "python"

    # Go
    if (dir_path / "go.mod").exists():
        return "go"

    # Static site
    if (dir_path / "index.html").exists():
        return "static"

    return "unknown"


def _parse_compose_build_context(repo_path: Path) -> BuildInfo | None:
    """Parse docker-compose.yml to extract build context and Dockerfile path.

    Looks for the first service with a `build` key and returns its context
    and dockerfile paths. Returns None if no compose file or no build config.
    """
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        compose_file = repo_path / name
        if compose_file.exists():
            break
    else:
        return None

    try:
        data = yaml.safe_load(compose_file.read_text())
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    services = data.get("services", {})
    if not isinstance(services, dict):
        return None

    # Find the first service with a build config
    for svc_name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        build_cfg = svc.get("build")
        if build_cfg is None:
            continue

        # `build` can be a string (just the context) or a dict
        if isinstance(build_cfg, str):
            context = build_cfg
            dockerfile_rel = None
        elif isinstance(build_cfg, dict):
            context = build_cfg.get("context", ".")
            dockerfile_rel = build_cfg.get("dockerfile")
        else:
            continue

        # Normalize context path (strip ./ prefix and trailing /)
        context = context.strip("/")
        if context.startswith("./"):
            context = context[2:]
        if not context or context == ".":
            context = "."
            context_dir = repo_path
        else:
            context_dir = repo_path / context

        if not context_dir.is_dir():
            continue

        # Resolve dockerfile path relative to repo root
        if dockerfile_rel:
            # dockerfile path is relative to the context dir
            df_abs = context_dir / dockerfile_rel
            if df_abs.exists():
                dockerfile_path = str(df_abs.relative_to(repo_path))
            else:
                dockerfile_path = None
        else:
            # Default: Dockerfile inside the context dir
            df_abs = context_dir / "Dockerfile"
            if df_abs.exists():
                dockerfile_path = str(df_abs.relative_to(repo_path))
            else:
                dockerfile_path = None

        # Detect framework within the context dir
        framework = _detect_framework_in_dir(context_dir)

        # If we found a Dockerfile path from compose but _detect_framework_in_dir
        # didn't find a Dockerfile (e.g., context: . with dockerfile: app/Dockerfile),
        # override to "dockerfile" since we know one exists
        if framework == "unknown" and dockerfile_path:
            framework = "dockerfile"

        return BuildInfo(
            framework=framework,
            build_context=context,
            dockerfile_path=dockerfile_path,
        )

    return None


def detect_framework(repo_dir: str) -> BuildInfo:
    """Detect the project framework, build context, and Dockerfile location.

    Search order:
    1. Root directory (existing behavior)
    2. docker-compose.yml build config (extracts context + dockerfile path)
    3. Common subdirectories (app/, src/, frontend/, etc.)

    Returns a BuildInfo with framework name, build context, and Dockerfile path.
    """
    repo_path = Path(repo_dir)

    # --- 1. Check root directory first ---
    root_fw = _detect_framework_in_dir(repo_path)
    if root_fw != "unknown":
        info = BuildInfo(framework=root_fw, build_context=".")
        if root_fw == "dockerfile":
            info.dockerfile_path = "Dockerfile"
        return info

    # --- 2. Parse docker-compose.yml for build context ---
    compose_info = _parse_compose_build_context(repo_path)
    if compose_info is not None:
        logger.info(
            "Detected build context from docker-compose: context=%s, dockerfile=%s, framework=%s",
            compose_info.build_context, compose_info.dockerfile_path, compose_info.framework,
        )
        return compose_info

    # --- 3. Scan common subdirectories ---
    for subdir in _COMMON_SUBDIRS:
        sub_path = repo_path / subdir
        if not sub_path.is_dir():
            continue

        sub_fw = _detect_framework_in_dir(sub_path)
        if sub_fw != "unknown":
            info = BuildInfo(framework=sub_fw, build_context=subdir)
            if sub_fw == "dockerfile":
                info.dockerfile_path = f"{subdir}/Dockerfile"
            return info

    return BuildInfo(framework="unknown")


# ---------------------------------------------------------------------------
# Dockerfile generation for detected frameworks
# ---------------------------------------------------------------------------

DOCKERFILE_TEMPLATES = {
    "nextjs": """\
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# Ensure output: "standalone" is set (required for containerised deploys).
# Handles next.config.ts / .mjs / .js — flexible regex covers type annotations.
RUN for f in next.config.ts next.config.mjs next.config.js; do \
      if [ -f "$f" ]; then \
        if ! grep -q 'standalone' "$f"; then \
          sed -i '/nextConfig/s/{/{\\n  output: "standalone",/' "$f" || true; \
          if ! grep -q 'standalone' "$f"; then \
            sed -i '/module\\.exports/s/{/{\\n  output: "standalone",/' "$f" || true; \
          fi; \
          if ! grep -q 'standalone' "$f"; then \
            sed -i '/export default/s/{/{\\n  output: "standalone",/' "$f" || true; \
          fi; \
        fi; \
        break; \
      fi; \
    done
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
""",
    "react": """\
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build

FROM nginx:1.25-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=builder /app/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
""",
    "python": """\
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt* pyproject.toml* ./
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; \\
    elif [ -f pyproject.toml ]; then pip install --no-cache-dir .; fi
COPY . .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
    "node": """\
FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --production; else npm install --production; fi
COPY . .
EXPOSE 3000
CMD ["node", "index.js"]
""",
    "go": """\
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /app/server .

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /app/server .
EXPOSE 8080
CMD ["./server"]
""",
    "static": """\
FROM nginx:1.25-alpine
COPY . /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
""",
}


def generate_dockerfile(
    framework: str,
    build_context_dir: str,
    *,
    install_command: str | None = None,
    build_command: str | None = None,
    output_directory: str | None = None,
) -> str | None:
    """Generate a Dockerfile for the detected framework.

    Writes the Dockerfile into the build context directory.
    Returns the Dockerfile content, or None if the framework has
    a Dockerfile already or is unknown.

    When ``install_command``, ``build_command``, or ``output_directory`` are
    provided they override the corresponding default steps in the template.
    """
    if framework == "dockerfile" or framework == "unknown":
        return None

    template = DOCKERFILE_TEMPLATES.get(framework)
    if not template:
        return None

    # --- Apply per-project overrides ---
    if install_command:
        template = _replace_install_step(framework, template, install_command)
    if build_command:
        template = _replace_build_step(framework, template, build_command)
    if output_directory:
        template = _replace_output_dir(framework, template, output_directory)

    # Write generated Dockerfile into the build context directory
    dockerfile_path = os.path.join(build_context_dir, "Dockerfile")
    with open(dockerfile_path, "w") as f:
        f.write(template)

    return template


# ---------------------------------------------------------------------------
# Dockerfile template override helpers
# ---------------------------------------------------------------------------

def _replace_install_step(framework: str, template: str, install_cmd: str) -> str:
    """Replace the default install command in the Dockerfile template."""
    replacements = {
        "nextjs": (
            "RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi",
            f"RUN {install_cmd}",
        ),
        "react": (
            "RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi",
            f"RUN {install_cmd}",
        ),
        "node": (
            "RUN if [ -f package-lock.json ]; then npm ci --production; else npm install --production; fi",
            f"RUN {install_cmd}",
        ),
        "python": (
            'RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; \\\n'
            '    elif [ -f pyproject.toml ]; then pip install --no-cache-dir .; fi',
            f"RUN {install_cmd}",
        ),
        "go": (
            "RUN go mod download",
            f"RUN {install_cmd}",
        ),
    }
    old, new = replacements.get(framework, (None, None))
    if old and old in template:
        template = template.replace(old, new)
    return template


def _replace_build_step(framework: str, template: str, build_cmd: str) -> str:
    """Replace the default build command in the Dockerfile template."""
    replacements = {
        "nextjs": ("RUN npm run build", f"RUN {build_cmd}"),
        "react": ("RUN npm run build", f"RUN {build_cmd}"),
        "go": (
            "RUN CGO_ENABLED=0 go build -o /app/server .",
            f"RUN {build_cmd}",
        ),
    }
    old, new = replacements.get(framework, (None, None))
    if old and old in template:
        template = template.replace(old, new)
    return template


def _replace_output_dir(framework: str, template: str, output_dir: str) -> str:
    """Replace the default output directory in the Dockerfile template.

    For react/static builds this changes where built files are copied from.
    For Next.js this adjusts the standalone copy source.
    """
    if framework == "react":
        # Default copies from /app/dist and /app/build — replace with custom dir
        template = template.replace(
            "COPY --from=builder /app/dist /usr/share/nginx/html\n"
            "COPY --from=builder /app/build /usr/share/nginx/html",
            f"COPY --from=builder /app/{output_dir} /usr/share/nginx/html",
        )
    elif framework == "static":
        template = template.replace(
            "COPY . /usr/share/nginx/html",
            f"COPY ./{output_dir} /usr/share/nginx/html",
        )
    # For nextjs, output_directory is less common — the standalone output
    # structure is fixed by Next.js. Skip for now.
    return template


# ---------------------------------------------------------------------------
# Build execution
# ---------------------------------------------------------------------------


async def _run_cmd(
    cmd: list[str],
    cwd: str | None = None,
    env: dict | None = None,
    log_lines: list[str] | None = None,
    stdin_data: str | None = None,
) -> tuple[int, str]:
    """Run a subprocess, capture output, and optionally append to log_lines."""
    full_env = {**os.environ, **(env or {})}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if stdin_data else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
        env=full_env,
    )

    output_lines = []
    # Feed stdin data if provided (e.g., for --password-stdin)
    if stdin_data and proc.stdin:
        proc.stdin.write(stdin_data.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").rstrip()
        output_lines.append(decoded)
        if log_lines is not None:
            log_lines.append(decoded)
        # Log first 500 lines to avoid flooding
        if len(output_lines) <= 500:
            logger.debug("[build] %s", decoded)

    await proc.wait()
    return proc.returncode, "\n".join(output_lines)


async def run_build(build_id: uuid.UUID, db: AsyncSession) -> None:
    """Execute a full build pipeline for the given build ID.

    Steps:
    1. Look up build, project, and repo
    2. Clone repository
    3. Detect framework
    4. Build Docker image
    5. Push image to registry
    6. Create artifact record
    7. Save build logs

    This function is designed to be called as a background task.
    """
    log_lines: list[str] = []

    def log(msg: str):
        logger.info("[build %s] %s", str(build_id)[:8], msg)
        log_lines.append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}")

    async def flush_logs(build_obj: Build):
        """Write current log_lines to the DB so the logs endpoint returns live data."""
        build_obj.logs = "\n".join(log_lines)
        await db.flush()

    try:
        # --- Step 1: Look up build + project + repo ---
        result = await db.execute(select(Build).where(Build.id == build_id))
        build = result.scalar_one_or_none()
        if not build:
            logger.error("Build %s not found", build_id)
            return

        result = await db.execute(
            select(Project).options(selectinload(Project.owner)).where(Project.id == build.project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            log("ERROR: Project not found")
            build.status = "failed"
            build.logs = "\n".join(log_lines)
            build.finished_at = datetime.now(timezone.utc)
            await db.flush()
            return

        result = await db.execute(
            select(Repo).where(Repo.project_id == project.id)
        )
        repo = result.scalar_one_or_none()
        if not repo or not repo.repo_full_name:
            log("ERROR: No GitHub repo linked to project")
            build.status = "failed"
            build.logs = "\n".join(log_lines)
            build.finished_at = datetime.now(timezone.utc)
            await db.flush()
            return

        # Transition to building
        build.status = "building"
        build.started_at = datetime.now(timezone.utc)
        await db.flush()

        log(f"Starting build for {repo.repo_full_name} @ {build.commit_sha[:8]}")

        # --- Step 2: Clone repo ---
        work_dir = os.path.join(BUILD_WORK_DIR, str(build_id))
        os.makedirs(work_dir, exist_ok=True)
        repo_dir = os.path.join(work_dir, "repo")

        log("Cloning repository...")
        clone_url = f"https://github.com/{repo.repo_full_name}.git"

        # Get project owner's OAuth token for private repo access
        owner_token = await get_owner_github_token(db, project.id)
        if owner_token:
            clone_url = f"https://x-access-token:{owner_token}@github.com/{repo.repo_full_name}.git"
        else:
            log("WARNING: No owner OAuth token found, attempting public clone")

        rc, output = await _run_cmd(
            ["git", "clone", "--depth=1", f"--branch={repo.default_branch}", clone_url, repo_dir],
            log_lines=log_lines,
        )
        if rc != 0:
            log(f"ERROR: git clone failed (exit {rc})")
            build.status = "failed"
            build.logs = "\n".join(log_lines)
            build.finished_at = datetime.now(timezone.utc)
            await db.flush()
            return

        # Checkout specific commit if it differs from HEAD
        rc, _ = await _run_cmd(
            ["git", "checkout", build.commit_sha],
            cwd=repo_dir,
            log_lines=log_lines,
        )
        # Checkout may fail if commit_sha is the latest on the branch — that's OK

        log("Clone complete")
        await flush_logs(build)

        # --- Step 3: Detect framework ---
        # If project has a root_directory override, use it as the build context
        # instead of auto-detecting from the repo root.
        if project.root_directory:
            root_dir_path = os.path.join(repo_dir, project.root_directory)
            if not os.path.isdir(root_dir_path):
                log(f"ERROR: Configured root_directory '{project.root_directory}' not found in repo")
                build.status = "failed"
                build.logs = "\n".join(log_lines)
                build.finished_at = datetime.now(timezone.utc)
                await db.flush()
                return
            # Detect framework within the specified root directory
            framework = _detect_framework_in_dir(Path(root_dir_path))
            build_info = BuildInfo(
                framework=framework,
                build_context=project.root_directory,
                dockerfile_path=(
                    f"{project.root_directory}/Dockerfile"
                    if framework == "dockerfile"
                    else None
                ),
            )
            log(f"Using configured root_directory: {project.root_directory}")
        else:
            build_info = detect_framework(repo_dir)

        log(f"Detected framework: {build_info.framework}")
        if build_info.build_context != ".":
            log(f"Build context: {build_info.build_context}")
        if build_info.dockerfile_path:
            log(f"Dockerfile: {build_info.dockerfile_path}")

        # Log any per-project build overrides
        if project.install_command:
            log(f"Install command override: {project.install_command}")
        if project.build_command:
            log(f"Build command override: {project.build_command}")
        if project.output_directory:
            log(f"Output directory override: {project.output_directory}")

        # Resolve absolute paths for build context and Dockerfile
        if build_info.build_context == ".":
            build_context_abs = repo_dir
        else:
            build_context_abs = os.path.join(repo_dir, build_info.build_context)

        # Update project framework if not already set
        if not project.framework:
            project.framework = build_info.framework
            await db.flush()

        # Generate Dockerfile if needed (written into build context dir)
        # Pass per-project overrides so the template uses custom commands.
        if build_info.framework != "dockerfile":
            template = generate_dockerfile(
                build_info.framework,
                build_context_abs,
                install_command=project.install_command,
                build_command=project.build_command,
                output_directory=project.output_directory,
            )
            if template:
                log(f"Generated Dockerfile for {build_info.framework}")
                # Update build_info since we just created a Dockerfile
                build_info.dockerfile_path = os.path.join(
                    build_info.build_context, "Dockerfile"
                ) if build_info.build_context != "." else "Dockerfile"
            elif build_info.framework == "unknown":
                log("ERROR: No Dockerfile found and framework not recognized")
                build.status = "failed"
                build.logs = "\n".join(log_lines)
                build.finished_at = datetime.now(timezone.utc)
                await db.flush()
                return

        # --- Step 4: Build Docker image ---
        log(f"Building image (this may take a while)...")
        await flush_logs(build)

        registry_host = settings.registry_url.replace("http://", "").replace("https://", "")
        image_tag = f"{registry_host}/{project.slug}:{build.commit_sha[:8]}"
        latest_tag = f"{registry_host}/{project.slug}:latest"

        log(f"Building image: {image_tag}")

        # Build the docker build command with correct context and Dockerfile
        docker_build_cmd = [
            "docker", "build",
            "-t", image_tag,
            "-t", latest_tag,
            "--label", f"tbd.project={project.slug}",
            "--label", f"tbd.build={str(build_id)}",
            "--label", f"tbd.commit={build.commit_sha[:8]}",
        ]

        # Add -f flag when Dockerfile is not at the default location
        # Docker looks for "Dockerfile" in the build context root by default.
        # We need -f when: (a) build context is not root, or (b) Dockerfile
        # is not named "Dockerfile" at the build context root.
        if build_info.dockerfile_path:
            # Check if Dockerfile is at the default location for the build context
            if build_info.build_context == ".":
                default_df = "Dockerfile"
            else:
                default_df = f"{build_info.build_context}/Dockerfile"
            if build_info.dockerfile_path != default_df:
                docker_build_cmd.extend(["-f", build_info.dockerfile_path])

        # Build context is relative to repo root
        docker_build_cmd.append(
            build_info.build_context if build_info.build_context != "." else "."
        )

        rc, _ = await _run_cmd(
            docker_build_cmd,
            cwd=repo_dir,
            log_lines=log_lines,
        )
        if rc != 0:
            log(f"ERROR: docker build failed (exit {rc})")
            build.status = "failed"
            build.logs = "\n".join(log_lines)
            build.finished_at = datetime.now(timezone.utc)
            await db.flush()
            return

        log("Build complete")
        await flush_logs(build)

        # --- Step 5: Push to registry ---
        # Login to registry if credentials are configured
        if settings.registry_username and settings.registry_password:
            log("Authenticating with registry...")
            rc, _ = await _run_cmd(
                [
                    "docker", "login", registry_host,
                    "-u", settings.registry_username,
                    "--password-stdin",
                ],
                log_lines=log_lines,
                stdin_data=settings.registry_password,
            )
            if rc != 0:
                log("WARNING: Registry login failed, push may fail")

        log(f"Pushing image to registry...")
        rc, _ = await _run_cmd(
            ["docker", "push", image_tag],
            log_lines=log_lines,
        )
        if rc != 0:
            log(f"ERROR: docker push failed (exit {rc})")
            build.status = "failed"
            build.logs = "\n".join(log_lines)
            build.finished_at = datetime.now(timezone.utc)
            await db.flush()
            return

        # Also push latest tag
        await _run_cmd(
            ["docker", "push", latest_tag],
            log_lines=log_lines,
        )

        log("Push complete")
        await flush_logs(build)

        # --- Step 6: Get image digest ---
        rc, digest_output = await _run_cmd(
            ["docker", "inspect", "--format={{.Id}}", image_tag],
        )
        image_digest = digest_output.strip() if rc == 0 else f"sha256:{build.commit_sha}"

        # Get image size
        rc, size_output = await _run_cmd(
            ["docker", "inspect", "--format={{.Size}}", image_tag],
        )
        image_size = int(size_output.strip()) if rc == 0 and size_output.strip().isdigit() else 0

        # --- Step 7: Create artifact record ---
        build.image_ref = image_tag
        build.status = "success"
        build.finished_at = datetime.now(timezone.utc)
        build.logs = "\n".join(log_lines)

        artifact = Artifact(
            build_id=build_id,
            image_ref=image_tag,
            sha256=image_digest,
            size=image_size,
            stored_at=datetime.now(timezone.utc),
        )
        db.add(artifact)
        await db.flush()

        log(f"Artifact created: {image_tag} ({image_size / 1024 / 1024:.1f} MB)")

        await write_audit_log(
            db,
            actor_user_id=None,
            action="build.complete",
            target_type="build",
            target_id=str(build_id),
            payload={
                "project_id": str(project.id),
                "image_ref": image_tag,
                "framework": build_info.framework,
                "sha256": image_digest,
                "size": image_size,
            },
        )

        log("Build pipeline complete!")

        # --- Step 8: Auto-deploy if enabled ---
        # IMPORTANT: Deploy runs as a *separate* background task so the
        # build semaphore slot is freed immediately.  The deploy has its
        # own concurrency gate (_deploy_semaphore) to prevent OOM from
        # unbounded parallel deploys.
        if project.auto_deploy:
            log("Auto-deploy enabled, triggering deploy...")
            await flush_logs(build)
            from app.services.build_coordinator import trigger_deploy, ContainerLimitError
            try:

                deploy = await trigger_deploy(
                    db,
                    project=project,
                    build=build,
                    artifact=artifact,
                    env_name=project.default_env,
                    actor_user_id=None,
                )
                log(f"Deploy {deploy.id} created (status={deploy.status}, url={deploy.url})")

                # Capture IDs needed by the background deploy task.
                # We do NOT await execute_deploy here — it will run in
                # its own task with its own DB session after the build
                # semaphore is released.
                _deploy_id = deploy.id
                _artifact_id = artifact.id
                _build_id = build.id
                _project_id = project.id
                _env_id = deploy.env_id

                # Commit now so the deploy/build/artifact rows are
                # visible to the background task's independent session.
                # The outer _guarded_build() commit becomes a no-op.
                await db.commit()

                asyncio.create_task(
                    _launch_deploy_background(
                        deploy_id=_deploy_id,
                        artifact_id=_artifact_id,
                        build_id=_build_id,
                        project_id=_project_id,
                        env_id=_env_id,
                    )
                )
                log("Deploy task spawned (running outside build semaphore)")
            except ContainerLimitError as e:
                log(f"Auto-deploy skipped: {e}")
                logger.info("Auto-deploy skipped for build %s: container limit reached", build_id)
            except Exception as e:
                log(f"WARNING: Auto-deploy failed: {e}")
                logger.exception("Auto-deploy failed for build %s", build_id)

    except Exception as e:
        logger.exception("Build %s failed with exception", build_id)
        log_lines.append(f"FATAL: {str(e)}")

        # Try to update build status
        try:
            result = await db.execute(select(Build).where(Build.id == build_id))
            build = result.scalar_one_or_none()
            if build:
                build.status = "failed"
                build.finished_at = datetime.now(timezone.utc)
                build.logs = "\n".join(log_lines)
                await db.flush()
        except Exception:
            logger.exception("Failed to update build status after error")

    finally:
        # Cleanup work directory
        work_dir = os.path.join(BUILD_WORK_DIR, str(build_id))
        try:
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass
