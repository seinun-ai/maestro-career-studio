from app.schemas.resume import ResumeData


def test_minimal_resume_round_trips():
    data = {
        "contact": {
            "name": "Riley Quill",
            "email": "riley.quill@example.com",
        },
        "skills": [{"category": "Languages", "items": ["Python", "SQL"]}],
        "experience": [
            {
                "company": "Fictional Employer 2",
                "role": "Data Analyst",
                "start_date": "Jul 2022",
                "end_date": "Jun 2024",
                "bullets": ["Built data pipelines."],
            }
        ],
    }

    resume = ResumeData.model_validate(data)

    assert resume.contact.name == "Riley Quill"
    assert resume.skills[0].items == ["Python", "SQL"]
    assert resume.model_dump()["experience"][0]["company"] == "Fictional Employer 2"


def test_project_enabled_defaults_true():
    resume = ResumeData.model_validate(
        {
            "contact": {"name": "Riley", "email": "riley.quill@example.com"},
            "projects": [{"name": "Alpha", "bullets": []}],
        }
    )
    assert resume.projects[0].enabled is True


def test_project_enabled_false():
    resume = ResumeData.model_validate(
        {
            "contact": {"name": "Riley", "email": "riley.quill@example.com"},
            "projects": [{"name": "Archived", "enabled": False, "bullets": []}],
        }
    )
    assert resume.projects[0].enabled is False
