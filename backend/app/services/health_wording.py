"""The health check's word bank: clichés and filler words matched in CODE.

The model never decides what counts as a cliché: the same words always flag,
and the user owns the list (`GET/PUT /api/resume-lint/wording`, plus reset).
Storage is two `Setting` rows holding JSON:

- `health.word_bank` — `{"cliche": [...], "filler": [...]}`. ABSENT until the
  first edit, and absent means the built-in defaults (reset deletes it).
- `health.ignored_words` — the "Never flag" list, lower-cased. It silences a
  bank word AND a classifier slip whose span matches it.

Matching and the Remove / Apply text edits are pure; `resume_lint` turns them
into zero-score `language.*` notes and gates each edited text through
`health_guards` before offering it as a suggestion.
"""
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.setting import Setting

BANK_KEY = "health.word_bank"
IGNORED_KEY = "health.ignored_words"
MAX_ENTRIES = 200
MAX_CHARS = 40

# Sources (docs/health-check-rubric.md, "Word bank"): CareerBuilder/Harris 2014
# "worst resume terms" and the VMock filler list via Boston University.
DEFAULT_CLICHE = (
    "results-driven", "results-oriented", "team player", "go-getter",
    "think outside the box", "synergy", "best of breed", "go-to person",
    "thought leadership", "value add", "detail-oriented", "self-motivated",
    "hard worker", "strategic thinker", "dynamic", "proactive", "track record",
    "self-starter",
)
DEFAULT_FILLER = (
    "successfully", "effectively", "efficiently", "various", "several", "very",
    "really", "basically", "actually",
)


@dataclass(frozen=True)
class WordBank:
    cliche: tuple[str, ...]
    filler: tuple[str, ...]
    ignored: tuple[str, ...] = ()

    def payload(self) -> dict:
        """The `/wording` response shape."""
        return {
            "cliche": list(self.cliche), "filler": list(self.filler),
            "ignored": list(self.ignored),
            "defaults": {"cliche": list(DEFAULT_CLICHE), "filler": list(DEFAULT_FILLER)},
        }


DEFAULT_BANK = WordBank(cliche=DEFAULT_CLICHE, filler=DEFAULT_FILLER)


# --------------------------------------------------------------------------- #
# normalization + storage

def normalize(words: Iterable[str]) -> list[str]:
    """Trim, collapse inner whitespace, lower-case, dedupe (first wins).

    Raises ValueError for an entry outside 1–MAX_CHARS characters, or more
    than MAX_ENTRIES entries once deduped."""
    out: list[str] = []
    for word in words:
        norm = " ".join(str(word).split()).lower()
        if not 1 <= len(norm) <= MAX_CHARS:
            raise ValueError(f"Each word or phrase must be 1 to {MAX_CHARS} characters.")
        if norm not in out:
            out.append(norm)
    if len(out) > MAX_ENTRIES:
        raise ValueError(f"A list can hold at most {MAX_ENTRIES} words.")
    return out


def _read(db: Session, key: str):
    row = db.get(Setting, key)
    if row is None or not row.value:
        return None
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        return None


def _stored_list(value) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    try:
        return tuple(normalize(value))
    except ValueError:
        return None


def load(db: Session) -> WordBank:
    """The user's bank; any missing or unreadable part reads as its default."""
    bank = _read(db, BANK_KEY)
    cliche = filler = None
    if isinstance(bank, dict):
        cliche, filler = _stored_list(bank.get("cliche")), _stored_list(bank.get("filler"))
    if cliche is None or filler is None:
        cliche, filler = DEFAULT_CLICHE, DEFAULT_FILLER
    ignored = _stored_list(_read(db, IGNORED_KEY)) or ()
    return WordBank(cliche=cliche, filler=filler, ignored=ignored)


def _write(db: Session, key: str, value) -> None:
    payload = json.dumps(value)
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=payload))
    else:
        row.value = payload


