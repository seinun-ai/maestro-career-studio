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

_RULE_BODY = (
    "written in implied first person. Lead each bullet with a verb (\"Built X\", not \"Builds X\" "
    "or \"He built X\"). Never write \"I\", \"my\", \"he\", \"she\", \"they\", \"his\", \"her\" or "
    "\"their\", and never use the person's name."
)
VOICE_RULE = f"VOICE: this is the resume owner's own resume, {_RULE_BODY}"
# Chat also writes first-person posts, so its rule is scoped to the text it saves
# to a resume or the Career KB.
CHAT_VOICE_RULE = (
    "VOICE, for resume and Career KB text passed to edit_resume, propose_edits or kb_capture "
    "(not for chat replies or social posts): that text is the resume owner's own, " + _RULE_BODY
)

# Where the model can learn the fix: the operator's sentence for a caller that
# wrote the text itself (MCP ops) and for the retry.
OPS_ERROR = (
    "Some of the resume text reads as written about someone else. Write it in implied "
    "first person: lead with a verb, and use no \"I\", \"my\", \"he\", \"she\", \"they\", "
    "\"his\", \"her\" or \"their\" and no name."
)


@dataclass(frozen=True)
class VoiceHit:
    # pronoun | first_person | name (the full name) | name_token (one token, subject or
    # possessive position) | founder_which                      -> blocking
    # name_mention | founder_note | opener                      -> flagged, never rewritten
    kind: str
    text: str
    start: int
    end: int

    @property
    def blocking(self) -> bool:
        """Only a hit that is unambiguous blocks or is rewritten. The rest are
        ambiguous (a word that may be a noun, a company, a place) and are left to
        the health check's advisory."""
        return self.kind in _BLOCKING_KINDS


_BLOCKING_KINDS = {"pronoun", "first_person", "name", "name_token", "founder_which"}


# --------------------------------------------------------------------------- #
# detection

# "them" is left out: "rebuilt 2 of them" refers to things, not to the owner.
_PRONOUN = re.compile(
    r"\b(?:he|she|they|his|her|hers|him|their|theirs|himself|herself)\b",
    re.IGNORECASE,
)
_MY = re.compile(r"\b(?:my|My|myself|MY)\b")
_I = re.compile(r"(?<![\w/.\-'])I(?![\w/.\-]|'(?![smvld]))")
# "Phase I", "Type I diabetes", "World War I": a Roman numeral, not the pronoun.
_ROMAN_PRECEDERS = {
    "phase", "phases", "type", "types", "class", "level", "tier", "grade", "stage",
    "part", "series", "step", "group", "category", "tranche", "chapter", "section",
    "title", "form", "schedule", "appendix", "war", "volume", "round", "wave",
    "module", "unit", "act", "book", "generation", "gen", "mark", "mk", "version",
    "release", "sprint", "batch", "cohort", "division", "league", "tour", "exhibit",
    "annex", "calculus", "algebra", "physics", "chemistry", "biology", "statistics",
    "accounting", "economics", "anatomy", "studio", "lab",
}
_ROMAN_FOLLOWERS = re.compile(r"\s*(?:,|and|&|-|\u2013|/)\s*(?:II|III|IV|V|VI|VII|VIII|IX|X)\b")
_FOUNDER = re.compile(r"\b(?:co-?)?founder\b[^.;!?]*?(\bwhich\s+(\w+))", re.IGNORECASE)
# What follows "which" in a founder line: past-tense achievements are third-person
# narration; "which has 2M users" or "which serves clinics" describes the company.
_FOUNDER_PAST = {"built", "shipped", "launched", "created", "developed", "ran", "led", "grew"}
_FOUNDER_SOFT = {"has", "have", "had", "serves", "serve", "provides", "provide", "helps", "help",
                 "employs", "employ", "supports", "support", "ships", "ship"}
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
_COPULA = {"is", "has", "was", "does", "did", "also", "now", "then"}


def _verb_opener(word: str) -> bool:
    low = word.lower()
    if not low.endswith("s") or len(low) < 4:
        return False
    stems = {low[:-1], low[:-2]}
    if low.endswith("ies"):
        stems.add(low[:-3] + "y")
    return bool(stems & _VERB_STEMS)


