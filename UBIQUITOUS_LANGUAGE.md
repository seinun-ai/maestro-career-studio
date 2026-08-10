# Ubiquitous Language

The vocabulary of Maestro CS. Terms are grouped by subdomain. Where the
codebase and the domain disagree, the **domain** term wins in prose and the code
identifier is noted — see *Recommended renames* for the ones worth changing.

## Career record — the durable layer

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Career KB** | The durable record of everything the user has done, independent of any one resume | knowledge base, master profile, memory, career context |
| **KB Entity** | One thing the user did — a job, project, degree, or certification | item, record, node |
| **KB Point** | A single claim under an entity, in the user's own words | bullet, evidence, achievement |
| **KB Profile** | The singleton holding contact details, skills, and the career summary | profile, master |
| **Port** | Copying approved points from the Career KB into a resume, verbatim or AI-adapted | import, sync, push |
| **Drift** | A ported point whose KB source text has since been edited | stale, out of date |

## Resume artifacts

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Base Resume** | A reusable resume aimed at one role, the starting point for tailoring | base, source resume, master |
| **Tailored Resume** | The per-application copy of a base, rewritten against one job | customized resume, tailored copy |
| **Resume Version** | An immutable snapshot of a resume's content at one point in time | revision, history entry |
| **Resume Data** | The structured content of a resume — contact, experience, projects, education, skills | resume JSON, payload |
| **Extra Section** | A user-defined resume section beyond the fixed core ones | custom section, additional section |
| **Slug** | The stable identifier of a base resume, used in URLs and on disk | id, key, name |
| **Role Category** | The canonical role a resume or job belongs to, drawn from a fixed vocabulary | title family, family, role, category |

## Application pipeline

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Job** | A job posting the user has captured | posting, JD, listing, req |
| **Application** | The user's pursuit of one job, from tailoring through outcome | submission, app |
| **Tailoring Session** | The working draft between a base resume and an application, where edits accumulate before commit | session, draft, workspace |
| **Quick Tailor** | A one-shot tailor whose resolutions are planned from the saved profile instead of reviewed at the checkpoint; a Tailoring Session is still created underneath | fast tailor, instant tailor |
| **Artifact** | A rendered output file belonging to one application — resume PDF, cover letter, Q&A | output, document, deliverable |

## Assessment

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **ATS Score** | The engine's rating of one resume against one job | score, match score, fit score |
| **Composite** | The single headline number an ATS score rolls up to | overall, total, final score |
| **Gap** | A job requirement the resume does not evidence | miss, weakness, hole |
| **Health Report** | The deterministic quality check on a resume, independent of any job | lint report, health check, audit |
| **Evidence Level** | How directly a bullet supports a claim — direct, analogue, or weaker | strength, confidence, tier |
| **Gate** | A pass/fail condition that caps a score or blocks an action regardless of points | check, rule, validation |
| **Placement Target** | The destination on a resume where a gap resolution lands — a skills category, an enabled experience/project entry, or an enabled extra section | destination, target, slot |

## Rendering

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Template** | The visual design a resume renders through, owning its own default formatting | theme, style, layout |
| **Engine** | The typesetting system a template is written for — LaTeX or Typst | renderer, backend, compiler |
| **Formatting** | The per-resume overrides layered on top of a template's defaults | styles, options, settings |
| **Template Preview** | The sample-resume PDF generated when a template is validated | preview |
| **Application Preview** | The rasterized image of a real application's rendered resume | preview |

## Browser extension

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Autofill Profile** | The stored answers the extension fills application forms from | profile, saved data |
| **Autofill Rule** | A pattern that maps a form field to a profile answer | matcher, mapping, selector |
| **Field Observation** | One record of what happened when the extension met one form field | telemetry row, event, log |
| **Outcome** | What became of one field — a success, a failure, or neither | result, status |
| **Neutral Outcome** | An outcome that moves no rate, because declining to fill a field is not a failure | ignored, skipped |
| **Saturation** | The point at which further capture stops revealing new field patterns | coverage, completeness |

## Codebase governance

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Deprecation Ledger** | The register of things built twice, where one copy must still die | tech debt list, TODO list |
| **Removal Trigger** | The observable condition under which an old path may be deleted | criteria, condition, definition of done |
| **Deferred Item** | Work not yet built, as opposed to work built twice | backlog item, TODO |
| **Publish Gate** | The checks that must pass before the open-source tree is published | pre-flight, checklist |

## Relationships

