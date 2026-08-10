"""X-Maestro-CS-Origin headers -> a WriteOrigin the KB routers can persist."""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.write_origin import WriteOrigin, get_write_origin

app = FastAPI()


@app.get("/probe")
def probe(origin: WriteOrigin = Depends(get_write_origin)):
    return {"origin": origin.origin, "detail": origin.detail}


client = TestClient(app)


def test_absent_headers_mean_no_override():
    assert client.get("/probe").json() == {"origin": None, "detail": None}


def test_headers_are_read():
    resp = client.get(
        "/probe",
        headers={
            "X-Maestro-CS-Origin": "mcp",
            "X-Maestro-CS-Origin-Detail": "Claude Desktop",
        },
    )
    assert resp.json() == {"origin": "mcp", "detail": "Claude Desktop"}


def test_legacy_career_studio_headers_are_accepted():
    resp = client.get(
        "/probe",
        headers={
            "X-Career-Studio-Origin": "mcp",
            "X-Career-Studio-Origin-Detail": "Claude Desktop",
        },
    )
    assert resp.json() == {"origin": "mcp", "detail": "Claude Desktop"}


def test_unknown_origin_is_rejected_not_persisted():
    resp = client.get("/probe", headers={"X-Maestro-CS-Origin": "nonsense"})
    assert resp.json() == {"origin": None, "detail": None}


def test_detail_is_truncated_and_stripped():
    resp = client.get(
        "/probe",
        headers={
            "X-Maestro-CS-Origin": "mcp",
            "X-Maestro-CS-Origin-Detail": "  " + "x" * 300,
        },
    )
    assert len(resp.json()["detail"]) == 120
