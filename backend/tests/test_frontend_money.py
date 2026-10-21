"""One formatter for pay (`frontend/lib/money.ts`), with "≈" for converted figures (D8).

The node suite pins the rules; the source pins keep every pay display on it, with no USD default.
"""

import re
from pathlib import Path

from tests.node_ts import run_node_test

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(rel: str) -> str:
    return (_FRONTEND / rel).read_text(encoding="utf-8")


def test_money_node_suite():
    result = run_node_test("lib/money.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_formatter_mirrors_the_backend_rules():
    src = _read("lib/money.ts")
    assert "HOURS_PER_YEAR = 2080" in src
    assert "day: 260, week: 52, month: 12, year: 1" in src
    assert 'currencyDisplay: code === home ? "narrowSymbol" : "symbol"' in src
    assert 'APPROX = "≈ "' in src
    assert "USD" not in src  # no currency is ever assumed


def test_pay_displays_use_the_one_formatter_with_no_usd_default():
    fields = _read("components/job-extracted-fields.tsx")
    assert "function formatMoney" not in fields and "function formatSalary" not in fields
    assert '"USD"' not in fields
    for rel in ("components/job-extracted-fields.tsx", "app/jobs/[id]/page.tsx",
                "components/explore/explore-overview.tsx"):
        src = _read(rel)
        assert "formatSalary" not in src, rel
        assert re.search(r"\bformatPay\(", src), rel


def test_money_options_come_from_the_settings_and_the_rates():
    hook = _read("hooks/use-money.ts")
    assert '"/api/settings/money"' in hook and '"/api/fx/rates"' in hook
    assert "useQuery" in hook
