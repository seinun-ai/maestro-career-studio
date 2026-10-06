"""GET /api/countries — the country list, for pickers.

The vocabulary lives in services/data/countries.yaml and the web app fetches it
rather than copying it, the same reason as /api/role-categories.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import countries

router = APIRouter(prefix="/api/countries", tags=["countries"])


class Country(BaseModel):
    code: str
    name: str


@router.get("", response_model=list[Country])
def list_countries():
    """Every ISO 3166-1 alpha-2 country, in file (alphabetical by code) order."""
    return [Country(code=code, name=name) for code, name in countries.labels().items()]
