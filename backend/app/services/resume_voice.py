"""Resume text is the owner's own, in implied first person.

A resume line reads "Built X", never "He built X", "Builds X", "I built X" or
"Alex built X". Nothing in a rewrite prompt can guarantee that, so this module
checks the text in code (`third_person_hits`), words the rule for every prompt
(`VOICE_RULE`), and repairs what slips through conservatively (`repair`): a
clause it cannot fix without inventing words is dropped, and a pronoun is never
stored.

Pure: no DB, no LLM. Word boundaries throughout, so "Heroku" and "other" are
not hits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

VOICE_RULE = (
    "VOICE: this is the resume owner's own resume, written in implied first person. "
    "Lead each bullet with a verb (\"Built X\", not \"Builds X\" or \"He built X\"). "
    "Never write \"I\", \"my\", \"he\", \"she\", \"they\", \"his\", \"her\" or \"their\", "
    "and never use the person's name."
)

# Where the model can learn the fix: the operator's sentence for a caller that
# wrote the text itself (MCP ops) and for the retry.
OPS_ERROR = (
    "Some of the new text reads as written about someone else. Write it in implied "
    "first person: lead with a verb, and use no \"I\", \"my\", \"he\", \"she\", \"they\", "
    "\"his\", \"her\" or \"their\" and no name."
)


@dataclass(frozen=True)
class VoiceHit:
    kind: str  # pronoun | first_person | name | founder_which | opener
    text: str
    start: int
    end: int

    @property
    def blocking(self) -> bool:
        """An opener ("Builds ...") is flagged, never rejected: the word may be a
        noun, and a correct fix needs a tense the code cannot know."""
        return self.kind != "opener"


# --------------------------------------------------------------------------- #
# detection

_PRONOUN = re.compile(
    r"\b(?:he|she|they|his|her|hers|him|them|their|theirs|himself|herself|themselves)\b",
    re.IGNORECASE,
)
_MY = re.compile(r"\b(?:my|My|myself)\b")
_I = re.compile(r"(?<![\w/.\-'])I(?![\w/.\-]|'(?![smvld]))")
# "Phase I", "Type I diabetes", "World War I": a Roman numeral, not the pronoun.
_ROMAN_PRECEDERS = {
    "phase", "phases", "type", "types", "class", "level", "tier", "grade", "stage",
    "part", "series", "step", "group", "category", "tranche", "chapter", "section",
    "title", "form", "schedule", "appendix", "war", "volume", "round", "wave",
    "module", "unit", "act", "book", "generation", "gen", "mark", "mk", "version",
    "release", "sprint", "batch", "cohort", "division", "league", "tour", "exhibit",
}
_FOUNDER_WHICH = re.compile(
    r"\b(?:co-?)?founder\b[^.;!?]*?(\bwhich\s+(?:has|have|had|built|ships?|shipped|"
    r"launched|serves?|served|provides?|helps?)\b)",
    re.IGNORECASE,
)
_SENTENCE_START = re.compile(r"(?:^|(?<=[.!?])\s+)([A-Z][a-z]+)\b")

# Third-person-singular present verbs that open a resume line by mistake. A
# curated stem list: a plain "ends in s" test would flag every plural noun.
_VERB_STEMS = frozenset("""
accelerate achieve act add address advise analyze apply architect assess assist
automate begin build cache champion clean coach collaborate combine communicate
configure connect consolidate construct consult contribute convert coordinate
create cut debug define deliver deploy design detect develop diagnose direct
document drive drives eliminate enable engineer enhance ensure establish
evaluate execute expand extract facilitate fix forecast found generate guide
handle help identify implement improve increase integrate introduce investigate
launch lead leverage maintain manage map measure mentor migrate model monitor
negotiate operate optimize orchestrate organize oversee own partner perform
pilot plan present prioritize process produce program prototype provide publish
reduce refactor release research resolve restructure review roll run scale
schedule ship simplify solve spearhead streamline strengthen support
supervise test track train transform translate triage tune turn use validate
work write
""".split())


def _verb_opener(word: str) -> bool:
    low = word.lower()
    if not low.endswith("s") or len(low) < 4:
        return False
    stems = {low[:-1], low[:-2]}
    if low.endswith("ies"):
        stems.add(low[:-3] + "y")
    return bool(stems & _VERB_STEMS)


def _name_tokens(name: str) -> list[str]:
    tokens = [re.sub(r"[^\w'’-]", "", t) for t in (name or "").split()]
    return [t for t in tokens if len(t) >= 3 and t.lower() not in {"jr", "sr", "phd", "mba", "mrs", "miss"}]


def _mask(text: str, names: Iterable[str]) -> str:
    """`text` with each org name blanked to spaces (same length, so hit offsets
    stay valid): a contact name inside "Rivera Logistics" is the company."""
    masked = text
    for org in sorted({n.strip() for n in names if n and len(n.strip()) >= 3}, key=len, reverse=True):
        masked = re.sub(
            re.escape(org), lambda m: " " * len(m.group(0)), masked, flags=re.IGNORECASE
        )
    return masked


def third_person_hits(
    text: str, name: str = "", orgs: Iterable[str] = ()
) -> list[VoiceHit]:
    """Every place `text` stops being the owner's implied first person.

    `name` is the contact name; its tokens count as hits except inside an `orgs`
    name (company, school, project). Hits are sorted by position. Only
    `opener` hits are non-blocking."""
    if not text:
        return []
    hits: list[VoiceHit] = []

    for m in _PRONOUN.finditer(text):
        word = m.group(0)
        if len(word) > 1 and word.isupper():  # "HE", "HER": an acronym
            continue
        hits.append(VoiceHit("pronoun", word, m.start(), m.end()))
    for m in _MY.finditer(text):
        hits.append(VoiceHit("first_person", m.group(0), m.start(), m.end()))
    for m in _I.finditer(text):
        before = text[: m.start()].split()
        if before and before[-1].strip("(,").lower() in _ROMAN_PRECEDERS:
            continue
        hits.append(VoiceHit("first_person", "I", m.start(), m.end()))

    tokens = _name_tokens(name)
    if tokens:
        masked = _mask(text, orgs)
        phrase = " ".join((name or "").split())
        taken: list[tuple[int, int]] = []
        if len(tokens) > 1 and phrase:
            for m in re.finditer(r"\s+".join(re.escape(p) for p in phrase.split()), masked, re.I):
                hits.append(VoiceHit("name", m.group(0), m.start(), m.end()))
                taken.append((m.start(), m.end()))
        for token in tokens:
            for m in re.finditer(rf"(?<![\w]){re.escape(token)}(?![\w])", masked, re.I):
                if not m.group(0)[0].isupper():
                    continue  # lower-case "grant", "will": an ordinary word
                if any(a <= m.start() < b for a, b in taken):
                    continue
                hits.append(VoiceHit("name", m.group(0), m.start(), m.end()))

    for m in _FOUNDER_WHICH.finditer(text):
        hits.append(VoiceHit("founder_which", m.group(1), m.start(1), m.end(1)))

    for m in _SENTENCE_START.finditer(text):
        if _verb_opener(m.group(1)):
            hits.append(VoiceHit("opener", m.group(1), m.start(1), m.end(1)))

    return sorted(hits, key=lambda h: (h.start, h.end))


def blocking(hits: Iterable[VoiceHit]) -> list[VoiceHit]:
    return [h for h in hits if h.blocking]


# --------------------------------------------------------------------------- #
# repair

_PAST_IRREGULAR = frozenset("""
built led ran wrote made drove grew took won began sold taught brought set put cut
held kept found gave got saw chose spoke fell sent spent met paid taught thought
rose broke wove forged oversaw undertook overhauled
""".split())
_SUBJECT = re.compile(
    r"(?P<lead>\s*[,;]?\s*(?:(?:where|and|while|who|when|after|as|but|then|so)\s+)?)"
    r"\b(?P<subj>he|she|they|I)\s+(?:(?:has|had|have)\s+)?(?P<verb>[A-Za-z]+)",
    re.IGNORECASE,
)
_WHICH = re.compile(
    r"(?P<lead>\s*,?\s*)(?P<which>\bwhich)\s+(?:(?:has|have|had)\s+)?(?P<verb>[A-Za-z]+)",
    re.IGNORECASE,
)
_OBJECT_FOLLOWERS = {
    "to", "in", "on", "at", "for", "with", "and", "of", "as", "by", "into", "from",
    "about", "through", "over", "after", "before", "so", "but", "or",
}
_THIRD_SINGULAR_NEXT = {"is", "has", "was", "does", "brings", "specializes", "works"}


def _is_past(word: str) -> bool:
    low = word.lower()
    return low.endswith("ed") or low in _PAST_IRREGULAR


def _clause_end(s: str, pos: int) -> int:
    """End of the clause holding `pos`: the next comma or semicolon, else just
    before the sentence's closing punctuation."""
    m = re.compile(r"[,;]").search(s, pos)
    if m:
        return m.start()
    return len(s.rstrip().rstrip(".!?"))


