"""Links, emails and phone numbers in a draft or a note: which ones are the owner's, and which only look like
one (dates, versions, counts, ISBNs). One table, used by the draft check (qa) and the reasoning step's note."""

import pytest

from app.services import autofill_reason, contact_scan, qa

OWNER = [s.lower() for s in ["Ada Lovelace", "ada@example.test", "5550100199", "https://github.com/ada",
                             "linkedin.com/in/ada", "Springfield"]]

KEEP = [
    "I used Python 3.12.1 daily.", "At Acme (2019-2023) I built X.", "At Acme 2019-2023 (4 years) I built X.",
    "From 2019 - 2023 I led it.", "From 2019–2023 I led it.", "Salary 120,000-140,000.", "Range 120000-140000.",
    "Req REQ371910.", "Req 3719101 posted.", "Started 2023-01-15 at Acme.", "Started 15.01.2023.",
    "Processed 10 000 000 records.", "Scaled to 1,000,000 users.", "Grew ARR from 1200000 to 3400000.",
    "Call +1 555-010-0199.", "Call (555) 010-0199.", "Call 555.010.0199.", "Call 5550100199.",
    "See github.com/ada/forecast.", "See https://github.com/ada/forecast.", "See https://www.linkedin.com/in/ada/.",
    "Mail ada@example.test.", "Versions 1.2.3.4567 shipped.", "Releases 2021 2022 2023.", "ISBN 978-3-16-148410-0.",
    "Patent US 10,123,456.", "Patent US10123456.", "Q3 2023 18 releases.", "Mon–Fri 9-5 2019 2020",
    "Read report.pdf and data.csv.", "Wrote main.py and app.ts, see README.md.", "Used Next.js, Vue.js, D3.js.",
    "Stack: Node.js/Express and Vue.js/React.", "IP 192.168.100.200", "Phone ext 555-0199", "Mail ADA@EXAMPLE.TEST",
    "I built it in Node.js and ASP.NET.", "Used B.Tech methods.", "Rated 4.5 by 1.2 million users.",
]
DROP = [
    "See acme.in/jobs.", "See jobs.acme.us/x.", "See acme.jobs.", "See acme.careers/apply", "See evil.link/x",
    "See acme.site/x", "See acme.ru/x", "See acme.co.uk/x", "See acme.me.uk/x", "See acme.fr/x", "See acme.eu",
    "See acme.com.au/x", "See acme.nl/x", "See bit.ly/abc", "See t.co/abc", "See acme.ly/x", "Visit ACME.COM/apply",
    "See acme.zzz/x", "Call 5558675309.", "Call 15558675309 now.", "Call 555-867-5309.",
    "Email a@example.test.", "See github.com/someone-else.", "See globex.test/jobs.", "See https://github.com/adam/x.",
    "Mail recruiter@globex.test now.", "See www.globex.test today.", "Visit careers.globex.test.",
    "Call 555-010-0123 to hear more.", "Call +44 20 7946 0958 today.", "Call (415) 555-0132.",
    "Reach me at 212 555 0143.",
]


@pytest.mark.parametrize("text", KEEP)
def test_what_is_the_owners_or_only_looks_like_a_contact_is_kept(text):
    assert not contact_scan.foreign(text, OWNER), text


@pytest.mark.parametrize("text", DROP)
def test_a_link_email_or_phone_that_is_not_the_owners_is_dropped(text):
    assert contact_scan.foreign(text, OWNER), text


def test_an_email_must_match_exactly_not_as_a_piece_of_the_owners():
    assert contact_scan.foreign("Mail a@example.test", OWNER)
    assert not contact_scan.foreign("Mail ADA@example.test", OWNER)


def test_a_host_on_the_resume_passes_only_as_the_whole_host():
    assert contact_scan.foreign("I worked at king.com.", OWNER, known="analyst at booking.com")
    assert not contact_scan.foreign("I worked at Booking.com.", OWNER, known="analyst at www.booking.com. then")


def test_a_host_on_the_resume_is_not_foreign():
    assert contact_scan.foreign("I worked at Booking.com.", OWNER)
    assert not contact_scan.foreign("I worked at Booking.com.", OWNER, known="experience: booking.com, analyst")
    # ...but only a bare host: a path on it is still a link nobody gave.
    assert contact_scan.foreign("See booking.com/careers.", OWNER, known="booking.com")


def test_the_note_and_the_draft_check_read_contacts_the_same_way():
    assert autofill_reason.contacts is contact_scan.contacts
    assert qa._foreign_contact is contact_scan.foreign


def test_contacts_lists_what_a_note_must_lose():
    text = "Call 555-010-0123 or mail hr@globex.test, see https://globex.test/x and globex.test/apply from 2019-2023."
    assert contact_scan.contacts(text) == ["555-010-0123", "hr@globex.test", "https://globex.test/x",
                                           "globex.test/apply"]
