"""The country list and its one normalizer (`services/countries`)."""

import pytest
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


@pytest.mark.parametrize("text, code", [
    ("usa", "US"), ("U.S.", "US"), ("u.s.a.", "US"), ("US of A", "US"), ("America", "US"),
    ("United States of America", "US"),
    ("Great Britain", "GB"), ("Britain", "GB"), ("England", "GB"), ("Scotland", "GB"),
    ("Wales", "GB"),
    ("Turkey", "TR"), ("Turkiye", "TR"), ("Türkiye", "TR"),
    ("Czech Republic", "CZ"), ("The Netherlands", "NL"), ("Holland", "NL"), ("UAE", "AE"),
    ("Korea", "KR"), ("Republic of Korea", "KR"),
    ("Ivory Coast", "CI"), ("Cote d'Ivoire", "CI"), ("Côte d\u2019Ivoire", "CI"),
    ("Russia", "RU"), ("Vietnam", "VN"), ("Viet Nam", "VN"),
])
def test_normalize_common_english_variants(text, code):
    assert countries.normalize(text) == code


def test_variants_stay_out_of_the_list_and_never_collide():
    for variant in ("USA", "UK", "Holland", "Ivory Coast", "UAE", "u.s."):
        assert not countries.is_valid(variant)
        assert variant not in countries.labels().values()
    # An alias must not shadow a different code's own name.
    for alias, code in countries._ALIASES.items():
        assert countries._names().get(alias, code) == code, alias
    assert "North Korea" in countries.labels().values()
    assert countries.normalize("North Korea") == "KP"


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
    names = [countries._fold(n) for n in countries.labels().values()]
    assert len(names) == len(set(names))


def test_get_countries_route():
    body = TestClient(app).get("/api/countries").json()
    assert {"code": "GB", "name": "United Kingdom"} in body
    assert [c["code"] for c in body] == list(countries.labels())
