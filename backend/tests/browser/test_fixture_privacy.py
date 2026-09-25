import re

import pytest

from tests.browser.conftest import FIXTURES

PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "email"),
    (re.compile(r"\+?\d[\d\s().-]{8,}\d"), "phone-like digits"),
    (re.compile(r"linkedin\.com/in/", re.I), "profile url"),
]


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.html")), ids=lambda p: p.name)
def test_no_fixture_carries_personal_data(path):
    text = path.read_text()
    for pattern, what in PII:
        assert not pattern.search(text), f"{path.name}: {what}"
