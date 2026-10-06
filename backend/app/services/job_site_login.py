"""The job-site login: one email and password used only for job-site accounts.

SYSTEM.md {#inv-job-site-password-local}: kept in settings/secrets/job-site-login.json (0600,
directory 0700), never in the database, exports, telemetry or logs. The web API
reports only whether a password is set; the agent gets it over MCP only while full automation is
on (routers/proposals.py job-site-login).
"""

import json
import os
import tempfile
from pathlib import Path

from app.config import settings

FILENAME = "job-site-login.json"


def path() -> Path:
    return Path(settings.settings_dir) / "secrets" / FILENAME


def read() -> tuple[str | None, str | None]:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None, None
    return data.get("email"), data.get("password")


def write(email: str | None, password: str | None) -> None:
    old_email, old_password = read()
    data = {"email": email if email is not None else old_email,
            "password": password if password is not None else old_password}
    target = path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    fd, name = tempfile.mkstemp(prefix=".job-site-login.", suffix=".tmp", dir=target.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def clear() -> None:
    path().unlink(missing_ok=True)


def status() -> dict:
    email, password = read()
    return {"email": email, "password_set": bool(password)}
