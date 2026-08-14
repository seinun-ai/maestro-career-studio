// typst-classic: seeded Typst starter (Phase 1).
// Data contract: sys.inputs.resume = ResumeData JSON (post resume_for_render,
// dates already formatted server-side per fmt.date_format), sys.inputs.fmt =
// merged formatting JSON. Honors: font_size, side_margins, top_bottom_margin,
// section_spacing, entry_spacing, line_spacing, bullet_icon, hide_divider,
// header_align, justify, education_order, skills_layout, fmt.date_format
// (applied server-side before serialization).
#let r = json(bytes(sys.inputs.resume))
#let fmt = json(bytes(sys.inputs.fmt))

#set page(
  paper: "us-letter",
  margin: (
    x: fmt.side_margins * 1in,
    y: fmt.top_bottom_margin * 1in,
  ),
)
#set text(
  font: ("XCharter", "Libertinus Serif"),
  size: fmt.font_size * 1pt,
)
#set par(
  justify: fmt.justify,
  leading: 0.55em * fmt.line_spacing,
)
#set list(
  marker: if fmt.bullet_icon == "dash" [#sym.dash.en] else [#sym.bullet],
  indent: 6pt,
)

#let header_alignment = if fmt.header_align == "left" { left } else if fmt.header_align == "right" { right } else { center }

#let section(title) = {
  v(fmt.section_spacing * 1pt)
  text(size: 1.05em, weight: "bold", smallcaps(title))
  if not fmt.hide_divider {
    v(-4pt)
    line(length: 100%, stroke: 0.6pt)
  }
  v(2pt)
}

#let has_date(value) = value != none and value.trim() != ""

#let date_range(start, end, ongoing: false) = {
  if has_date(start) and has_date(end) [#start #sym.dash.en #end] else if has_date(start) and ongoing [#start #sym.dash.en Present] else if has_date(start) [#start] else if has_date(end) [#end]
}

// ---- Header
#align(header_alignment)[
  #text(size: 1.6em, weight: "bold", smallcaps(r.contact.name))\
  #{
    let parts = ()
    if r.contact.location != none { parts.push(r.contact.location) }
    if r.contact.phone != none { parts.push(r.contact.phone) }
    parts.push(link("mailto:" + r.contact.email)[#r.contact.email])
    if r.contact.linkedin != none { parts.push(link("https://" + r.contact.linkedin)[#r.contact.linkedin]) }
    if r.contact.github != none { parts.push(link("https://" + r.contact.github)[#r.contact.github]) }
    if r.contact.website != none { parts.push(link("https://" + r.contact.website)[#r.contact.website]) }
    text(size: 0.9em, parts.join([ #sym.dot.c ]))
  }
]

// ---- Summary
#if r.summary != none [
  #section("Summary")
  #r.summary
]

// ---- Experience
#if r.experience.len() > 0 {
  section("Experience")
  for (i, job) in r.experience.enumerate() {
    if i > 0 { v(fmt.entry_spacing * 1pt) }
    grid(
      columns: (1fr, auto),
      [*#job.company* #if job.location != none [#sym.dash.en #job.location]],
      [*#date_range(job.start_date, job.end_date, ongoing: true)*],
    )
    emph(job.role)
    for b in job.bullets [
      - #b
    ]
  }
}

// ---- Projects
#if r.projects.len() > 0 {
  section("Projects")
  for (i, p) in r.projects.enumerate() {
    if i > 0 { v(fmt.entry_spacing * 1pt) }
    grid(
      columns: (1fr, auto),
      [*#p.name* #if p.tech != none [| #emph(p.tech)]],
      [#if p.date != none [*#p.date*]],
    )
    for b in p.bullets [
      - #b
    ]
  }
}

// ---- Custom sections (extra_sections). Documented anchor: after Projects,
// before Technical Skills. resume_for_render already dropped disabled
// sections/entries; empty sections render nothing.
#for sec in r.extra_sections {
  if sec.type == "entries" and sec.entries.len() > 0 {
    section(sec.title)
    for (i, e) in sec.entries.enumerate() {
      if i > 0 { v(fmt.entry_spacing * 1pt) }
      grid(
        columns: (1fr, auto),
        [*#e.heading* #if e.subheading != none [#sym.dash.en #e.subheading]],
        [#if e.date != none [*#e.date*]],
      )
      if e.location != none { emph(e.location) }
      if e.link != none [
        - #link(e.link)[#underline(e.link)]
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

// ---- Technical Skills (+ Certifications, matching the Classic layout)
#if r.skills.len() > 0 or r.certifications.len() > 0 {
  section("Technical Skills")
  if fmt.skills_layout == "bulleted" {
    for g in r.skills [
      - *#g.category*: #g.items.join(", ")
    ]
    if r.certifications.len() > 0 [
      - *Certifications*: #r.certifications.join(", ")
    ]
  } else {
    for g in r.skills [
      *#g.category*: #g.items.join(", ")\
    ]
    if r.certifications.len() > 0 [
      *Certifications*: #r.certifications.join(", ")
    ]
  }
}

// ---- Education
#if r.education.len() > 0 {
  section("Education")
  for (i, edu) in r.education.enumerate() {
    if i > 0 { v(fmt.entry_spacing * 1pt) }
    let inst = if edu.location != none [#edu.institution, #edu.location] else [#edu.institution]
    let edu_start = if edu.start_date != none { edu.start_date } else { edu.graduation_date }
    // Non-degree study (degree == none) has no title to lead with, so it always
    // renders institution-first: the degree-first branch would otherwise open
    // the entry with an empty line carrying the dates.
    let inst_first = fmt.education_order == "institution_first" or edu.degree == none
    let first = if inst_first [*#inst*] else [*#edu.degree*]
    let second = if inst_first {
      if edu.degree != none [#emph(edu.degree)]
    } else [#emph(inst)]
    grid(
      columns: (1fr, auto),
      first,
      [*#date_range(edu_start, edu.end_date)*],
    )
    if second != none or edu.gpa != none {
      grid(
        columns: (1fr, auto),
        if second != none { second } else [],
        [#if edu.gpa != none [#edu.gpa]],
      )
    }
    if edu.coursework.len() > 0 [
      - Coursework: #edu.coursework.join(", ").
    ]
    for b in edu.bullets [
      - #b
    ]
  }
}
