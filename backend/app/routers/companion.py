"""Routes only the Companion extension may call."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.companion_origin import is_companion
from app.db import get_db
from app.models.application_proposal import ApplicationProposal
from app.services import proposals


class _LoginRoute(APIRoute):
    """Keep a rejected body out of the login route's validation response."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError:
                raise HTTPException(422, detail="The job-site login request is invalid.") from None

        return handler


router = APIRouter(prefix="/api/companion", tags=["companion"], route_class=_LoginRoute)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: UUID


@router.post("/job-site-login")
def companion_job_site_login(
    payload: LoginRequest, request: Request, db: Annotated[Session, Depends(get_db)],
):
    """The saved job-site login for a Queued job, for the Companion's sign-in step only.
    Never reaches a model: the Companion types it into the job's own sign-in page."""
    if not is_companion(request):
        raise HTTPException(403, detail="Only the Companion can ask for the job-site login here.")
    prop = db.get(ApplicationProposal, payload.proposal_id)
    if prop is None:
        raise HTTPException(404, detail="Proposal not found")
    try:
        return proposals.share_job_site_login(db, prop, "companion", channel="companion")
    except proposals.TransitionError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
