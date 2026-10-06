"""The country list and its one normalizer (`services/countries`)."""

from fastapi.testclient import TestClient

from app.main import app
from app.services import countries


def test_normalize_codes_aliases_and_names():
    assert countries.normalize("us") == "US"
    assert countries.normalize(" GB ") == "GB"
    assert countries.normalize("UK") == "GB"
    assert countries.normalize("United States") == "US"
    assert countries.normalize("india") == "IN"
    for junk in (None, "", "Remote", "XX", "Narnia"):
        assert countries.normalize(junk) is None


def test_list_is_iso_shaped():
    codes = list(countries.labels())
    assert len(codes) == len(set(codes)) >= 240
    assert all(len(c) == 2 and c.isupper() for c in codes)
    assert countries.name_for("IN") == "India"


def test_is_valid_and_name_for():
    assert countries.is_valid("KR")
    assert not countries.is_valid("UK")  # alias for input only, never a stored code
    assert not countries.is_valid("kr")
    assert countries.name_for("KR") == "South Korea"


def test_names_are_unambiguous():
    # Two codes sharing a casefolded name would make normalize() order-dependent.
    names = [n.casefold() for n in countries.labels().values()]
    assert len(names) == len(set(names))


def test_get_countries_route():
    body = TestClient(app).get("/api/countries").json()
    assert {"code": "GB", "name": "United Kingdom"} in body
    assert [c["code"] for c in body] == list(countries.labels())
