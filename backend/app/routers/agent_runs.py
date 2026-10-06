"""The run log over HTTP (`services/agent_runs.py`). Written by MCP `record_run`; read by the
Agent inbox's Recent runs panel and the Automations page's Last ran line. No edit, no delete."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.agent_runs import AgentRunCreate, AgentRunList, AgentRunRead, LatestAgentRuns
from app.services import agent_runs
from app.write_origin import WriteOrigin, get_write_origin

router = APIRouter(prefix="/api/agent-runs", tags=["agent-runs"])


@router.post("", response_model=AgentRunRead, status_code=201)
def post_agent_run(
    payload: AgentRunCreate,
    db: Annotated[Session, Depends(get_db)],
    write_origin: Annotated[WriteOrigin, Depends(get_write_origin)],
):
    agent = write_origin.detail if write_origin.origin == "mcp" else None
    return agent_runs.read_one(db, agent_runs.record(db, payload, agent))


@router.get("/latest", response_model=LatestAgentRuns)
def get_latest_runs(db: Annotated[Session, Depends(get_db)]):
    return {"items": agent_runs.latest(db), "refused_requests": agent_runs.refused_requests(db)}


@router.get("", response_model=AgentRunList)
def list_agent_runs(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
):
    return {"items": agent_runs.recent(db, limit)}
