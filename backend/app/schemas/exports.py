from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CareerExportMetadata(BaseModel):
    name: Literal["career"] = "career"
    filename: Literal["career.md"] = "career.md"
    generated_at: datetime
    content_hash: str
    download_url: Literal["/api/exports/career"] = "/api/exports/career"