def save(db: Session, *, cliche: Iterable[str], filler: Iterable[str],
         ignored: Iterable[str]) -> WordBank:
    bank = WordBank(cliche=tuple(normalize(cliche)), filler=tuple(normalize(filler)),
                    ignored=tuple(normalize(ignored)))
    _write(db, BANK_KEY, {"cliche": list(bank.cliche), "filler": list(bank.filler)})
    _write(db, IGNORED_KEY, list(bank.ignored))
    db.commit()
    return bank


def reset(db: Session) -> WordBank:
    """Back to the default clichés and filler; the Never flag list is kept."""
    row = db.get(Setting, BANK_KEY)
    if row is not None:
        db.delete(row)
        db.commit()
    return load(db)


# --------------------------------------------------------------------------- #
# matching + text edits (pure)

def _pattern(phrase: str) -> re.Pattern:
    body = r"\s+".join(re.escape(part) for part in phrase.split())
    return re.compile(rf"(?<![\w-]){body}(?![\w-])", re.IGNORECASE)


def is_ignored(word: str, bank: WordBank) -> bool:
    return word.strip().lower() in bank.ignored


def matches(text: str, bank: WordBank) -> list[tuple[str, str]]:
    """(kind, word) for each bank word in `text`, once each, in bank order;
    a word on the Never flag list is skipped."""
    hits: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kind, words in (("cliche", bank.cliche), ("filler", bank.filler)):
        for word in words:
            if word in seen or is_ignored(word, bank) or not _pattern(word).search(text):
                continue
            seen.add(word)
            hits.append((kind, word))
    return hits


_SENTENCE_END = ".!?"
_JOINING = ",;:"
# "A dynamic, detail-oriented engineer": the comma after a cut adjective
# belongs to it when a determiner precedes it.
_DETERMINERS = frozenset({"a", "an", "the", "my", "our", "their", "his", "her", "its"})


def _cut(text: str, start: int, end: int, capital: bool) -> str:
    """`text` without [start, end), with the seam cleaned up."""
    before, after = text[:start].rstrip(), text[end:].lstrip()
    if not before or before[-1] in _SENTENCE_END:
        # The cut word opened a sentence: no leading comma, keep its capital.
        after = after.lstrip(_JOINING + " ")
        if capital:
            after = after[:1].upper() + after[1:]
        return f"{before} {after}".strip() if before else after
    if not after:
        return before.rstrip(_JOINING)
    if after[0] == "," and before.split()[-1].lower() in _DETERMINERS:
        return f"{before} {after[1:].lstrip()}"
    if after[0] in _JOINING + _SENTENCE_END + ")":
        if before[-1] in _JOINING:
            if after[0] == "," and before[-1] == ",":
                # ", word," was parenthetical: drop both commas.
                return f"{before[:-1].rstrip()} {after[1:].lstrip()}".rstrip()
            before = before[:-1].rstrip()
        return before + after  # no space before punctuation
    return f"{before} {after}"


def remove(text: str, phrase: str) -> str:
    """`text` with every whole-word occurrence of `phrase` deleted."""
    pattern = _pattern(phrase)
    for _ in range(text.count(" ") + 2):  # each pass removes one; bounded
        m = pattern.search(text)
        if m is None:
            break
        text = _cut(text, m.start(), m.end(), m.group(0)[:1].isupper())
    return text


def apply_fix(text: str, span: str, fix: str) -> str:
    """`text` with the slip `span` (verbatim, case-sensitive) replaced by `fix`.
    A span that begins or ends with a word character must not be part of a
    longer word."""
    lead = r"(?<!\w)" if span[:1].isalnum() or span[:1] == "_" else ""
    tail = r"(?!\w)" if span[-1:].isalnum() or span[-1:] == "_" else ""
    return re.sub(f"{lead}{re.escape(span)}{tail}", lambda _m: fix, text)
