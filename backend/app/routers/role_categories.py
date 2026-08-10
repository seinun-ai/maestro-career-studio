"""GET /api/role-categories — the role vocabulary, for pickers.

Exists because the vocabulary lives in ats/data/role_categories.yaml and
`frontend/lib/format.ts` deliberately declines to duplicate it — without this
endpoint no picker can be built without recreating the drift that
services/role_categories was written to end.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import role_categories

router = APIRouter(prefix="/api/role-categories", tags=["role-categories"])


class RoleCategory(BaseModel):
    key: str
    label: str
    reserved: bool = False


@router.get("", response_model=list[RoleCategory])
def list_role_categories():
    """Declared categories in file order, then the reserved other/unknown."""
    labels = role_categories.labels()
    return [
        RoleCategory(key=key, label=labels[key])
        for key in role_categories.keys()
    ] + [
        RoleCategory(key=key, label=labels[key], reserved=True)
        for key in (role_categories.OTHER, role_categories.UNKNOWN)
    ]
