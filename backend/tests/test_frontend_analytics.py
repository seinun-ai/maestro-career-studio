"""CI pin for frontend/lib/analytics-series.ts. Node tests are not in CI."""

from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def test_analytics_series_caps_roles_and_charts_do_not_cycle_colours():
    series = _read("lib/analytics-series.ts")
    assert "export const MAX_ROLE_SERIES = 4" in series
    assert "export function splitTopRoles" in series
    ats = _read("components/charts/ats-over-time-chart.tsx")
    mix = _read("components/charts/role-mix-chart.tsx")
    assert "splitTopRoles" in ats and "splitTopRoles" in mix
    assert "% COLORS.length" not in ats
    assert "% COLORS.length" not in mix
    assert "More roles" in mix
    assert 'from "@/lib/format"' not in mix
    assert not (_FRONTEND / "lib/format.ts").exists()
