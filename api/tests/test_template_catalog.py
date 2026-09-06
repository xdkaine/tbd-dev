"""Source discovery must work without seeds and preserve local visibility controls."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.database import get_db
from app.middleware.auth import get_current_user
from app.routers.templates import router
from app.services import template_catalog as catalog
from app.services.rbac import Role


def database(rows=()):
    db = AsyncMock()
    result = Mock()
    result.scalars.return_value.all.return_value = list(rows)
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    return db


def row(slug, folder=None, active=True):
    return SimpleNamespace(
        id=uuid4(),
        name="Curated starter",
        slug=slug,
        description="Curated description",
        framework="nextjs",
        github_owner="xdkaine/tbd-dev",
        github_repo=folder or slug,
        icon_url=None,
        tags=[],
        sort_order=3,
        active=active,
        created_at=datetime.now(UTC),
    )


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    monkeypatch.setattr(catalog, "_cache_key", None)
    monkeypatch.setattr(catalog, "_failure_key", None)
    monkeypatch.setattr(catalog.settings, "template_source_repo", "xdkaine/tbd-dev")
    monkeypatch.setattr(catalog.settings, "template_source_branch", "main")
    monkeypatch.setattr(catalog.settings, "template_source_token", "")


def blob(path, mode="100644"):
    return {"path": path, "type": "blob", "mode": mode}


def test_discovery_requires_direct_starter_with_real_dockerfile():
    payload = {
        "tree": [
            blob("templates/react-vite-starter/Dockerfile"),
            blob("templates/react-vite-starter/vite.config.ts"),
            blob("templates/docs/README.md"),
            blob("templates/link/Dockerfile", "120000"),
            blob("templates/nested/child/Dockerfile"),
            blob("elsewhere/Dockerfile"),
            blob("templates/../Dockerfile"),
        ]
    }
    assert catalog.parse_tree(payload) == {
        "react-vite-starter": {"Dockerfile", "vite.config.ts"},
    }


@pytest.mark.parametrize("payload", [{"truncated": True, "tree": []}, {}, {"tree": [None]}])
def test_incomplete_or_malformed_tree_is_not_empty_catalog(payload):
    with pytest.raises(ValueError):
        catalog.parse_tree(payload)


@pytest.mark.parametrize(
    "files,framework",
    [
        ({"next.config.js"}, "nextjs"),
        ({"vite.config.ts"}, "react-vite"),
        ({"go.mod"}, "go"),
        ({"requirements.txt"}, "python"),
        ({"package.json"}, "nodejs"),
        ({"index.html"}, "static"),
    ],
)
def test_detects_starter_framework(files, framework):
    assert catalog.framework_for(files) == framework


async def test_empty_database_discovers_and_resolves_same_template(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "source_folders",
        AsyncMock(
            return_value=(
                {
                    "react-vite-starter": {"Dockerfile", "vite.config.ts"},
                },
                "a" * 40,
            )
        ),
    )
    db = database()
    items = await catalog.list_catalog(db)
    assert len(items) == 1
    assert items[0].github_repo == "react-vite-starter"
    assert items[0].framework == "react-vite"
    assert items[0].created_at is None
    assert (await catalog.resolve_template(db, items[0].slug)).id == items[0].id
    db.add.assert_not_called()
    db.commit.assert_not_called()


async def test_disabled_and_renamed_overrides_are_not_resurrected(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "source_folders",
        AsyncMock(
            return_value=(
                {
                    "starter": {"Dockerfile"},
                    "hidden": {"Dockerfile"},
                },
                "a" * 40,
            )
        ),
    )
    db = database([row("renamed", "starter"), row("hidden", active=False)])
    items = await catalog.list_catalog(db)
    assert [item.slug for item in items] == ["renamed"]
    assert items[0].description == "Curated description"
    for slug in ("starter", "hidden"):
        with pytest.raises(HTTPException) as error:
            await catalog.resolve_template(db, slug)
        assert error.value.status_code == 404


async def test_removed_github_folder_is_not_deployable(monkeypatch):
    monkeypatch.setattr(catalog, "source_folders", AsyncMock(return_value=({}, "a" * 40)))
    assert await catalog.list_catalog(database([row("removed")])) == []


async def test_fetch_uses_configured_source_token_branch_and_cache(monkeypatch):
    monkeypatch.setattr(catalog.settings, "template_source_branch", "feature/starter")
    monkeypatch.setattr(catalog.settings, "template_source_token", "test-source-token")
    requests = []

    def handle(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-source-token"
        assert request.url.params["recursive"] == "1"
        assert "feature%2Fstarter" in str(request.url)
        return httpx.Response(
            200, json={"sha": "a" * 40, "tree": [blob("templates/static-site/Dockerfile")]}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        catalog.httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(handle),
            **kw,
        ),
    )
    assert "static-site" in (await catalog.source_folders())[0]
    await catalog.source_folders()
    assert len(requests) == 1


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
async def test_github_errors_are_sanitized_and_not_cached(monkeypatch, status):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        catalog.httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(lambda req: httpx.Response(status, text="secret-body")),
            **kw,
        ),
    )
    with pytest.raises(HTTPException) as error:
        await catalog.source_folders()
    assert error.value.status_code == 503
    assert "secret-body" not in error.value.detail
    assert catalog._cache_key is None


async def test_list_detail_deploy_use_source_without_seeds(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "source_folders",
        AsyncMock(
            return_value=(
                {
                    "static-site": {"Dockerfile", "index.html"},
                },
                "a" * 40,
            )
        ),
    )
    app = FastAPI()
    app.include_router(router)
    db = database()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(),
        role=Role.DEVELOPER,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as ac:
        listing = await ac.get("/templates")
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        detail = await ac.get("/templates/static-site")
        assert detail.status_code == 200
        assert detail.json() == listing.json()["items"][0]
        deploy = await ac.post("/templates/static-site/deploy", json={"repo_name": "new-project"})
        # Discovery succeeds, but real account-link authorization is still required.
        assert deploy.status_code == 400
        assert "GitHub account not linked" in deploy.json()["detail"]
        missing = await ac.post("/templates/missing/deploy", json={"repo_name": "new-project"})
        assert missing.status_code == 404


async def test_unauthenticated_gallery_cannot_fetch_github(monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(catalog, "source_folders", fetch)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: database()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as ac:
        response = await ac.get("/templates")
    assert response.status_code in (401, 403)
    fetch.assert_not_called()


async def test_discovered_selection_reaches_repository_copy_with_correct_folder(monkeypatch):
    from app.routers import templates

    monkeypatch.setattr(
        catalog,
        "source_folders",
        AsyncMock(
            return_value=(
                {
                    "static-site": {"Dockerfile", "index.html"},
                },
                "a" * 40,
            )
        ),
    )
    copy_repo = AsyncMock(return_value=None)
    monkeypatch.setattr(templates, "create_repo_from_template", copy_repo)
    db = database()
    db.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(
        github_token="test-user-token",
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4(),
        role=Role.DEVELOPER,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as ac:
        response = await ac.post("/templates/static-site/deploy", json={"repo_name": "starter"})
    assert response.status_code == 422  # Mocked GitHub failure, no external mutations.
    copy_repo.assert_awaited_once_with(
        token="test-user-token",
        source_repo="xdkaine/tbd-dev",
        template_path="templates/static-site",
        new_repo_name="starter",
        new_repo_description="",
        private=False,
        source_branch="main",
        source_token=None,
        source_tree_sha="a" * 40,
    )
    db.commit.assert_not_called()


@pytest.mark.parametrize("status", [403, 429])
async def test_expired_cache_failure_backs_off_without_serving_stale_catalog(monkeypatch, status):
    clock = [0.0]
    monkeypatch.setattr(catalog, "monotonic", lambda: clock[0])
    requests = []

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "sha": "a" * 40,
                    "tree": [blob("templates/static-site/Dockerfile")],
                },
            )
        return httpx.Response(status)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        catalog.httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(handle),
            **kw,
        ),
    )
    await catalog.source_folders()
    clock[0] = 599
    await catalog.source_folders()
    assert len(requests) == 1
    clock[0] = 601
    for _ in range(3):
        with pytest.raises(HTTPException) as error:
            await catalog.source_folders()
        assert error.value.status_code == 503
    assert len(requests) == 2
    clock[0] = 662
    with pytest.raises(HTTPException):
        await catalog.source_folders()
    assert len(requests) == 3


async def test_repository_copy_uses_selected_tree_without_resolving_moving_branch(monkeypatch):
    from app.services import github

    requests = []

    def handle(request):
        requests.append((request.method, request.url.path))
        path = request.url.path
        if path == "/user/repos":
            return httpx.Response(
                201, json={"full_name": "tester/starter", "default_branch": "main"}
            )
        if path == "/repos/tester/starter/git/ref/heads/main":
            return httpx.Response(404)
        if path == "/repos/xdkaine/tbd-dev/git/trees/" + "a" * 40:
            return httpx.Response(
                200,
                json={
                    "tree": [
                        {
                            **blob("templates/static-site/Dockerfile"),
                            "sha": "b" * 40,
                        }
                    ]
                },
            )
        if path == "/repos/xdkaine/tbd-dev/git/blobs/" + "b" * 40:
            return httpx.Response(200, json={"content": "RlJPTSBuZ2lueA==", "encoding": "base64"})
        if path in (
            "/repos/tester/starter/git/blobs",
            "/repos/tester/starter/git/trees",
            "/repos/tester/starter/git/commits",
        ):
            return httpx.Response(201, json={"sha": "c" * 40})
        if path == "/repos/tester/starter/git/refs":
            return httpx.Response(201)
        raise AssertionError(f"Unexpected request: {request.method} {path}")

    original = httpx.AsyncClient
    monkeypatch.setattr(
        github.httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(handle),
            **kw,
        ),
    )
    repo = await github.create_repo_from_template(
        token="test-token",
        source_repo="xdkaine/tbd-dev",
        template_path="templates/static-site",
        new_repo_name="starter",
        source_branch="moving-branch",
        source_tree_sha="a" * 40,
    )
    assert repo is not None
    assert repo["full_name"] == "tester/starter"
    assert not any("moving-branch" in path for _, path in requests)
    assert ("GET", "/repos/xdkaine/tbd-dev/git/trees/" + "a" * 40) in requests
