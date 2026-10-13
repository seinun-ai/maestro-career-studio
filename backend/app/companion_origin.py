"""Is this request from the configured Companion? An exact chrome-extension:// origin, never a
pattern (SYSTEM.md inv-browser-boundary item 3)."""
from fastapi import Request

from app.config import settings


def is_companion(request: Request) -> bool:
    origin = request.headers.get("origin", "")
    return origin in {f"chrome-extension://{ext_id}" for ext_id in settings.maestro_cs_extension_ids}
