"""The shared list of known ATS hosts (`extension/shared/ats-hosts.js`).

One list serves detect.js (which vendor is this page) and the queued run's driver (the saved
job-site password is typed only on a host listed here). What matters: a host counts only when the
pattern is anchored at a dot or the start, so a lookalike never earns the password.
"""

import pytest

from tests.extension_harness import ROOT, run_node

ATS_HOSTS_JS = (ROOT / "extension" / "shared" / "ats-hosts.js").read_text(encoding="utf-8")

_DRIVER = "const ns = loadModules(); emit(spec.hosts.map((h) => [ns.atsHosts.vendorOf(h), ns.atsHosts.isKnown(h)]));"


def _vendors(tmp_path, *hosts):
    return run_node(_DRIVER, {"hosts": list(hosts)}, tmp_path, source=ATS_HOSTS_JS)


@pytest.mark.parametrize("host, vendor", [
    ("acme.wd5.myworkdayjobs.com", "workday"), ("boards.greenhouse.io", "greenhouse"),
    ("job-boards.greenhouse.io", "greenhouse"), ("jobs.lever.co", "lever"),
    ("jobs.ashbyhq.com", "ashby"), ("acme.icims.com", "icims"), ("ACME.Taleo.NET", "taleo"),
    ("ats.rippling.com", "rippling"), ("acme.rippling-ats.com", "rippling"),
])
def test_a_known_ats_host_names_its_vendor(tmp_path, host, vendor):
    assert _vendors(tmp_path, host) == [[vendor, True]]


@pytest.mark.parametrize("host", [
    "greenhouse.io.attacker.test", "myworkdayjobs.com.evil.test", "evilmyworkdayjobs.com",
    "notgreenhouse.io", "lever.co", "jobs.lever.co.attacker.test", "careers.acme.test", "", None,
    "login.evil.test/boards.greenhouse.io",
])
def test_a_lookalike_or_unknown_host_is_not_known(tmp_path, host):
    assert _vendors(tmp_path, host) == [[None, False]]