def _verb_like(word: str) -> bool:
    low = word.lower()
    return low in _VERB_STEMS or low in _COPULA or _is_past(low) or _verb_opener(low)


def _sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    start = max((m.end() for m in re.finditer(r"[.!?]\s+", text[:pos])), default=0)
    m = re.search(r"[.!?](?:\s|$)", text[pos:])
    return start, (pos + m.start() + 1 if m else len(text))


def _caps_reads_as_pronoun(text: str, m: re.Match[str]) -> bool:
    """An all-caps "HE" or "MY" is a shouted pronoun only when it opens a
    sentence ahead of a verb-like word ("HE built", "HE BUILT"), or sits in a
    sentence that is mostly upper case. Anywhere else ("the HIS integration",
    "HE sector", "HE (Higher Education)", "MY-SQL") it is an acronym."""
    nxt = re.match(r"\s+([A-Za-z]+)", text[m.end():])
    if not nxt or not _verb_like(nxt.group(1)):
        return False
    start, end = _sentence_bounds(text, m.start())
    if not text[start:m.start()].strip(" \t\"'(["):
        return True
    words = re.findall(r"[A-Za-z]{2,}", text[start:end])
    return len(words) >= 4 and sum(w.isupper() for w in words) / len(words) >= 0.8


_NAME_SKIP = {"jr", "sr", "ii", "iii", "iv", "phd", "mba", "md", "dr", "mr", "ms", "mrs", "miss"}
_NAME_CONNECTORS = {"where", "and", "while", "who", "when", "after", "as", "but", "so", "then",
                    "that", "because"}


def _name_tokens(name: str) -> list[str]:
    tokens = [re.sub(r"[^\w'\u2019-]", "", t) for t in (name or "").split()]
    # Two letters is a name ("Li", "Xu"); a single letter is an initial.
    return [t for t in tokens if len(t) >= 2 and t.lower() not in _NAME_SKIP]


def _mask(text: str, names: Iterable[str]) -> str:
    """`text` with each org name blanked to spaces (same length, so hit offsets
    stay valid): a contact name inside "Rivera Logistics" is the company, and
    "Her Campus" is not a pronoun."""
    masked = text
    for org in sorted({n.strip() for n in names if n and len(n.strip()) >= 3}, key=len, reverse=True):
        masked = re.sub(
            re.escape(org), lambda m: " " * len(m.group(0)), masked, flags=re.IGNORECASE
        )
    return masked


def _token_hit(text: str, masked: str, m: re.Match[str], tokens: list[str]) -> str | None:
    """How a single name token reads: "name_token" in subject or possessive
    position, None beside another capitalised word that is not part of the name
    ("Wells Fargo", "Ann Arbor", "Lee & Partners"), else the flag-only
    "name_mention"."""
    others = {t.lower() for t in tokens}
    before = re.search(r"([A-Za-z&][\w'\u2019&-]*)\s+$", masked[: m.start()])
    after = re.match(r"\s+([A-Za-z&][\w'\u2019&-]*)", masked[m.end():])
    for neighbour in (before, after):
        if neighbour:
            word = neighbour.group(1)
            # A capitalised verb ("Led", "Built") is just a sentence's first word.
            if (
                (word[0].isupper() or word == "&")
                and word.lower() not in others
                and not _verb_like(word)
            ):
                return None
    tail = masked[m.end():]
    if tail.startswith(("'s", "\u2019s")):
        return "name_token"
    following = after.group(1) if after else ""
    if following.lower() in {"is", "has", "was", "does"}:
        return "name_token"
    if following and _verb_like(following):
        start, _ = _sentence_bounds(masked, m.start())
        lead = masked[start:m.start()].strip(" \t\"'(")
        prior = lead.split()[-1].lower() if lead.split() else ""
        if not lead or prior in _NAME_CONNECTORS:
            return "name_token"
    return "name_mention"


