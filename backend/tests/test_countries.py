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


def test_names_are_unambiguous():
    # Two codes sharing a casefolded name would make normalize() order-dependent.
    names = [countries._fold(n) for n in countries.labels().values()]
    assert len(names) == len(set(names))


def test_get_countries_route():
    body = TestClient(app).get("/api/countries").json()
    assert {"code": "GB", "name": "United Kingdom"} in body
    assert [c["code"] for c in body] == list(countries.labels())


def test_country_spellings_collapse_to_one_code():
    for text in ["United States", "USA", "U.S.", "united states ", "United States of America"]:
        assert countries.normalize(text) == "US"
    assert countries.normalize("Canada / United States") is None  # more than one: no guess
    assert countries.normalize("unknown") is None
    assert countries.label("GB") == "United Kingdom"
    assert countries.label(" gb ") == "United Kingdom"
    # "UK" is input the normalizer accepts, never a stored code, so it has no label.
    assert countries.label("UK") is None
    assert countries.label(None) is None


def test_market_keys_name_their_country():
    """markets.yaml says "UK" where ISO says GB; the normalizer joins the two."""
    from app.services import markets

    assert countries.normalize("UK") == "GB"
    for key in markets.keys():
        assert countries.normalize(key) is not None, key


def test_currency_is_data_and_never_a_guess():
    assert countries.currency("CA") == "CAD"
    assert countries.currency("ca") == "CAD"
    assert countries.currency("US") == "USD"
    assert countries.currency("GB") == "GBP"
    assert countries.currency("DE") == "EUR"
    assert countries.currency("IN") == "INR"
    assert countries.currency("AQ") is None  # Antarctica pays in nothing: no entry, no guess
    assert countries.currency("UK") is None  # not a code
    assert countries.currency(None) is None


def test_currency_entries_are_listed_countries_with_iso_codes():
    table = countries._currencies()
    assert len(table) >= 240
    for code, currency in table.items():
        assert code in countries.labels(), code
        assert len(currency) == 3 and currency.isalpha() and currency.isupper(), (code, currency)


def test_each_market_currency_is_its_country_currency():
    from app.services import markets

    for key in markets.keys():
        assert countries.currency(countries.normalize(key)) == markets.currency_for(key), key


@pytest.mark.parametrize("place, code", [
    ("Toronto, ON, Canada", "CA"),
    ("London, UK", "GB"),
    ("Berlin (Germany)", "DE"),
    ("New York, NY, United States", "US"),
    ("Remote - United States", "US"),
    ("Sarajevo, Bosnia and Herzegovina", "BA"),
    ("Canada", "CA"),
    ("DE", "DE"),
    # A two-letter part is a state as often as a country: California, not Canada.
    ("San Francisco, CA", None),
    ("Austin, TX (Hybrid)", None),
    # Two countries named, or none: no guess.
    ("Toronto, Canada / Seattle, United States", None),
    ("Remote", None),
    # A US state with a country's name names neither.
    ("Atlanta, Georgia", None),
    ("Georgia", None),
    ("", None),
    (None, None),
])
def test_a_place_names_at_most_one_country(place, code):
    assert countries.named_in(place) == code


def test_a_job_country_comes_from_its_country_then_its_location():
    assert countries.for_job("United States", "Toronto, Canada") == "US"
    assert countries.for_job(None, "Toronto, Canada") == "CA"
    assert countries.for_job("Remote", "London, UK") == "GB"
    assert countries.for_job("Canada / United States", None) is None
    assert countries.for_job("Georgia", None) == "GE"  # a country field names a country
    assert countries.for_job(None, None) is None
