// XCharter Serif: pt-exact Typst port.
// Mapping derived from the LaTeX article class, not eyeballed. Two facts drive
// every number below:
//   1. A LaTeX length is in TeX points (1/72.27in); a Typst/PDF point is
//      1/72in. Every class length is therefore multiplied by 0.996264 here,
//      which is why the table reads 9.963pt rather than a round 10pt.
//   2. Type sizes do NOT scale linearly with the class option, so they are
//      looked up per font_size instead of multiplied by a ratio:
//      \small = 9/10/10.95pt, \large = 12/12/14.4pt, \small's baselineskip =
//      11/12/13.6pt for font_size 10/11/12, and \Huge caps at 24.88pt in all
//      three classes.
//   effective margins (measured from the compiled LaTeX PDF):
//   left 28.8pt (0.4in), text width 554.2pt.
#let r = json(bytes(sys.inputs.resume))
#let fmt = json(bytes(sys.inputs.fmt))
#let header_alignment = if fmt.header_align == "left" { left } else if fmt.header_align == "right" { right } else { center }

// small / large / \small baselineskip / level-2 list body offset, in PDF pt.
// `body` is LaTeX's \leftmarginii, measured off the compiled PDF at each class
// size: 21.9 / 24.0 / 25.8pt.
#let T = (
  "10": (small: 8.966pt, large: 11.955pt, bs: 10.959pt, body: 21.92pt),
  "11": (small: 9.963pt, large: 11.955pt, bs: 11.955pt, body: 24.00pt),
  "12": (small: 10.909pt, large: 14.346pt, bs: 13.549pt, body: 25.75pt),
).at(str(fmt.font_size))
#let name_size = 24.787pt
// Bullet geometry. The marker is LaTeX's \tiny bullet, so it scales with the
// body size, and `body_pad` stands in for \labelsep. Both are expressed
// against T.small so the body column lands on `T.body` at every class size.
#let mark_size = 0.5 * T.small
// LaTeX right-aligns the list label in its box, so a wider label grows to the
// LEFT and the body column never moves. Typst places the marker at `indent`
// and the body `body-indent` after it, so the marker's own advance width has
// to come out of the indent: bullet 0.295em, en dash 0.5em.
#let mark_w = if fmt.bullet_icon == "dash" { 0.5 * T.small } else { 0.295 * T.small }
#let body_pad = 0.632 * T.small
#let list_indent(body_offset) = body_offset - mark_w - body_pad
// The skills list is LaTeX's `leftmargin=0.15in` itemize: body column at 10.8pt.
#let skills_offset = 10.8pt

// Vertical calibration, measured against the LaTeX render of example.json at
// each class size. LaTeX carries a different literal \vspace after every
// section, so the port carries a matching pair per section rather than one
// shared constant. `dsize` is 0pt at font_size 11; the slopes on it are the
// measured per-point drift of the LaTeX gaps as \small changes, and they come
// in two families: a section that follows a paragraph loses ~1.1pt per point,
// one that follows a bullet list loses ~2.2pt (the list end scales too).
#let dsize = T.small - 9.963pt
#let PRE_AFTER_PARA(base) = base + 1.1 * dsize
#let PRE_AFTER_LIST(base) = base + 2.2 * dsize
#let POST(base) = base + 1.0 * dsize
#let PRE_DEFAULT = PRE_AFTER_LIST(4pt)
#let POST_DEFAULT = POST(0pt)
#let PRE_SUMMARY = PRE_AFTER_PARA(6.9pt)
#let POST_SUMMARY = POST(0.5pt)
#let PRE_EXPERIENCE = PRE_AFTER_PARA(6.9pt)
#let POST_EXPERIENCE = POST(-0.6pt)
#let PRE_PROJECTS = PRE_AFTER_LIST(3.5pt)
#let POST_PROJECTS = POST(-0.4pt)
#let PRE_SKILLS = PRE_AFTER_LIST(16.4pt)
#let POST_SKILLS = POST(0.5pt)
#let PRE_EDUCATION = PRE_AFTER_LIST(5.9pt)
#let POST_EDUCATION = POST(-0.6pt)
#let HIDDEN_RULE = 7.5pt
#let BULLET_LEAD = 0.6pt
#let ENTRY_GAP = 1.4pt
#let PROJECT_GAP = 2.2pt + 1.0 * dsize

