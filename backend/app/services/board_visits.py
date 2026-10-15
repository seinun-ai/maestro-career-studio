"""The job board page the user opened last, so a job saved on the employer's own page can say where it was found.

The extension (the Companion's origin only; an agent's find_job_by_url is not the user's browsing) asks
`GET /api/jobs/match?url=` for each page it opens. When that page is a known job board's (Built In,
LinkedIn, ...), the board's name is kept here for TTL_S seconds; `POST /api/jobs` stamps it on the job it saves from
a page that is not a board's (`Job.referrer_board`), and "How did you hear about us?" reads it as the board
(`routers/autofill._job_hint`). One slot, in memory: the app has one user, and a stale or wrong board is only an
assumed answer the user is told to check. Nothing but the board's NAME is kept, never the address."""

import time

from app.services import autofill_job

TTL_S = 20 * 60
_last: tuple[str, float] | None = None


def seen(url: str | None) -> None:
    """Note `url` if it is a known job board's page."""
    global _last
    if board := autofill_job.board_of_url(url):
        _last = (board, time.monotonic())


def recent() -> str | None:
    """The board seen within TTL_S seconds, else None."""
    last = _last   # one read: seen() may replace the slot meanwhile
    if last is None or time.monotonic() - last[1] > TTL_S:
        return None
    return last[0]


def forget() -> None:
    global _last
    _last = None