def _drop_clause(s: str, start: int, pos: int) -> str | None:
    """`s` without the clause that begins at `start` (a delimiter or connector
    position) and holds `pos`."""
    end = _clause_end(s, pos)
    return (s[:start] + s[end:]).strip()


def _clause_start(s: str, pos: int) -> int | None:
    """Start of the delimiter that opens the clause holding `pos`, None for the head."""
    cut = max(s.rfind(",", 0, pos), s.rfind(";", 0, pos))
    return cut if cut >= 0 else None


def _tidy(s: str) -> str:
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+([,;.])", r"\1", s)
    s = re.sub(r"[,;]\s*([,;])", r"\1", s)
    s = re.sub(r"^[\s,;:.\-]+", "", s)
    s = re.sub(r"[,;]\s*$", "", s)
    return s.strip()


def _capitalize(s: str) -> str:
    return s[:1].upper() + s[1:]


def _fix_once(s: str, hit: VoiceHit, name: str) -> str | None:
    """One conservative fix for `hit` in the single sentence `s`; None when the
    only safe move is to give the sentence up."""
    low = hit.text.lower()

    if hit.kind == "founder_which":
        for m in _WHICH.finditer(s):
            if m.start("which") == hit.start:
                return _join_clause(s, m)
        return None

    if hit.kind == "name":
        if hit.start == 0 or not s[: hit.start].strip():
            rest = s[hit.end:]
            if rest.startswith(("'s", "’s")):
                return None
            rest = rest.lstrip()
            first = re.match(r"[A-Za-z]+", rest)
            if not first or first.group(0).lower() in _THIRD_SINGULAR_NEXT or _verb_opener(
                first.group(0)
            ):
                return None
            return _capitalize(rest)
        tail = s[hit.end:]
        if tail.startswith(("'s ", "’s ")):
            return s[: hit.start] + tail[3:]
        clause = _clause_start(s, hit.start)
        return None if clause is None else _drop_clause(s, clause, hit.start)

    if low in {"he", "she", "they", "i"}:
        for m in _SUBJECT.finditer(s):
            if m.start("subj") == hit.start:
                return _join_clause(s, m)
        clause = _clause_start(s, hit.start)
        return None if clause is None else _drop_clause(s, clause, hit.start)

    if low in {"his", "their", "my"} or (
        low == "her" and _possessive_her(s, hit.end)
    ):
        if not s[: hit.start].strip():
            return None
        # Deleting the determiner invents nothing: "Led his team" -> "Led team".
        return s[: hit.start] + s[hit.end:].lstrip()

    clause = _clause_start(s, hit.start)
    return None if clause is None else _drop_clause(s, clause, hit.start)


