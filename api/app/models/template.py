"""Template model — curated starter project catalog."""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Template(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A curated starter template that users can deploy as a new project.

    Template files are stored in the main TBD repo under templates/<slug>/.
    When a user deploys a template, TBD creates a new repo in the user's
    GitHub account, pushes the template files as an initial commit (via
    the Git Data API), then creates a project and triggers a build+deploy.

    The source repo is configured via TEMPLATE_SOURCE_REPO in settings.
    The github_repo column stores the template directory name (slug).
    """

    __tablename__ = "templates"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    framework: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Framework identifier: nextjs, react-vite, python, nodejs, go, static",
    )

    # GitHub template source coordinates
    github_owner: Mapped[str] = mapped_column(
        String(255), nullable=False, default="xdkaine/tbd-dev",
        comment="Source repo (legacy column — source repo is now in settings)",
    )
    github_repo: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Template directory name under templates/ in the source repo",
    )

    # Display
    icon_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
