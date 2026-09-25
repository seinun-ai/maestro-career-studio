# Health-check rubric

> Reference tier of [SYSTEM.md](../SYSTEM.md). Its living-document contract applies.
> This rubric defines the evaluator; later-wave disputes and flags are identified below until available.

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
- **Evidence validation** [weak]: high levels require a substantive quote from the bullet. Quotes
  validate structure, not the truth or quality of a model's judgment. Source: evaluator contract.
- **Scoring** [weak]: the score is the plain mean of enabled experience, project and extra-section
  bullet levels. The summary is assessed but is not scored. Attention zones order suggestions;
  gates can cap the score. Source: `health_score.py`.

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
- **No numbers** [moderate, later wave]: `evidence.no_numbers` highlights a resume with no measured
  bullets, with zero penalty and no quota. Source: CareerBuilder/Harris resume survey cited by the
  approved design. The detector is heuristic: bare “Python 3” counts; “AUC 0.789” resembles a version.
- **Language slips** [strong, later wave]: `language.slip` reports clear spelling and grammar
  corrections, with no score impact. Source: [recruiter experiment](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0283280).
- **Word bank** [moderate, later wave]: cliché and filler notes use an editable whole-word bank
  and a Never flag list. Source: the approved design's CareerBuilder/Harris and Boston University
  guidance. Matching is contextuality-blind: “dynamic programming” flags “dynamic” until ignored.

## User control and verification

- **Precedence** [weak, disputes in a later wave]: manual override > current dispute > evaluation.
  A note can clarify a reading; new facts count only after acceptance into the bullet. “No number
  exists” stays in force for that text until the dispute is reopened. Source: approved dispute contract.
- **Rewrites** [weak]: never invent numbers, drop protected entities or introduce placeholders.
  All appliable rewrites pass `health_guards`; a rejected suggestion is copy-only or absent.
  Source: `health_guards.py` and the product truthfulness requirement.
- **Repeatability** [weak]: cache by text, rubric version and model, with user overrides preserved.
  Source: evaluator cache contract. Repeatability is not proof of an accurate judgment.
- **Golden set** [weak]: 80 synthetic bullets across eight roles plus 12 adversarial disputes are
  a pilot, not broad validation. Five bullets per role are development examples and five are held
  out. The owner must approve the labels before judging the evaluator. Tune only on development
  examples and freeze the prompt before the held-out run. Source: evaluation plan.
- **Pilot gate** [weak]: across three held-out trials, each role needs 80% within-one-level agreement,
  overall needs 90% within-one and 70% exact; unnatural number asks and overcredited disputes must
  be zero. Persisted no-number facts must suppress measure asks. Source: evaluation plan.