def _possessive_her(s: str, end: int) -> bool:
    m = re.match(r"\s+([A-Za-z]+)", s[end:])
    return bool(m) and m.group(1).lower() not in _OBJECT_FOLLOWERS


def _join_clause(s: str, m: re.Match[str]) -> str | None:
    """"…, where he built X" -> "…; built X", when the verb is past tense.
    A subject opening the sentence just loses the pronoun. Any other verb form
    ("where he leads") cannot be fixed without choosing a tense: the clause goes."""
    verb = m.group("verb")
    if m.start("lead") == 0 and not s[: m.start("subj")].strip():
        if not _is_past(verb):
            return None
        return _capitalize(s[m.start("verb"):])
    head = s[: m.start("lead")].rstrip(" ,;")
    if not head:
        return None
    if _is_past(verb):
        return f"{head}; {s[m.start('verb'):]}"
    return _drop_clause(s, m.start("lead"), m.end())


def repair_sentence(
    s: str, name: str = "", orgs: Iterable[str] = ()
) -> str | None:
    orgs = list(orgs)
    for _ in range(10):
        hits = blocking(third_person_hits(s, name, orgs))
        if not hits:
            return _tidy(s) or None
        fixed = _fix_once(s, hits[0], name)
        if fixed is None or fixed == s:
            return None
        s = fixed
    return None


def repair(text: str, name: str = "", orgs: Iterable[str] = ()) -> str | None:
    """`text` with every third-person clause repaired or dropped, None when
    nothing sensible is left. The result never holds a blocking hit."""
    orgs = list(orgs)
    if not blocking(third_person_hits(text, name, orgs)):
        return text
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        if not blocking(third_person_hits(sentence, name, orgs)):
            kept.append(sentence)
            continue
        fixed = repair_sentence(sentence, name, orgs)
        if fixed and len(fixed.split()) >= 3:
            if sentence.rstrip().endswith((".", "!", "?")) and not fixed.endswith((".", "!", "?")):
                fixed += sentence.rstrip()[-1]
            kept.append(fixed)
    result = " ".join(kept).strip()
    if not result or blocking(third_person_hits(result, name, orgs)):
        return None
    return result


