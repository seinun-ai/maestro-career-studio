"""`base_resume_path` keeps every base resume file inside the base-resumes folder."""

import os

import pytest

from app.config import settings
from app.services.base_resume_data import base_resume_path


def test_a_slug_names_a_file_in_the_folder():
    path = base_resume_path("ml-engineer-us")
    assert os.path.dirname(str(path)) == os.path.normpath(str(settings.base_resumes_dir))
    assert path.name == "ml-engineer-us.json"


@pytest.mark.parametrize("slug", ["../escape", "a/../../b", "nested/name", "/etc/passwd", "../.."])
def test_a_slug_that_leaves_the_folder_is_refused(slug):
    with pytest.raises(ValueError):
        base_resume_path(slug)