def third_person_hits(
    text: str, name: str = "", orgs: Iterable[str] = ()
) -> list[VoiceHit]:
    """Every place `text` stops being the owner's implied first person, or might.

    `name` is the contact name; `orgs` are company, school and project names,
    which are blanked first (a contact name inside "Rivera Logistics", a company
    called "Her Campus"). Hits are sorted by position. Only unambiguous kinds are
    `blocking`; see `VoiceHit`."""
    if not text:
        return []
    hits: list[VoiceHit] = []
    masked = _mask(text, orgs)

    for m in _PRONOUN.finditer(masked):
        word = m.group(0)
        if word.isupper() and not _caps_reads_as_pronoun(masked, m):  # "HE": an acronym
            continue
        hits.append(VoiceHit("pronoun", word, m.start(), m.end()))
    for m in _MY.finditer(masked):
        word = m.group(0)
        if word.isupper() and not _caps_reads_as_pronoun(masked, m):  # "MY": a country code
            continue
        hits.append(VoiceHit("first_person", word, m.start(), m.end()))
    for m in _I.finditer(masked):
        before = masked[: m.start()].split()
        if before and before[-1].strip("(,").lower() in _ROMAN_PRECEDERS:
            continue
        if _ROMAN_FOLLOWERS.match(masked[m.end():]):
            continue
        hits.append(VoiceHit("first_person", "I", m.start(), m.end()))

    tokens = _name_tokens(name)
    if tokens:
        phrase = " ".join((name or "").split())
        taken: list[tuple[int, int]] = []
        if len(tokens) > 1 and phrase:
            full = r"(?<!\w)" + r"\s+".join(re.escape(p) for p in phrase.split()) + r"(?!\w)"
            for m in re.finditer(full, masked, re.I):
                hits.append(VoiceHit("name", m.group(0), m.start(), m.end()))
                taken.append((m.start(), m.end()))
        for token in tokens:
            for m in re.finditer(rf"(?<![\w]){re.escape(token)}(?![\w])", masked, re.I):
                # Case-sensitive: the name as written or as a capitalised word. Lower
                # case ("grant", "li-ion") is an ordinary word, ALL CAPS an acronym.
                if m.group(0) not in (token, token.title(), token.capitalize()):
                    continue
                if any(a <= m.start() < b for a, b in taken):
                    continue
                kind = _token_hit(text, masked, m, tokens)
                if kind:
                    hits.append(VoiceHit(kind, m.group(0), m.start(), m.end()))

    for m in _FOUNDER.finditer(text):
        verb = m.group(2).lower()
        after = re.match(r"\s+(\w+)", text[m.end():])
        past = verb in _FOUNDER_PAST or (
            verb in {"has", "have", "had"} and bool(after) and _is_past(after.group(1))
        )
        if past:
            hits.append(VoiceHit("founder_which", m.group(1), m.start(1), m.end(1)))
        elif verb in _FOUNDER_SOFT:
            hits.append(VoiceHit("founder_note", m.group(1), m.start(1), m.end(1)))

    for m in _SENTENCE_START.finditer(text):
        if _verb_opener(m.group(1)):
            hits.append(VoiceHit("opener", m.group(1), m.start(1), m.end(1)))

    return sorted(hits, key=lambda h: (h.start, h.end))


def blocking(hits: Iterable[VoiceHit]) -> list[VoiceHit]:
    return [h for h in hits if h.blocking]


def _clean_target(hit: VoiceHit) -> bool:
    """The hits a line the edit did not write may be repaired for: a lower-case
    pronoun or the full name. Everything else is left to the health check."""
    return (hit.kind == "pronoun" and not hit.text.isupper()) or hit.kind == "name"


# --------------------------------------------------------------------------- #
# repair

