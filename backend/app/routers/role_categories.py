"""GET /api/role-categories — the role vocabulary, for pickers.

Exists because the vocabulary lives in ats/data/role_categories.yaml and
`frontend/lib/format.ts` deliberately declines to duplicate it — without this
endpoint no picker can be built without recreating the drift that
services/role_categories was written to end.

`/match` is here for the same reason: mapping typed text onto the vocabulary
runs on the same slug + alias map as everything else, and reimplementing that
in TypeScript would be the fourth vocabulary.
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.schemas.job_preferences import MAX_LABEL_CHARS
from app.services import role_categories

router = APIRouter(prefix="/api/role-categories", tags=["role-categories"])


class CatalogRole(BaseModel):
    key: str
    label: str


class RoleCategory(BaseModel):
    key: str
    label: str
    reserved: bool = False
    # Additive on purpose: RoleCategoryPicker sets the BASE-RESUME role, which
    # must stay coarse because it is a stored, validated column. That component
    # ignores this field; only the job-preferences picker reads it.
    roles: list[CatalogRole] = []


# Named ...Response rather than RoleMatch: the service already owns a `RoleMatch`
# TypedDict and the frontend type will be a third. One name across three layers
# guarantees someone imports the wrong one.
class RoleMatchResponse(BaseModel):
    role: str | None
    category: str | None
    label: str
    # Imported from the service rather than redeclared, so the producer owns the
    # vocabulary and a typo is an author-time error instead of a 500 at response
    # validation. NB "none" is TRUTHY in JavaScript — clients must compare
    # against the string, never test this field for falsiness.
    confidence: role_categories.Confidence


@router.get("", response_model=list[RoleCategory])
def list_role_categories():
    """Declared categories in file order, then the reserved other/unknown."""
    labels = role_categories.labels()
    return [
        RoleCategory(
            key=key,
            label=labels[key],
            roles=[CatalogRole(**role) for role in role_categories.roles_for(key)],
        )
        for key in role_categories.keys()
    ] + [
        RoleCategory(key=key, label=labels[key], reserved=True)
        for key in (role_categories.OTHER, role_categories.UNKNOWN)
    ]


@router.get("/match", response_model=RoleMatchResponse)
def match_role_text(q: str = Query(default="", max_length=MAX_LABEL_CHARS)):
    """Map typed text onto the vocabulary, for the custom-role suggestion.

    A MISS is 200, never a 4xx: `confidence: "none"` is a normal successful
    answer meaning "we do not know this role", and the picker keeps it as an
    unmapped custom entry. Treating a miss as an error would push the client
    toward inventing a mapping, which is the one thing this must not do.

    An over-long `q` IS a 422, and the bound is deliberately the same constant
    the preference label is capped at. On a miss this text becomes the label of
    a custom `FavoredRole`, and that schema REJECTS over-80 rather than
    truncating — so a looser bound here would hand back a 200 for text that
    cannot subsequently be saved. The picker also caps its input, which is what
    makes this 422 unreachable in practice rather than merely survivable.
    """
    return role_categories.match_free_text(q)
