from scripts.backfill_work_auth import compute_updates


def test_compute_updates_flips_unstated_via_backstop():
    auth, disq = compute_updates(
        work_authorization="unstated",
        opt_accepted="unstated",
        raw_text="We do not offer sponsorship.",
    )
    assert auth == "no_sponsorship"
    assert disq is True


def test_compute_updates_leaves_clear_row_alone():
    auth, disq = compute_updates(
        work_authorization="sponsorship_available",
        opt_accepted="yes",
        raw_text="Sponsorship available.",
    )
    assert auth == "sponsorship_available"
    assert disq is False


def test_compute_updates_disqualifies_on_opt_no_even_when_auth_unstated():
    auth, disq = compute_updates(
        work_authorization="unstated",
        opt_accepted="no",
        raw_text="Some unrelated text.",
    )
    assert auth == "unstated"
    assert disq is True
