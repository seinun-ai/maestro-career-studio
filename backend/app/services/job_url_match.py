"""Deciding whether the page the user is on IS a job already in the library.

This lived in the browser extension's side panel (`urlMatchScore`, deleted with
that panel) as a comment that never executed: the field it compared,
JobSummary.source_url, was dropped
by the response schema, so it scored 0 for every job. Moving it next to the
data made it testable, and the table in tests/test_job_url_match.py is the
specification.

The first server-side version kept the browser's scoring shape — a HOST_ONLY
floor of 10 plus one point per shared leading path segment — and that shape was
wrong. It conflated a confidence tier with an unnormalized similarity count, so
the same integer meant opposite things depending on how deep a host's paths
run:

    12  jobs.lever.co/acme/abc          -> .../abc/apply       SAME posting
    12  boards.greenhouse.io/a/jobs/123 -> .../jobs/456        DIFFERENT posting

No threshold separates those, because the count was never normalized by path
depth. Both landed on "likely", which is precisely how a wrong job gets
offered to the user.

**Containment is directional** — the same principle the ATS matcher already
applies to token containment (SYSTEM.md §4). The current page is the saved
posting if and only if the saved path is a PREFIX of the current path:

  - current-more-specific is the SAME posting. Applying navigates DOWN from a
    posting (/acme/abc -> /acme/abc/apply, /acme/jobs/123 ->
    /acme/jobs/123/application), which is the whole point of the feature: the
    user is on the apply form of the job they saved.
  - saved-more-specific is NOT the same posting, so the reverse direction
    deliberately does not match. Capture happens on the job page, so
    saved-shorter-or-equal is the normal case; a shorter CURRENT path means
    the user navigated up to an employer index or search listing, and a
    listing is an ancestor of the posting rather than the posting.
  - siblings fall out by construction: /acme/jobs/456 is not below
    /acme/jobs/123 however many segments they share.

A saved link with no path segments at all matches nothing. Pure prefix logic
would otherwise make a bare host a prefix of every page on that host, which is
the exact false positive the old HOST_ONLY floor existed to prevent — the
multi-tenant ATS problem (boards.greenhouse.io, *.myworkdayjobs.com,
jobs.lever.co each front thousands of unrelated employers) reappearing as a
full match rather than as a weak one.

There is no score and no threshold any more, so the function returns a bool.
An integer magnitude that nothing branches on is a number a client can invent
meaning for, and the old constants were guessed rather than measured — the
heuristic had never once run. A decision the caller must not reinterpret is
better typed as a decision.

Query strings and fragments are ignored, as before: a `?gh_src=` or
`?utm_source=` referral link and a `#apply` anchor name a posting that is
already saved, and treating them as new is how a library fills with
duplicates.
"""

from urllib.parse import urlsplit


def _host_and_segments(url: str | None) -> tuple[str, list[str]] | None:
    """(hostname, non-empty path segments), or None if `url` is unusable.

    The falsy guard is explicit and comes FIRST rather than falling out of the
    hostname check below. urlsplit(None) does not raise — it returns a *bytes*
    result — so b"".split("/") would raise TypeError, which the ValueError
    handler here would not catch, the moment segment computation moved above
    the hostname check. Jobs legitimately have no source_url, so "a missing
    link matches nothing" is a real contract and is enforced rather than
    implied.

    Dropping empty segments is what makes a trailing slash irrelevant;
    urlsplit already separates query and fragment out of the path, and already
    lowercases the hostname.
    """
    if not url:
        return None
    try:
        split = urlsplit(url)
        host = split.hostname
        path = split.path
    except ValueError:
        # e.g. "http://[" — an unterminated IPv6 literal.
        return None
    if not host:
        return None
    return host, [segment for segment in path.split("/") if segment]


def is_same_posting(saved: str | None, current: str | None) -> bool:
    """Is the page at `current` the same job posting as the saved link `saved`?

    True when the hosts agree and the saved path is a prefix of the current
    path (an equal path counts as a prefix). Never raises: source_url is
    user-supplied and the caller is a request path with nowhere to report a
    parse failure, so an unusable URL simply does not match.
    """
    saved_parts = _host_and_segments(saved)
    current_parts = _host_and_segments(current)
    if saved_parts is None or current_parts is None:
        return False

    saved_host, saved_segments = saved_parts
    current_host, current_segments = current_parts
    if saved_host != current_host:
        return False
    # A pathless saved link would otherwise prefix every page on the host.
    if not saved_segments:
        return False
    return current_segments[: len(saved_segments)] == saved_segments
