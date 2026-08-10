from app.services.pdf_render import render_document
from app.services.resume_projects import (
    active_experience,
    active_projects,
    project_enabled,
    resume_for_render,
)


def render_tex(*args, **kwargs) -> str:
    """Latex source text via render_document (render_tex itself was removed)."""
    return render_document(*args, **kwargs).source_text


def test_project_enabled_missing_is_true():
    assert project_enabled({"name": "A"}) is True


def test_project_enabled_false():
    assert project_enabled({"name": "A", "enabled": False}) is False


def test_active_projects_filters_disabled():
    projects = [
        {"name": "A", "enabled": True},
        {"name": "B", "enabled": False},
        {"name": "C"},
    ]
    assert [p["name"] for p in active_projects(projects)] == ["A", "C"]


def test_render_tex_omits_disabled_projects():
    tex = render_tex(
        {
            "contact": {"name": "Sample", "email": "a@b.com"},
            "projects": [
                {"name": "Visible", "bullets": ["Did work."]},
                {"name": "Hidden", "enabled": False, "bullets": ["Old work."]},
            ],
        }
    )
    assert "Visible" in tex
    assert "Hidden" not in tex
    assert "Old work." not in tex


def test_render_tex_hides_projects_section_when_all_disabled():
    tex = render_tex(
        {
            "contact": {"name": "Sample", "email": "a@b.com"},
            "projects": [{"name": "Archived", "enabled": False, "bullets": []}],
        }
    )
    assert "\\section{Projects}" not in tex


def test_resume_for_render_shallow_copy():
    data = {
        "contact": {"name": "Sample", "email": "a@b.com"},
        "projects": [{"name": "A"}, {"name": "B", "enabled": False}],
    }
    out = resume_for_render(data)
    assert len(out["projects"]) == 1
    assert len(data["projects"]) == 2


def test_active_experience_filters_disabled():
    experience = [
        {"company": "A", "enabled": True},
        {"company": "B", "enabled": False},
        {"company": "C"},
    ]
    assert [e["company"] for e in active_experience(experience)] == ["A", "C"]


def test_render_tex_omits_disabled_experience():
    tex = render_tex(
        {
            "contact": {"name": "Sample", "email": "a@b.com"},
            "experience": [
                {
                    "company": "VisibleCo",
                    "role": "Eng",
                    "start_date": "2020",
                    "bullets": ["Shipped it."],
                },
                {
                    "company": "HiddenCo",
                    "role": "Eng",
                    "enabled": False,
                    "start_date": "2018",
                    "bullets": ["Old role."],
                },
            ],
        }
    )
    assert "VisibleCo" in tex
    assert "HiddenCo" not in tex
    assert "Old role." not in tex


def test_render_tex_hides_experience_section_when_all_disabled():
    tex = render_tex(
        {
            "contact": {"name": "Sample", "email": "a@b.com"},
            "experience": [
                {
                    "company": "Archived",
                    "role": "Eng",
                    "enabled": False,
                    "start_date": "2018",
                    "bullets": [],
                }
            ],
        }
    )
    assert "\\section{Experience}" not in tex


def test_resume_for_render_filters_experience():
    data = {
        "contact": {"name": "Sample", "email": "a@b.com"},
        "experience": [{"company": "A"}, {"company": "B", "enabled": False}],
    }
    out = resume_for_render(data)
    assert len(out["experience"]) == 1
    assert len(data["experience"]) == 2
