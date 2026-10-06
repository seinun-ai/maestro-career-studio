import re

import pytest

from tests.browser.conftest import FIXTURES

EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.[\w.]+)")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
PROFILE_URL = re.compile(r"linkedin\.com/in/", re.I)

# RFC 2606 reserves these for documentation; `logo@2x.png` is an asset name.
SAFE_EMAIL_DOMAIN = re.compile(r"^(?:.+\.)?example\.(?:com|org|net)$|^\d+x\.", re.I)


def personal_data(text: str) -> list[str]:
    """What kinds of personal data `text` appears to carry."""
    found = []
    if any(not SAFE_EMAIL_DOMAIN.search(m.group(1).rstrip(".")) for m in EMAIL.finditer(text)):
        found.append("email")
    if any(sum(c.isdigit() for c in m.group()) >= 10 for m in PHONE.finditer(text)):
        found.append("phone-like digits")
    if PROFILE_URL.search(text):
        found.append("profile url")
    return found


@pytest.mark.parametrize("text, kinds", [
    ("write to sam.rivera@mailhost.io", ["email"]),
    ("call (512) 555-0142", ["phone-like digits"]),
    ("call +1 512 555 0142", ["phone-like digits"]),
    ("see linkedin.com/in/someone", ["profile url"]),
    ("started 2024-01-15", []),
    ("write to name@example.com", []),
    ("<img src='logo@2x.png'>", []),
])
def test_the_guard_catches_personal_data_and_nothing_else(text, kinds):
    assert personal_data(text) == kinds


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.html")), ids=lambda p: p.name)
def test_no_fixture_carries_personal_data(path):
    assert personal_data(path.read_text(encoding="utf-8")) == [], path.name