- A **Career KB** holds many **KB Entities**; each entity holds many **KB Points**
- A **KB Profile** is exactly one per Career KB
- A **Port** moves **KB Points** into exactly one **Base Resume**
- A **Base Resume** declares exactly one **Role Category** and renders through exactly one **Template**
- A **Template** targets exactly one **Engine**
- One **Job** may have many **Applications**; each **Application** targets exactly one **Job**
- An **Application** is produced from one **Base Resume**, optionally via a **Tailoring Session**
- Each edit to a resume records one **Resume Version**
- An **ATS Score** rates one resume against one **Job**; a **Health Report** rates a resume alone
- An **ATS Score** yields one **Composite** and zero or more **Gaps**
- A **Deprecation Ledger** row names exactly one **Removal Trigger** — a row without one is a design bug, not a migration

## Example dialogue

> **Dev:** "When someone edits a **KB Point** that was already **ported** into a **Base Resume**, does the resume change?"

> **Domain expert:** "No. The port copies the text — that is the whole point of the KB being a sidecar. What changes is that the port is now **drifted**, and we can show them."

> **Dev:** "So if they want two resumes off the same history — one for data science, one for engineering — that is two **Base Resumes**, not one with two versions?"

> **Domain expert:** "Two **Base Resumes**, each with its own **Role Category**. A **Resume Version** is history, not an alternative. We looked hard at a 'variant' concept and cut it — the two resumes differed by rewriting, not by which bullets were switched on, so there was nothing for a variant to select."

> **Dev:** "And once they pick a **Job**, the tailoring happens in a **Tailoring Session**?"

> **Domain expert:** "Unless they use **Quick Tailor**, which plans the resolutions from their saved profile and lands straight on the **Application** — a **Tailoring Session** still runs underneath, they just never see the checkpoint. Either way the **Application** owns the **Artifacts** — the actual PDFs — and the **ATS Score** rates the tailored resume against that one job. Don't confuse it with the **Health Report**: that one never looks at a job at all."

## Flagged ambiguities

- **"Preview" means two unrelated things.** A *Template Preview* is a sample-resume PDF produced by template validation; an *Application Preview* is a raster of a real application's output. Today's work found the first sitting in a directory everyone assumed held assets. Always qualify which.
- **"Score" is overloaded.** An *ATS Score* needs a job; a *Health Report* score does not. Saying "the score dropped" without qualifying is the single most confusing sentence in this domain. Never use bare "score".
- **"Session" is overloaded three ways** — a *Tailoring Session* (a domain entity), a chat session, and an agent working session. Only the first is domain vocabulary; qualify the others or avoid the word.
- **"Variant" is a rejected term.** It named a feature that was designed and then cut on evidence. Do not reintroduce it: for an alternative resume say *duplicate*, and for history say *Resume Version*.
- **"Master" is dead.** It was a reserved base-resume slug, superseded by the Career KB. It still appears in reserved-slug guards. Never use it for the KB, the profile, or a resume.
- **"Memory" is dead.** It named a settings blob superseded by the Career KB. Say *Career KB*.
- **"Title family" is dead and was actively harmful.** Its title-cased keys never matched the snake_case values production emits, leaving the ATS adjacent-role tier unreachable in production while tests passed. Say *Role Category*.
- **"Explore" vs "Analytics".** The UI says Analytics; the API prefix and seven MCP tool names still say `explore` and are deliberately frozen. Say *Analytics* in prose; treat `explore` as an identifier, not a word.
- **"Lint" vs "health".** `ResumeLintReport` is the class; the domain concept is a *Health Report*. Linting is a programming metaphor that means nothing to someone assessing a resume.
- **"Point" vs "bullet" are genuinely different.** A *KB Point* is a durable claim in the career record; a bullet is rendered text in one resume. A point becomes a bullet by being ported. Using them interchangeably erases the sidecar boundary.
- **"Resume Tailor" vs "Maestro CS".** The product was renamed. The server correctly reports `maestro-career-studio`, but the local MCP client still registers it as `resume-tailor` and the checkout directory is still `~/Projects/resume-tailor`. Neither is repo state; both will read as the product's name to anyone who sees them.

## Recommended renames

Opinionated, ordered by value. The first three are prose-only and free.

1. **"Health Report", never "lint report"** — in docs, UI, and commit messages. Leave `ResumeLintReport` as the class name; a rename there touches the model, a migration, and the MCP surface for no domain gain.
2. **"Role Category", never "family"** — the ATS config still exposes a derived `title_families` mapping, which is fine as an internal index, but the word should not appear in prose or UI.
3. **Qualify every "preview" and every "score"** at first use in any document or comment.
4. **`Port` → `Copy to resume` in user-facing text.** "Port" is opaque outside the codebase; nothing in a resume tool suggests it means "copy these points across". Keep `KBPortLog` and the endpoints — the rename is for labels and help text.
5. **Rename the MCP client registration `resume-tailor` → `maestro-career-studio`**, matching what the server already reports. One line in the local client config; it is the last place the old product name is visible in daily use.
