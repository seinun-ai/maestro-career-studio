# Health-check rubric

> Reference tier of [SYSTEM.md](../SYSTEM.md). Its living-document contract applies.
> This rubric says what the evaluator judges and why. The code's contract (fields, endpoints, errors) is
> `docs/entities/others.md`, ResumeLintReport; where the two disagree, the code wins and this file is fixed.

- **Evidence tags** [weak]: strong means direct empirical evidence, moderate means career-service
  guidance or surveys, and weak means a product heuristic. These tags describe support for the principle,
  not scientific validation of our exact scores. Source: the approved health-check design.
- **A strong bullet** [moderate]: state a specific action and a concrete result. A result can be a
  measure, a decision and its effect, a named adopter, recognition with its selector, or a problem
  solved with its consequence. Source: [Harvard resume guidance](https://careerservices.fas.harvard.edu/resources/create-a-strong-resume/).
- **Numbers** [moderate]: ask for a measure only when it fits the work and the text names what to
  measure. Always offer a question that can be answered without a number. A qualitative result can
  earn full credit. Source: [MIT career toolkit](https://capd.mit.edu/resources/career-toolkit-crafting-an-effective-resume/).

## Levels

**The five levels** [weak] are product judgments, not validated hiring probabilities. Source: the
approved evaluator contract. Code validates the model response and computes scores; the prompt judges.

| Level | Value | Meaning |
|---|---|---|
| `direct` | 1.0 | Specific action + a concrete result: measured, OR clearly stated qualitatively (a named decision and its effect, a named adopter, a launch to named users, recognition with its selector, a problem solved with its consequence). |
| `analogue` | 0.8 | Specific action + a result that is only partly stated (scale without effect, an effect without who/what). |
| `adjacent` | 0.5 | Specific action and scope, no result at all. |
| `implied` | 0.3 | Vague or team-level; the reader can't tell what this person did. |
| `unaddressed` | 0.0 | A duty statement or a list of tools. |

- **Natural measures** [weak]: latency, invoice processing time, sales revenue or response time
  often support a number question. Care decisions, design rationale, confidential negotiations and
  ongoing studies often need an explanation instead. Source: product interpretation of MIT guidance.
- **One question** [weak]: ask for the single missing piece: what changed, who used it, why that
  approach, or a natural measure. Every measure question names its target and has a number-free
  alternative. Source: approved evaluator contract.
- **Evidence validation** [weak]: `analogue` and `direct` need a verbatim quote of at least three words
  from the bullet (case, whitespace, curly quotes, dashes and wrapping quote marks aside), else
  the level drops to `adjacent`. A measure question survives only when its target
  is in the bullet's own words and its alternative asks for no number; otherwise the alternative is
  asked instead. Quotes validate structure, not the truth or quality of a model's judgment.
  Source: evaluator contract, `bullet_classify._validate`.
- **Scoring** [weak]: the score is the plain mean of enabled experience, project and extra-section
  bullet levels. The summary is assessed but is not scored. Attention zones order suggestions;
  gates can cap the score. A finding shows what moving its bullet ONE level up is worth, and the
  report the points to the next grade. Source: `health_score.py`.

## Writing examples

- **Writing shapes** [weak]: these are optional writing aids, not scoring taxonomies. Source:
  product examples consistent with Harvard's action-and-result guidance. STAR is for interview stories.
  XYZ: “Reduced invoice errors by 24% by adding supplier validation.”
  CAR/PAR/APR: “Resolved an ambiguous medication order with the prescriber before administration.”
  Action + Purpose + Outcome: “Added keyboard shortcuts to the booking flow so blind users could reserve independently.”
  What-Who-Win: “Published an archive index for visiting scholars, enabling retrieval of uncatalogued letters.”

## Gates and flags

- **Existing gates** [weak]: `S1` PDF text, `S2` email, `S3` dates, `S4` section headings,
  `S5` placeholders, `C1` strong opening and `C2` years matching dates retain their current
  enforcement. A fresh, failing, unwaived fatal gate blocks tailoring. Source: `health_gates.py`.
- **Existing advisories** [weak]: missing summary, entry bullet count, long or short bullets,
  duplicate or undemonstrated skills, sentence-like skills, punctuation and duplicate certifications
  remain suggestions with no score impact. Source: `resume_lint._advisories` and `_shape_notes`.
- **No numbers** [moderate]: `evidence.no_numbers` is a whole-resume note (location
  `{"section": "resume"}`, no index) that fires when at least `MIN_SCOREABLE_ITEMS` (4) scored bullets
  exist (experience, projects, extras; the summary is not one) and none contains a number. It is a
  highlighted flag with zero score impact and no quota: one number anywhere silences it, and nothing
  counts how many are "enough". Source: CareerBuilder/Harris resume survey cited by the approved design;
  `resume_lint._no_numbers_note`.
  **The detector** (`_has_metric`) strips versions first (a capitalised name followed by a dotted number,
  “Spark 3.5.1”, or a v-number, “v2.1”), ignores years 1900–2099, and counts digits, “two” to “ten”,
  dozens, hundreds, thousands and millions. **Known limits:** a bare “Python 3” (no dot) still counts as
  a number, so the flag stays silent in that rare case; “AUC 0.789” (a capitalised word directly before
  a decimal) reads as a version, so the flag can fire when that is the only number. Both errors affect
  only this zero-score note.
- **Wording is flagged, never scored**: every `language.*` note is a zero-score `note`, and a ladder
  ask on the same bullet never hides it. A word or span on the user's **Never flag** list is skipped.
- **Language slips** [strong]: `language.slip` reports each spelling or grammar correction the evaluator
  already returns in its `language` field (verbatim span and fix, at most three per bullet; no extra
  model call), for the summary and every scored bullet. Source: [recruiter experiment](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0283280).
- **Clichés** [moderate]: `language.cliche` flags words hiring managers rate as meaningless, matched by
  code against an editable bank. Defaults: results-driven, results-oriented, team player, go-getter,
  think outside the box, synergy, best of breed, go-to person, thought leadership, value add,
  detail-oriented, self-motivated, hard worker, strategic thinker, dynamic, proactive, track record,
  self-starter. Source: CareerBuilder/Harris Poll 2014 survey of hiring managers, “worst resume terms”.
- **Filler words** [moderate]: `language.filler` flags words that lengthen a line without informing:
  successfully, effectively, efficiently, various, several, very, really, basically, actually.
  Source: the VMock filler-word list, as published by Boston University career services.
- **Word bank matching** [weak]: whole words or phrases, case-insensitive, one note per location and
  word (`health_wording.matches`). The user edits both lists and the Never flag list, and can reset
  the two lists to the defaults (Never flag is kept). **Known limitation:** matching is context-blind,
  so “dynamic programming” flags “dynamic”; the user adds “dynamic” to Never flag. Source: `health_wording.py`.
- **Remove and Apply** [weak]: a **cliché** never gets one-click Remove: it is a noun or adjective the
  sentence needs, so the note asks for a rewrite in the user's own words (or a cut by hand). A
  **filler** word gets Remove, which cuts every whole-word occurrence and tidies the seam (spaces, a
  newline, empty brackets, a dangling slash or dash, the capital; the comma before a filler always
  stays, an -ly word keeps the comma after it unless both surround it). The rewrite guards check facts,
  not grammar, so Remove is copy-only when the cut is risky or reads broken: after "not", a linking
  verb (is, was, are, were, be, been, being, as), "of" or an a/an article; a non -ly filler before a
  function word or relative pronoun ("several of the"); "the" before a function word or punctuation;
  an and/or left with nothing to join or opening a sentence; empty quotes. Apply swaps a slip's span
  for its fix, only when the span occurs once as a whole word. Either text is offered only when it
  also passes the rewrite guards below, so a fix that adds a number or drops a named tool or company
  is copy-only.

## User control and verification

- **Precedence** [weak]: manual override > current dispute > evaluation. A dispute (**Not right?**)
  re-reads one bullet with the user's note: the note can clarify a reading, but the level never rises
  without a verbatim quote, and a new fact counts only once the user accepts it into the bullet (it
  comes back as a guarded suggestion). “No number exists” stays in force for that text, across later
  disputes and model or rubric changes, until the dispute is reopened. A hand-set rating is not
  disputable: set it back to automatic first. Source: approved dispute contract, `health_disputes.py`.
- **Rewrites** [weak]: never invent numbers, drop protected entities or introduce placeholders.
  All appliable rewrites pass `health_guards`; a rejected suggestion is copy-only or absent.
  Source: `health_guards.py` and the product truthfulness requirement.
- **Repeatability** [weak]: cache by text, rubric version and model, with user overrides preserved;
  a change to what the prompt judges bumps the rubric version. Source: evaluator cache contract.
  Repeatability is not proof of an accurate judgment.
- **Golden set** [weak]: 80 synthetic bullets across eight roles plus 12 adversarial disputes are
  a pilot, not broad validation. Five bullets per role are development examples and five are held
  out. The owner must approve the labels before judging the evaluator. Tune only on development
  examples and freeze the prompt before the held-out run. Source: evaluation plan.
- **Pilot gate** [weak]: across three held-out trials, each role needs 80% within-one-level agreement,
  overall needs 90% within-one and 70% exact; unnatural number asks and overcredited disputes must
  be zero. Persisted no-number facts must suppress measure asks. Source: evaluation plan.
- **Known limits** [weak]: disputes are web-only (no MCP tool); a rating hand-set to `direct`
  leaves the report, so it can't be set back from the report's Done tab; custom-section suggestions
  are copy-only (no bullet edit op for them); a tailored draft gets the word bank but no automatic
  rubric check. Source: SYSTEM.md §11.
