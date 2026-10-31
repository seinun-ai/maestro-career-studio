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
    # The input-only variants `normalize` reads as this code, folded ("GB": "uk", "great britain", ...),
    # so a picker turns a typed "UK" into GB as a save would; empty for most.
    aliases: list[str] = []


@router.get("", response_model=list[Country])
def list_countries():
    """Every ISO 3166-1 alpha-2 country, in file (alphabetical by code) order, with its aliases."""
    return [
        Country(code=code, name=name, aliases=countries.aliases_for(code))
        for code, name in countries.labels().items()
    ]
