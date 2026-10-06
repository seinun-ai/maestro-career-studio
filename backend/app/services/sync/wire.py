"""Small pieces the sync's two ends share: how a row or a job id looks on the wire, and the fixed
sentences that name a disk problem. Nothing here touches a database or a file."""

import uuid

from app.models.sync import SyncRequest

DISK = "Maestro couldn't save the files it received."
CANT_READ = "Maestro couldn't read the files it needed to send."
MAX_REASON = 500


def uuid_of(raw: object) -> uuid.UUID | None:
    """The UUID a wire value names, or None when it names none."""
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def bundle_job_id(bundle: object) -> uuid.UUID | None:
    """The job a bundle is about, or None for a bundle with no readable ``job_id``."""
    try:
        return uuid.UUID(bundle["job_id"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def shown(row: SyncRequest) -> dict:
    """A request as it travels: ids as hex, the payload as stored."""
    return {"id": row.id.hex, "kind": row.kind, "job_id": row.job_id.hex if row.job_id else None,
            "payload": row.payload_json, "created_at": row.created_at.isoformat()}
