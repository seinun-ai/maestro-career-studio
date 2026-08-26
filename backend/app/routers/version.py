"""GET /api/version — what this stack actually is.

Deliberately network-free. The frontend calls this on every load to compare its
own baked version against the backend's, and that check must not be able to
hang or fail because GitHub is unreachable. The opt-in upstream release check
(deferred; see the design doc) would live at /api/version/upstream precisely
so the two keep separate failure domains.
"""

import os
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/api/version", tags=["version"])


class VersionInfo(BaseModel):
    version: str
    git_sha: str | None
    schema_revision: str


@router.get("", response_model=VersionInfo)
def get_version(db: Annotated[Session, Depends(get_db)]):
    # A local build has no APP_VERSION; "dev" is a load-bearing value, not a
    # placeholder — the frontend suppresses its version-mismatch banner when
    # either side STARTS WITH "dev" ("dev" locally, "dev-<sha>" from a
    # workflow_dispatch image), because those builds bind-mount or float free
    # of any release and a mismatch there means nothing.
    revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return VersionInfo(
        version=os.environ.get("APP_VERSION", "dev"),
        git_sha=os.environ.get("APP_GIT_SHA") or None,
        schema_revision=revision or "unknown",
    )