_PAST_IRREGULAR = frozenset("""
built led ran wrote made drove grew took won began sold taught brought set put cut
held kept found gave got saw chose spoke fell sent spent met paid taught thought
rose broke wove forged oversaw undertook overhauled
""".split())
# Subordinators change what a clause means ("after he left"), so joining it with
# a semicolon would misstate the line: the clause is dropped instead.
_JOINABLE = {None, "where", "and"}
_SUBJECT = re.compile(
    r"(?P<lead>\s*[,;]?\s*(?:(?P<conn>where|and|while|who|when|after|as|but|then|so|because|"
    r"before|since)\s+)?)"
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


def _drop_clause(s: str, start: int, pos: int, clean: bool) -> str | None:
    """`s` without the clause that begins at `start` (a delimiter or connector
    position) and holds `pos`. None in `clean` mode: a line the edit did not
    write is never cut."""
    if clean:
        return None
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


def _fix_once(s: str, hit: VoiceHit, name: str, clean: bool) -> str | None:
    """One conservative fix for `hit` in the single sentence `s`; None when the
    only safe move is to give the sentence up (`clean`: when anything but a
    mechanical fix would be needed)."""
    low = hit.text.lower()

    if hit.kind == "founder_which":
        for m in _WHICH.finditer(s):
            if m.start("which") == hit.start:
                return _join_clause(s, m, clean)
        return None

    if hit.kind in {"name", "name_token"}:
        if hit.start == 0 or not s[: hit.start].strip():
            rest = s[hit.end:]
            if rest.startswith(("'s", "\u2019s")):
                return None
            rest = rest.lstrip()
            first = re.match(r"[A-Za-z]+", rest)
            if not first or first.group(0).lower() in _THIRD_SINGULAR_NEXT or _verb_opener(
                first.group(0)
            ):
                return None
            return _capitalize(rest)
        tail = s[hit.end:]
        if tail.startswith(("'s ", "\u2019s ")):
            return s[: hit.start] + tail[3:]
        clause = _clause_start(s, hit.start)
        return None if clause is None else _drop_clause(s, clause, hit.start, clean)

    if low in {"he", "she", "they", "i"}:
        for m in _SUBJECT.finditer(s):
            if m.start("subj") == hit.start:
                return _join_clause(s, m, clean)
        clause = _clause_start(s, hit.start)
        return None if clause is None else _drop_clause(s, clause, hit.start, clean)

    if low in {"his", "their", "my"} or (
        low == "her" and _possessive_her(s, hit.end)
    ):
        if not s[: hit.start].strip():
            return None
        # Deleting the determiner invents nothing: "Led his team" -> "Led team".
        return s[: hit.start] + s[hit.end:].lstrip()

    clause = _clause_start(s, hit.start)
    return None if clause is None else _drop_clause(s, clause, hit.start, clean)


def _possessive_her(s: str, end: int) -> bool:
    m = re.match(r"\s+([A-Za-z]+)", s[end:])
    return bool(m) and m.group(1).lower() not in _OBJECT_FOLLOWERS


def _join_clause(s: str, m: re.Match[str], clean: bool) -> str | None:
    """"…, where he built X" -> "…; built X", when the verb is past tense and the
    connector is "where", "and" or a bare comma. After an opening bracket, colon
    or dash the clause joins with a space instead. A subordinator ("after he
    left") or a verb that is not past tense ("where he leads") cannot be fixed
    without changing or choosing a meaning: the clause goes (never, in `clean`
    mode). A subject opening the sentence just loses the pronoun."""
    verb = m.group("verb")
    conn = (m.groupdict().get("conn") or "").lower() or None
    if m.start("lead") == 0 and not s[: m.start("subj" if "subj" in m.groupdict() else "which")].strip():
        if conn or not _is_past(verb):
            return None
        return _capitalize(s[m.start("verb"):])
    head = s[: m.start("lead")].rstrip(" ,;")
    if not head:
        return None
    if _is_past(verb) and conn in _JOINABLE:
        rest = s[m.start("verb"):]
        if head.endswith("("):
            return f"{head}{rest}"
        if head.endswith((":", "-", "\u2013", "\u2014")):
            return f"{head} {rest}"
        return f"{head}; {rest}"
    return _drop_clause(s, m.start("lead"), m.end(), clean)


def repair_sentence(
    s: str,
    name: str = "",
    orgs: Iterable[str] = (),
    *,
    select=lambda h: h.blocking,
    clean: bool = False,
) -> str | None:
    orgs = list(orgs)
    for _ in range(10):
        hits = [h for h in third_person_hits(s, name, orgs) if select(h)]
        if not hits:
            return _tidy(s) or None
        fixed = _fix_once(s, hits[0], name, clean)
        if fixed is None or fixed == s:
            return None
        s = fixed
    return None


def repair(
    text: str, name: str = "", orgs: Iterable[str] = (), *, conservative: bool = False
) -> str | None:
    """`text` with every blocking third-person clause repaired or dropped, None
    when nothing sensible is left; the result never holds a blocking hit.

    `conservative` is for a line the edit did not write (text already on the
    base): only a lower-case pronoun or the full name is touched, only by a fix
    that adds and cuts nothing but the pronoun, and what cannot be fixed that way
    is kept as written. It always returns text."""
    orgs = list(orgs)
    select = _clean_target if conservative else (lambda h: h.blocking)
    if not [h for h in third_person_hits(text, name, orgs) if select(h)]:
        return text
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        if not [h for h in third_person_hits(sentence, name, orgs) if select(h)]:
            kept.append(sentence)
            continue
        fixed = repair_sentence(sentence, name, orgs, select=select, clean=conservative)
        if fixed and len(fixed.split()) >= 2:
            if sentence.rstrip().endswith((".", "!", "?")) and not fixed.endswith((".", "!", "?")):
                fixed += sentence.rstrip()[-1]
            kept.append(fixed)
        elif conservative:
            kept.append(sentence)
    result = " ".join(kept).strip()
    if conservative:
        return result or text
    if not result or [h for h in third_person_hits(result, name, orgs) if select(h)]:
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
    base: dict[str, Any], customized: dict[str, Any], *, summary_always: bool = True
) -> list[tuple[Path, str, list[VoiceHit]]]:
    """Blocking hits that are the edit set's to answer for: the summary always,
    and any bullet that is not, in the same place, what the base had. A base
    line copied into a changed bullet counts; an unchanged one in place does
    not (it is still repaired before storage, see `repair_resume`).

    `summary_always=False` treats the summary like a bullet: a caller who did not
    change it is not answerable for it (the MCP ops path)."""
    base_at = dict(slots(base))
    name = contact_name(customized) or contact_name(base)
    orgs = org_names(base) + org_names(customized)
    found = []
    for path, text in slots(customized):
        if (path != ("summary",) or not summary_always) and base_at.get(path) == text:
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