#set page(
  paper: "us-letter",
  margin: (
    x: fmt.side_margins * 1in,
    y: fmt.top_bottom_margin * 1in,
  ),
)
// Body text is \small on \small's baseline grid. The top and bottom edges are
// pinned so the glyph box is exactly 1em, which makes
// baseline-to-baseline = leading + 1em; leading is therefore the LaTeX
// baselineskip (scaled by \linespread) minus the type size.
// `spacing`: LaTeX's ragged-right line breaker may SHRINK interword glue to
// pull a last word onto a line; Typst's does not, so without help the port
// spills an extra line wherever LaTeX squeezed one. XCharter's natural space
// is 2.770pt at font_size 11 and LaTeX shrank it to 2.594pt on the tightest
// line; 91% is the widest setting at which both engines break at the same
// word for font_size 10, 11 AND 12 on the reference resume.
#set text(
  font: ("XCharter", "Libertinus Serif"),
  size: T.small,
  spacing: 91%,
  top-edge: 0.8em,
  bottom-edge: -0.2em,
)
#let leading = T.bs * fmt.line_spacing - T.small
#set par(justify: fmt.justify, leading: leading, spacing: leading)
#set block(spacing: leading)
// `spacing` is load-bearing only because the list is NOT tight: a tight list
// takes par.leading between items, but LaTeX's nested itemize adds \itemsep
// (2pt at this level) on top of the baseline pitch, so the items are spaced
// apart explicitly instead.
#set list(
  marker: if fmt.bullet_icon == "dash" [#sym.dash.en] else [#text(size: mark_size)[•]],
  indent: list_indent(T.body),
  body-indent: body_pad,
  tight: false,
  spacing: leading + 2pt,
)

// Section heading: \large\bfseries\scshape plus \titlerule.
// DEVIATION, deliberate: section_spacing is wired ONLY here, at the pre-title
// gap, so one knob unit moves each section by exactly 1pt on both engines. The
// LaTeX side does the same (the titleformat \vspace); the cross-engine 1pt law
// is the contract, not a shared internal decomposition.
#let section(title, before: PRE_DEFAULT, after: POST_DEFAULT) = {
  v(before + (fmt.section_spacing - 6) * 1pt)
  block(spacing: 0pt, text(size: T.large, weight: "bold", smallcaps(title)))
  if not fmt.hide_divider {
    // LaTeX's \titlerule hugs its heading (measured 1.75pt below the heading
    // box vs ~5pt to the content); split the 3.5pt envelope the same way so
    // the rule reads as underlining the heading, not topping the content.
    v(-0.25pt)
    line(length: 100%, stroke: 0.5pt)
    v(3.25pt)
  } else {
    // Keep the hidden layout's vertical envelope: LaTeX's hide_divider drops
    // the \titlerule but keeps the surrounding \vspace.
    v(HIDDEN_RULE)
  }
  v(after)
}

#let date_range(start, end) = {
  if start != none and end != none [#start -- #end] else if start != none [#start] else if end != none [#end]
}

// LaTeX-\underline-style link: the LaTeX original draws a continuous 0.4pt
// rule BELOW the box (clear of descenders), while typst's default underline
// hugs the baseline and evades descenders, which reads as the rule cutting
// through y/j/g/@ in URLs. offset 0.35em matches the measured LaTeX rule
// position (~3.5pt below baseline at the 10pt contact size).
#let ulink(url, body) = link(url, underline(offset: 0.35em, evade: false, stroke: 0.4pt, body))

// Header: \Huge smallcaps name and \small contact line.
#align(header_alignment)[
  #block(spacing: 0pt, text(size: name_size, smallcaps(r.contact.name)))
  #v(-0.3pt)
  #if r.contact.location != none {
    r.contact.location
    v(1pt)
  }
  #{
    let parts = ()
    if r.contact.phone != none { parts.push([#r.contact.phone]) }
    parts.push(ulink("mailto:" + r.contact.email, r.contact.email))
    if r.contact.linkedin != none { parts.push(ulink("https://" + r.contact.linkedin, r.contact.linkedin)) }
    if r.contact.github != none { parts.push(ulink("https://" + r.contact.github, r.contact.github)) }
    if r.contact.website != none { parts.push(ulink("https://" + r.contact.website, r.contact.website)) }
    parts.join([ | ])
  }
]

// Summary.
#if r.summary != none {
  section("Summary", before: PRE_SUMMARY, after: POST_SUMMARY)
  par(r.summary)
}