# --------------------------------------------------------------------------- #
# a whole resume

Path = tuple[Any, ...]


def org_names(resume: dict[str, Any]) -> list[str]:
    """Company, school, project and certification names on the resume: places a
    contact name legitimately appears ("Rivera Logistics")."""
    names: list[str] = []
    for entry in resume.get("experience") or []:
        names.append(str(entry.get("company") or ""))
    for entry in resume.get("projects") or []:
        names.append(str(entry.get("name") or ""))
    for entry in resume.get("education") or []:
        names.append(str(entry.get("institution") or ""))
    names.extend(str(c) for c in resume.get("certifications") or [])
    for section in resume.get("extra_sections") or []:
        for entry in section.get("entries") or []:
            names.append(str(entry.get("heading") or ""))
    return [n for n in names if n.strip()]


def contact_name(resume: dict[str, Any]) -> str:
    return str((resume.get("contact") or {}).get("name") or "")


def slots(resume: dict[str, Any]) -> list[tuple[Path, str]]:
    """(path, text) of the prose: the summary and every bullet."""
    out: list[tuple[Path, str]] = []
    if isinstance(resume.get("summary"), str):
        out.append((("summary",), resume["summary"]))
    for section in ("experience", "projects", "education"):
        for i, entry in enumerate(resume.get(section) or []):
            for j, bullet in enumerate(entry.get("bullets") or []):
                out.append(((section, i, "bullets", j), str(bullet)))
    for i, sec in enumerate(resume.get("extra_sections") or []):
        for j, bullet in enumerate(sec.get("bullets") or []):
            out.append((("extra_sections", i, "bullets", j), str(bullet)))
        for k, entry in enumerate(sec.get("entries") or []):
            for j, bullet in enumerate(entry.get("bullets") or []):
                out.append((("extra_sections", i, "entries", k, "bullets", j), str(bullet)))
    return out


def _get(resume: dict[str, Any], path: Path) -> Any:
    node: Any = resume
    for key in path:
        node = node[key]
    return node


def changed_hits(
    base: dict[str, Any], customized: dict[str, Any]
) -> list[tuple[Path, str, list[VoiceHit]]]:
    """Blocking hits in text the edit set wrote: a line that is not already,
    word for word, somewhere on the base resume."""
    known = {text for _, text in slots(base)}
    name = contact_name(customized) or contact_name(base)
    orgs = org_names(base) + org_names(customized)
    found = []
    for path, text in slots(customized):
        if text in known:
            continue
        hits = blocking(third_person_hits(text, name, orgs))
        if hits:
            found.append((path, text, hits))
    return found


def correction(problems: list[tuple[Path, str, list[VoiceHit]]]) -> str:
    quoted = "; ".join(json_quote(text) for _, text, _ in problems[:6])
    return (
        "CORRECTION REQUIRED: these lines read as written about someone else "
        f"({quoted}). Return a complete corrected ops list. {VOICE_RULE}"
    )


def json_quote(text: str) -> str:
    import json

    return json.dumps(text, ensure_ascii=False)


def repair_resume(base: dict[str, Any], customized: dict[str, Any]) -> list[Path]:
    """Repair `customized` in place wherever the edit set wrote third-person
    text; returns the paths it touched.

    A line that cannot be repaired is put back as the base had it (when the base
    entry still lines up) or removed. A summary falls back to the base summary.
    Nothing stored afterwards holds a pronoun the edit set wrote."""
    problems = changed_hits(base, customized)
    if not problems:
        return []
    name = contact_name(customized) or contact_name(base)
    orgs = org_names(base) + org_names(customized)
    removals: list[Path] = []
    touched: list[Path] = []
    for path, text, _ in problems:
        fixed = repair(text, name, orgs)
        parent = _get(customized, path[:-1]) if len(path) > 1 else customized
        if fixed:
            parent[path[-1]] = fixed
        elif path == ("summary",):
            parent["summary"] = base.get("summary", "")
        else:
            original = _original_bullet(base, path, customized)
            if original is None:
                removals.append(path)
            else:
                parent[path[-1]] = original
        touched.append(path)
    for path in sorted(removals, key=lambda p: p[-1], reverse=True):
        del _get(customized, path[:-1])[path[-1]]
    return touched


def _original_bullet(base: dict[str, Any], path: Path, customized: dict[str, Any]) -> str | None:
    try:
        old = _get(base, path[:-1])
        new = _get(customized, path[:-1])
        if len(old) == len(new):
            return str(old[path[-1]])
    except (KeyError, IndexError, TypeError):
        pass
    return None