def ops_error(problems: list[tuple[Path, str, list[VoiceHit]]]) -> str:
    """The 400 sentence for a caller's ops: what to do, and which lines."""
    quoted = "; ".join(json_quote(text) for _, text, _ in problems[:3])
    return f"{OPS_ERROR} Lines to fix: {quoted}."


def json_quote(text: str) -> str:
    import json

    return json.dumps(text, ensure_ascii=False)


def format_path(path: Path) -> str:
    """`("experience", 0, "bullets", 2)` -> `experience[0].bullets[2]`."""
    out = ""
    for key in path:
        out += f"[{key}]" if isinstance(key, int) else (f".{key}" if out else str(key))
    return out


def repair_resume(base: dict[str, Any], customized: dict[str, Any]) -> list[Path]:
    """Repair `customized` in place; returns the paths touched.

    Text the edit wrote (a summary or bullet that differs from the base at the
    same place) is held to the strict rule: repaired, else put back as the base
    had it, else removed (a summary keeps only its clean sentences). A line left
    as the base had it is repaired only where that is mechanical (a lower-case
    pronoun or the full name) and is never cut or dropped: whatever stays
    ambiguous is the health check's to flag."""
    name = contact_name(customized) or contact_name(base)
    orgs = org_names(base) + org_names(customized)
    base_at = dict(slots(base))
    removals: list[Path] = []
    touched: list[Path] = []
    for path, text in slots(customized):
        parent = _get(customized, path[:-1]) if len(path) > 1 else customized
        if base_at.get(path) == text:
            fixed = repair(text, name, orgs, conservative=True)
            if fixed != text:
                parent[path[-1]] = fixed
                touched.append(path)
            continue
        if not blocking(third_person_hits(text, name, orgs)):
            continue
        fixed = repair(text, name, orgs)
        if fixed is None:
            original = (
                str(base.get("summary") or "") if path == ("summary",)
                else _original_bullet(base, path, customized)
            )
            fixed = repair(original, name, orgs, conservative=True) if original else None
        if fixed is not None:
            parent[path[-1]] = fixed
        elif path == ("summary",):
            parent["summary"] = ""
        else:
            removals.append(path)
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


def identity(resume: dict[str, Any]) -> tuple[str, list[str]]:
    """(contact name, org names) for `third_person_hits`."""
    return contact_name(resume), org_names(resume)
