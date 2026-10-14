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
    # pronoun | first_person | name (the full name) | name_token (a given name opening
    # a clause, or a surname acting)                            -> blocking
    # pronoun_mention | name_mention | founder_note | opener    -> flagged, never rewritten
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


_BLOCKING_KINDS = {"pronoun", "first_person", "name", "name_token"}


# --------------------------------------------------------------------------- #
# detection

# "them" is left out: "rebuilt 2 of them" refers to things, not to the owner.
# A lookaround on the hyphen keeps "my-sql" and "she-wolf" whole tokens.
_PRONOUN = re.compile(
    r"(?<![\w-])(?:he|she|they|his|her|hers|him|their|theirs|himself|herself)(?![\w-])",
    re.IGNORECASE,
)
_MY = re.compile(r"(?<![\w-])(?:my|My|MY|myself)(?![\w-])")
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
# A capitalised word before an "I" makes it a numeral ("Analyst I", "Engineer I")
# unless that word is only a sentence's opening adverb ("Then I built").
_SENTENCE_ADVERBS = {"then", "later", "now", "when", "while", "after", "before", "today", "and",
                     "but", "so", "also", "first", "next", "finally", "there", "here"}
# Founder lines: "which has 2M users" describes the company; "which built X" narrates
# it. Neither is rewritten; both are left to the health check's advisory.
_FOUNDER = re.compile(r"\b(?:co-?)?founder\b[^.;!?]*?(\bwhich\s+(\w+))", re.IGNORECASE)
_FOUNDER_VERBS = {"built", "shipped", "launched", "created", "developed", "ran", "led", "grew",
                  "has", "have", "had", "serves", "serve", "provides", "provide", "helps", "help",
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
_COPULA = {"is", "am", "are", "was", "were", "be", "been", "has", "have", "had", "does", "did",
           "will", "would", "can", "could", "should", "must", "also"}
_FUNCTION_WORDS = {
    "and", "or", "in", "for", "of", "to", "with", "at", "on", "by", "as", "from", "vs",
    "via", "per", "the", "a", "an", "plus", "into", "about", "through", "over", "after",
    "before", "so", "but",
}


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


_QUOTES = " \t\"'\u201c\u2018\u2022*"


def _sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    start = max((m.end() for m in re.finditer(r"[.!?]\s+", text[:pos])), default=0)
    m = re.search(r"[.!?](?:\s|$)", text[pos:])
    return start, (pos + m.start() + 1 if m else len(text))


_BOUNDARY = r"[.!?;:,]\s+"
# In text the model or a caller wrote, a bracket or a dash opens a clause too.
_WIDE_BOUNDARY = r"(?:" + _BOUNDARY + r"|\(\s*|\s[-\u2013\u2014]\s+|[\u2013\u2014]\s*)"


def _clause_initial(text: str, pos: int, *, wide: bool = False) -> bool:
    """`pos` opens the text, a sentence, or a clause: after `.` `!` `?` `;` `:` or
    a comma, each followed by a space. `wide` adds a bracket and a dash."""
    before = text[:pos]
    pattern = _WIDE_BOUNDARY if wide else _BOUNDARY
    return not before.strip(_QUOTES) or bool(re.search(pattern + "$", before))


def _sentence_initial(text: str, pos: int) -> bool:
    before = text[:pos]
    return not before.strip(_QUOTES) or bool(re.search(r"[.!?]\s+$", before))


def _verb_after(text: str, end: int) -> bool:
    tail = text[end:]
    if re.match(r"['\u2019](?:s|d|ll|ve|m|re)\b", tail):
        return True
    m = re.match(r"\s+([A-Za-z]+)", tail)
    return bool(m) and _verb_like(m.group(1))


def _subject_position(text: str, m: re.Match[str], *, base_line: bool = False) -> bool:
    """A He/She/I that starts a clause, or follows ", where", with a verb next.
    On a line already on the base only a SENTENCE start counts: after `;` `:` or a
    comma a he/she is usually someone the owner mentored, hired or onboarded."""
    if not _verb_after(text, m.end()):
        return False
    opens = _sentence_initial(text, m.start()) if base_line else _clause_initial(
        text, m.start(), wide=True)
    return opens or bool(
        re.search(r",\s*where\s+$", text[: m.start()], re.IGNORECASE)
    )


def _possessive_position(
    text: str, m: re.Match[str], *, shouted: bool, base_line: bool = False
) -> bool:
    """His/her/my that directly modifies a noun in the owner's role: opening a
    clause ("My work reduced…") or right after the clause's verb ("Led his
    team"). "Helped a client grow his business" is someone else's. On a base line
    only the sentence's first clause counts: "Mentored Priya; doubled her output"
    is Priya's."""
    word = m.group(0).lower()
    nxt = re.match(r"\s+([A-Za-z][\w'\u2019-]*)", text[m.end():])
    if not nxt or not nxt.group(1)[0].islower() or nxt.group(1) in _FUNCTION_WORDS:
        return False
    if word == "her" and nxt.group(1) in _OBJECT_FOLLOWERS:
        return False
    before = text[: m.start()]
    if base_line:
        sentence = before[max((c.end() for c in re.finditer(r"[.!?]\s+", before)), default=0):]
        if re.search(_WIDE_BOUNDARY, sentence):
            return False
    cut = max((c.end() for c in re.finditer(_WIDE_BOUNDARY if not base_line else _BOUNDARY, before)),
              default=0)
    words = before[cut:].strip(_QUOTES).split()
    if not words:
        return True
    return not shouted and len(words) == 1 and _verb_like(words[0].strip("(\"'"))


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


def _given_name_opens_clause(masked: str, m: re.Match[str], *, base_line: bool = False) -> bool:
    """"Alex brings 8 years…", "…; Alex cut costs", "Alex, a data engineer, built…":
    the given name opens a sentence or clause, then a lower-case word or a comma.
    A name list ("Led Priya, Alex and Sam") is not that."""
    # On a base line, like he/she, only a sentence start counts.
    if not (_sentence_initial(masked, m.start()) if base_line
            else _clause_initial(masked, m.start(), wide=True)):
        return False
    tail = masked[m.end():]
    word = re.match(r"\s+([a-z][\w'\u2019-]*)", tail)
    if word and word.group(1) not in _FUNCTION_WORDS:
        return True
    if tail.startswith(","):
        # "Austin, TX" and "Austin, Texas" are places; "Alex, a data engineer," is not.
        if not re.match(r",\s+[a-z]", tail):
            return False
        before = masked[: m.start()]
        return not before.strip(_QUOTES) or bool(re.search(r"[.!?;:]\s+$", before))
    return False


def _token_hit(
    masked: str, m: re.Match[str], tokens: list[str], *, given: bool, base_line: bool = False
) -> str | None:
    """How a single name token reads. Only the given name (the first token) can
    block, as "name_token", when it opens a clause as a subject. A surname acting
    or possessing ("Shah built", "Ford's EV team") is the flag-only "name_mention",
    and beside another capitalised word that is not part of the name ("Wells
    Fargo", "Ann Arbor", "Lee & Partners") it is no hit at all."""
    if given and _given_name_opens_clause(masked, m, base_line=base_line):
        return "name_token"
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
    return "name_mention"


def third_person_hits(
    text: str, name: str = "", orgs: Iterable[str] = (), *, base_line: bool = False
) -> list[VoiceHit]:
    """Every place `text` stops being the owner's implied first person, or might.

    Only five shapes block: a clause-initial He/She/I + verb, ", where he/she/I +
    verb", a his/her/my modifying a noun in the owner's role, the full name, and a
    given name opening a clause. They/their, he/she after a noun or relative
    word ("that he wrote"), a capitalised She/He mid-sentence ("Why She Leads"),
    founder clauses, "Builds…" openers and other name tokens are flagged, never
    blocked or rewritten.

    `orgs` (company, school, project names) are blanked first, so a contact name
    inside "Rivera Logistics" and a company called "Her Campus" are safe.

    `base_line` is for a line already on the base, the owner's own words: a
    he/she counts only at a sentence start, a possessive only in the sentence's
    first clause, and brackets and dashes do not open clauses."""
    if not text:
        return []
    hits: list[VoiceHit] = []
    masked = _mask(text, orgs)

    for m in _PRONOUN.finditer(masked):
        word = m.group(0)
        low, shouted = word.lower(), word.isupper() and len(word) > 1
        if low in {"he", "she"} and _subject_position(masked, m, base_line=base_line):
            hits.append(VoiceHit("pronoun", word, m.start(), m.end()))
        elif low in {"his", "her"} and _possessive_position(
            masked, m, shouted=shouted, base_line=base_line
        ):
            hits.append(VoiceHit("pronoun", word, m.start(), m.end()))
        elif not shouted:  # "HE", "HIS": an acronym
            hits.append(VoiceHit("pronoun_mention", word, m.start(), m.end()))
    for m in _MY.finditer(masked):
        word = m.group(0)
        shouted = word == "MY"
        if word != "myself" and _possessive_position(
            masked, m, shouted=shouted, base_line=base_line
        ):
            hits.append(VoiceHit("first_person", word, m.start(), m.end()))
        elif not shouted:
            hits.append(VoiceHit("pronoun_mention", word, m.start(), m.end()))
    for m in _I.finditer(masked):
        before = masked[: m.start()].split()
        if before and before[-1].strip("(,").lower() in _ROMAN_PRECEDERS:
            continue
        if _ROMAN_FOLLOWERS.match(masked[m.end():]):
            continue
        prev = re.search(r"([A-Za-z][\w'\u2019-]*)\s+$", masked[: m.start()])
        if prev and prev.group(1)[0].isupper() and prev.group(1).lower() not in _SENTENCE_ADVERBS:
            continue  # "Analyst I", "Engineer I": a numeral
        if _subject_position(masked, m, base_line=base_line):
            hits.append(VoiceHit("first_person", "I", m.start(), m.end()))
        else:
            hits.append(VoiceHit("pronoun_mention", "I", m.start(), m.end()))

    tokens = _name_tokens(name)
    if tokens:
        phrase = " ".join((name or "").split())
        taken: list[tuple[int, int]] = []
        if len(tokens) > 1 and phrase:
            full = r"(?<!\w)" + r"\s+".join(re.escape(p) for p in phrase.split()) + r"(?!\w)"
            for m in re.finditer(full, masked, re.I):
                hits.append(VoiceHit("name", m.group(0), m.start(), m.end()))
                taken.append((m.start(), m.end()))
        for index, token in enumerate(tokens):
            for m in re.finditer(rf"(?<![\w]){re.escape(token)}(?![\w])", masked, re.I):
                # Case-sensitive: the name as written or as a capitalised word. Lower
                # case ("grant", "li-ion") is an ordinary word, ALL CAPS an acronym.
                if m.group(0) not in (token, token.title(), token.capitalize()):
                    continue
                if any(a <= m.start() < b for a, b in taken):
                    continue
                kind = _token_hit(masked, m, tokens, given=index == 0, base_line=base_line)
                if kind:
                    hits.append(VoiceHit(kind, m.group(0), m.start(), m.end()))

    for m in _FOUNDER.finditer(text):
        if m.group(2).lower() in _FOUNDER_VERBS:
            hits.append(VoiceHit("founder_note", m.group(1), m.start(1), m.end(1)))

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
_OBJECT_FOLLOWERS = {
    "to", "in", "on", "at", "for", "with", "and", "of", "as", "by", "into", "from",
    "about", "through", "over", "after", "before", "so", "but", "or",
}


def _is_past(word: str) -> bool:
    low = word.lower()
    if low.endswith("ed") or low in _PAST_IRREGULAR:
        return True
    # "rebuilt", "overhauled"-style prefixes on an irregular past
    return any(low.startswith(p) and low[len(p):] in _PAST_IRREGULAR
               for p in ("re", "over", "under", "out", "up"))


def _tidy(s: str) -> str:
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+([,;.])", r"\1", s)
    return s.strip()


def _capitalize(s: str) -> str:
    return s[:1].upper() + s[1:]


# Action participles that differ from the simple past: "He has taken", "I have grown".
# State participles (been, done, seen, known, fallen, gotten) are left out on purpose:
# "I have been building" is not "Built", and dropping the auxiliary would misstate it.
_PARTICIPLES = frozenset("taken grown driven written chosen given begun shown spoken broken".split())
_AUX = re.compile(r"(?:['\u2019](?:ve|s|d)|\s+(?:has|have|had))\s+(?P<verb>[A-Za-z]+)")


def _fix_once(s: str, hit: VoiceHit, *, wide: bool = True) -> str | None:
    """One mechanical fix for `hit` in the single sentence `s`, or None when
    anything else would be needed. The only rewrites there are:
    - "He/She/I built X" -> "Built X" (a clause-initial subject before a past verb);
    - ", where he/she/I built X" -> "; built X";
    - a possessive his/her/my after the verb is deleted ("Led his team" -> "Led team");
    - a leading full or given name before a past verb is stripped ("Alex built X").
    Never a join of any other kind, and never a cut."""
    low = hit.text.lower()
    after = re.match(r"(\s+)([A-Za-z]+)", s[hit.end:])

    if hit.kind in {"name", "name_token"} or low in {"he", "she", "i"}:
        rest = None
        if after and _is_past(after.group(2)):
            rest = s[hit.end + len(after.group(1)):]
        elif hit.kind in {"pronoun", "first_person"}:
            # "I've built", "He's built", "He has built": drop the auxiliary too
            aux = _AUX.match(s, hit.end)
            if aux and (_is_past(aux.group("verb")) or aux.group("verb").lower() in _PARTICIPLES):
                rest = s[aux.start("verb"):]
        if rest is None:
            return None
        where = re.search(r",\s*where\s+$", s[: hit.start], re.IGNORECASE)
        if where and hit.kind in {"pronoun", "first_person"}:
            return f"{s[: where.start()]}; {rest}"
        if not _clause_initial(s, hit.start, wide=wide):
            return None
        fixed = s[: hit.start] + rest
        if _sentence_initial(s, hit.start):
            fixed = fixed[: hit.start] + _capitalize(fixed[hit.start:])
        return fixed

    if low in {"his", "her", "my"}:
        if _clause_initial(s, hit.start, wide=wide):
            return None  # "Her team grew…": no subject left once the possessive goes
        return s[: hit.start] + s[hit.end:].lstrip()

    return None


def repair_sentence(
    s: str, name: str = "", orgs: Iterable[str] = (), *, base_line: bool = False
) -> str | None:
    orgs = list(orgs)
    for _ in range(10):
        hits = blocking(third_person_hits(s, name, orgs, base_line=base_line))
        if not hits:
            return _tidy(s) or None
        fixed = _fix_once(s, hits[0], wide=not base_line)
        if fixed is None or fixed == s:
            return None
        s = fixed
    return None


def repair(
    text: str, name: str = "", orgs: Iterable[str] = (), *, conservative: bool = False
) -> str | None:
    """`text` with each blocking hit fixed by `_fix_once`; nothing else is touched.

    Strict (the default, for text the model or a caller wrote): a sentence that
    cannot be fixed that way is dropped, and None comes back when nothing sensible
    is left, so the result never holds a blocking hit. `conservative` is for a line
    already on the base: a sentence that cannot be fixed is kept as written, and
    text always comes back."""
    orgs = list(orgs)
    if not blocking(third_person_hits(text, name, orgs, base_line=conservative)):
        return text
    kept: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        if not blocking(third_person_hits(sentence, name, orgs, base_line=conservative)):
            kept.append(sentence)
            continue
        fixed = repair_sentence(sentence, name, orgs, base_line=conservative)
        if fixed and len(fixed.split()) >= 2:
            if sentence.rstrip().endswith((".", "!", "?")) and not fixed.endswith((".", "!", "?")):
                fixed += sentence.rstrip()[-1]
            kept.append(fixed)
        elif conservative:
            kept.append(sentence)
    result = " ".join(kept).strip()
    if conservative:
        return result or text
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
        unchanged = base_at.get(path) == text
        if unchanged and (path != ("summary",) or not summary_always):
            continue
        hits = blocking(third_person_hits(text, name, orgs, base_line=unchanged))
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
