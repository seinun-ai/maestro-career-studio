from typing import Any


def project_enabled(entry: dict[str, Any] | Any) -> bool:
    if isinstance(entry, dict):
        return entry.get("enabled", True) is not False
    return getattr(entry, "enabled", True) is not False


def active_projects(projects: list[Any] | None) -> list[Any]:
    if not projects:
        return []
    return [p for p in projects if project_enabled(p)]


def active_experience(experience: list[Any] | None) -> list[Any]:
    if not experience:
        return []
    return [e for e in experience if project_enabled(e)]


def _section_get(section: Any, field: str, default: Any = None) -> Any:
    if isinstance(section, dict):
        return section.get(field, default)
    return getattr(section, field, default)


def extra_section_live(section: Any) -> bool:
    """True when a custom (extra) section is a live mapping: a dict that is not
    explicitly disabled.

    Shared by the ATS evidence indexer (``ats.resume_indexer.index_resume``) and
    the gap placement-target builder (``placement_targets.build_targets``) so
    both agree on which custom content is live. An omitted or ``None`` ``enabled``
    reads as live — matching ``project_enabled`` and the render view
    (``active_extra_sections``) — and non-dict junk is never live. Before this was
    shared the two views diverged: the indexer used a strict ``enabled is False``
    check (``None`` -> live, no dict guard) while the target builder used a truthy
    ``enabled`` check (``None`` -> disabled)."""
    return isinstance(section, dict) and project_enabled(section)


def extra_entry_live(entry: Any) -> bool:
    """True when an ``entries``-type custom section's entry is a live mapping.
    Same ``None`` -> live semantics as :func:`extra_section_live`."""
    return isinstance(entry, dict) and project_enabled(entry)


def active_extra_sections(sections: list[Any] | None) -> list[Any]:
    """Drop disabled extra sections and, within ``entries`` sections, disabled
    entries. Enabled ``entries`` sections are shallow-copied so the caller's
    data is not mutated; ``bullets`` sections pass through unchanged."""
    if not sections:
        return []
    out: list[Any] = []
    for section in sections:
        if not project_enabled(section):
            continue
        if _section_get(section, "type") == "entries" and isinstance(section, dict):
            entries = _section_get(section, "entries") or []
            copy = dict(section)
            copy["entries"] = [e for e in entries if project_enabled(e)]
            out.append(copy)
        else:
            out.append(section)
    return out


def resume_for_render(resume_data: dict[str, Any]) -> dict[str, Any]:
    """Shallow copy with only enabled projects, experience, and custom sections
    (and enabled entries within them) for PDF/LaTeX output."""
    out = dict(resume_data)
    out["projects"] = active_projects(resume_data.get("projects"))
    out["experience"] = active_experience(resume_data.get("experience"))
    out["extra_sections"] = active_extra_sections(resume_data.get("extra_sections"))
    return out