// Experience.
#if r.experience.len() > 0 {
  section("Experience", before: PRE_EXPERIENCE, after: POST_EXPERIENCE)
  for (i, job) in r.experience.enumerate() {
    if i > 0 { v(ENTRY_GAP + fmt.entry_spacing * 1pt) }
    grid(
      columns: (1fr, auto),
      align: (left, right),
      row-gutter: leading,
      [*#job.company*], [*#date_range(job.start_date, job.end_date)*],
      emph(job.role), emph(job.location),
    )
    v(BULLET_LEAD)
    for b in job.bullets [
      - #b
    ]
  }
}

// Projects.
#if r.projects.len() > 0 {
  section("Projects", before: PRE_PROJECTS, after: POST_PROJECTS)
  for (i, p) in r.projects.enumerate() {
    if i > 0 { v(PROJECT_GAP + fmt.entry_spacing * 1pt) }
    grid(
      columns: (1fr, auto),
      align: (left, right),
      [*#p.name* #if p.tech != none [ | #emph(p.tech)]],
      [*#p.date*],
    )
    v(BULLET_LEAD)
    for b in p.bullets [
      - #b
    ]
  }
}

// Custom sections (extra_sections). Anchor: after Projects, before
// Technical Skills, matching the documented XCharter layout.
#for sec in r.extra_sections {
  if sec.type == "entries" and sec.entries.len() > 0 {
    section(sec.title)
    for (i, e) in sec.entries.enumerate() {
      if i > 0 { v(ENTRY_GAP + fmt.entry_spacing * 1pt) }
      grid(
        columns: (1fr, auto),
        align: (left, right),
        row-gutter: leading,
        [*#e.heading*], [*#e.date*],
      )
      if e.subheading != none or e.location != none {
        grid(
          columns: (1fr, auto),
          align: (left, right),
          if e.subheading != none { emph(e.subheading) } else { [] },
          if e.location != none { emph(e.location) } else { [] },
        )
      }
      v(BULLET_LEAD)
      if e.link != none [
        - #ulink(e.link, e.link)
      ]
      for b in e.bullets [
        - #b
      ]
    }
  } else if sec.type == "bullets" and sec.bullets.len() > 0 {
    section(sec.title)
    for b in sec.bullets [
      - #b
    ]
  }
}

// Technical Skills and Certifications.
#if r.skills.len() > 0 or r.certifications.len() > 0 {
  section("Technical Skills", before: PRE_SKILLS, after: POST_SKILLS)
  if fmt.skills_layout == "bulleted" {
    [
      // A level-1 itemize: LaTeX adds itemsep+parsep (3pt+3pt) between items,
      // where the nested bullet lists add 2pt+2pt less \resumeItem's -2pt.
      #set list(
        indent: list_indent(skills_offset),
        body-indent: body_pad,
        spacing: leading + 6pt,
      )
      #for g in r.skills [
        - *#g.category*: #g.items.join(", ")
      ]
      #if r.certifications.len() > 0 [
        - *Certifications*: #r.certifications.join(", ")
      ]
    ]
  } else {
    pad(left: skills_offset)[
      #for g in r.skills [
        *#g.category*: #g.items.join(", ") \
      ]
      #if r.certifications.len() > 0 [
        *Certifications*: #r.certifications.join(", ")
      ]
    ]
  }
}

// Education.
#if r.education.len() > 0 {
  section("Education", before: PRE_EDUCATION, after: POST_EDUCATION)
  for (i, edu) in r.education.enumerate() {
    if i > 0 { v(ENTRY_GAP + fmt.entry_spacing * 1pt) }
    let edu_start = if edu.start_date != none { edu.start_date } else { none }
    let dates = if edu_start != none { date_range(edu_start, edu.end_date) } else { edu.graduation_date }
    let inst = if edu.location != none [#edu.institution, #edu.location] else [#edu.institution]
    let first = if fmt.education_order == "institution_first" [*#inst*] else [*#edu.degree*]
    let second = if fmt.education_order == "institution_first" [#emph(edu.degree)] else [#emph(inst)]
    grid(
      columns: (1fr, auto),
      align: (left, right),
      row-gutter: leading,
      first, [*#dates*],
      second, [#if edu.gpa != none [#edu.gpa]],
    )
    v(BULLET_LEAD)
    if edu.coursework.len() > 0 [
      - Coursework: #edu.coursework.join(", ").
    ]
    for b in edu.bullets [
      - #b
    ]
  }
}
