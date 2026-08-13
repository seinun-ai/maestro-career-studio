from app.schemas.resume import EducationEntry, ExperienceEntry, ResumeData


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


def test_experience_without_start_date_validates():
    """An undated role is a legal representation, not a parse failure: the
    resume genuinely states no date and nothing may invent one."""
    entry = ExperienceEntry.model_validate({"company": "C", "role": "R"})
    assert entry.start_date is None


def test_education_without_degree_validates():
    """Non-degree study (coursework, bootcamps, exchange terms) has no degree
    title to state."""
    entry = EducationEntry.model_validate({"institution": "I"})
    assert entry.degree is None


def test_undated_entries_survive_a_full_resume_round_trip():
    resume = ResumeData.model_validate(
        {
            "contact": {"name": "Riley", "email": "riley.quill@example.com"},
            "experience": [{"company": "C", "role": "R", "bullets": []}],
            "education": [{"institution": "I"}],
        }
    )
    dumped = resume.model_dump(mode="json")
    assert dumped["experience"][0]["start_date"] is None
    assert dumped["education"][0]["degree"] is None
