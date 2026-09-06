"""Discover deployable starter folders from the configured GitHub source.

Database rows are optional presentation/visibility overrides, not catalog seeds.
Only ordinary files in direct templates/<slug>/ folders are considered.
"""

import asyncio
import hashlib
import re
from time import monotonic
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.template import Template
from app.schemas.template import TemplateResponse

_cache_key: tuple[str, str, str] | None = None
_cache_until = 0.0
_cache: tuple[dict[str, set[str]], str] = ({}, "")
_failure_key: tuple[str, str, str] | None = None
_failure_until = 0.0
_lock = asyncio.Lock()


def parse_tree(payload: dict) -> dict[str, set[str]]:
    """Reject incomplete responses rather than silently hiding starters."""
    if payload.get("truncated") or not isinstance(payload.get("tree"), list):
        raise ValueError("Incomplete GitHub tree")
    folders: dict[str, set[str]] = {}
    for entry in payload["tree"]:
        if not isinstance(entry, dict):
            raise ValueError("Invalid GitHub tree entry")
        path = entry.get("path", "")
        if not isinstance(path, str):
            raise ValueError("Invalid GitHub tree path")
        parts = path.split("/", 2)
        if (
            len(parts) == 3
            and parts[0] == "templates"
            and re.fullmatch(r"[a-z0-9-]+", parts[1])
            and entry.get("type") == "blob"
            and entry.get("mode") in ("100644", "100755")
        ):
            folders.setdefault(parts[1], set()).add(parts[2])
    return {slug: files for slug, files in folders.items() if "Dockerfile" in files}


async def source_folders() -> tuple[dict[str, set[str]], str]:
    global _cache_key, _cache_until, _cache, _failure_key, _failure_until
    repo = settings.template_source_repo
    branch = settings.template_source_branch
    token = settings.template_source_token
    key = (repo, branch, hashlib.sha256(token.encode()).hexdigest())
    async with _lock:
        if key == _cache_key and monotonic() < _cache_until:
            return _cache
        if key == _failure_key and monotonic() < _failure_until:
            raise HTTPException(
                status_code=503,
                detail="Could not load templates from GitHub. Please try again later.",
            )
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        url = (
            f"https://api.github.com/repos/{quote(repo, safe='/')}/git/trees/"
            f"{quote(branch, safe='')}"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params={"recursive": "1"}, headers=headers)
                response.raise_for_status()
                payload = response.json()
                folders = parse_tree(payload)
                tree_sha = payload.get("sha", "")
                if not isinstance(tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
                    raise ValueError("Missing GitHub tree identity")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            _failure_key, _failure_until = key, monotonic() + 60
            # Never forward GitHub response bodies, request headers, or credentials.
            raise HTTPException(
                status_code=503,
                detail="Could not load templates from GitHub. Please try again later.",
            ) from exc
        _failure_key, _failure_until = None, 0.0
        _cache_key, _cache_until, _cache = key, monotonic() + 600, (folders, tree_sha)
        return _cache


def framework_for(files: set[str]) -> str:
    if any(name.startswith("next.config.") for name in files):
        return "nextjs"
    if any(name.startswith("vite.config.") for name in files):
        return "react-vite"
    if "go.mod" in files:
        return "go"
    if files & {"requirements.txt", "pyproject.toml"}:
        return "python"
    if "package.json" in files:
        return "nodejs"
    return "static"


async def list_catalog(db: AsyncSession) -> list[TemplateResponse]:
    folders, tree_sha = await source_folders()
    rows = (await db.execute(select(Template))).scalars().all()
    # Reserve every configured slug, including disabled entries, so discovery
    # cannot accidentally resurrect it under its original directory name.
    reserved = {row.slug for row in rows}
    overridden = {row.github_repo for row in rows}
    items = [
        TemplateResponse.model_validate(row)
        for row in rows
        if row.active and row.github_repo in folders
    ]
    for slug, files in folders.items():
        if slug in overridden or slug in reserved:
            continue
        items.append(
            TemplateResponse(
                id=uuid5(NAMESPACE_URL, f"{settings.template_source_repo}/templates/{slug}"),
                name=slug.replace("-", " ").title(),
                slug=slug,
                description="",
                framework=framework_for(files),
                github_owner=settings.template_source_repo,
                github_repo=slug,
                created_at=None,
            )
        )
    for item in items:
        item._source_tree_sha = tree_sha
    return sorted(items, key=lambda item: (item.sort_order, item.name, item.slug))


async def resolve_template(db: AsyncSession, slug: str) -> TemplateResponse:
    for template in await list_catalog(db):
        if template.slug == slug:
            return template
    raise HTTPException(status_code=404, detail="Template not found")
