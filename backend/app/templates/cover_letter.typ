// cover_letter.typ: the bundled cover letter for the Typst engine — the
// counterpart of cover_letter.tex.j2 + _header.tex.j2, self-contained because a
// Typst compile is root-scoped to one staged file (typst_compiler) and cannot
// include a bundled partial. Header layout and spacing mirror the LaTeX one.
//
// Data contract (every sys.input is a string): contact = ResumeData.contact
// JSON with blank strings already coerced to null; paragraphs = JSON array of
// strings; today = an already-formatted date; fmt = merged formatting JSON
// (honors font_size and header_align, like the LaTeX header partial).
#let contact = json(bytes(sys.inputs.contact))
#let paragraphs = json(bytes(sys.inputs.paragraphs))
#let today = sys.inputs.today
#let fmt = json(bytes(sys.inputs.fmt))

#set page(paper: "us-letter", margin: (x: 0.9in, y: 0.8in))
#set text(font: ("XCharter", "Libertinus Serif"), size: fmt.font_size * 1pt)
#set par(justify: false, leading: 0.6em)

#let header_alignment = if fmt.header_align == "left" { left } else if fmt.header_align == "right" { right } else { center }
#let field(key) = contact.at(key, default: none)

#align(header_alignment)[
  #text(size: 1.7em, weight: "bold", smallcaps(contact.name))
  #if field("location") != none [\ #field("location")]
  #{
    let parts = ()
    if field("phone") != none { parts.push(field("phone")) }
    if field("email") != none { parts.push(link("mailto:" + field("email"))[#underline(field("email"))]) }
    if field("linkedin") != none { parts.push(link("https://" + field("linkedin"))[#underline(field("linkedin"))]) }
    if field("github") != none { parts.push(link("https://" + field("github"))[#underline(field("github"))]) }
    if parts.len() > 0 [\ #text(size: 0.9em, parts.join([ #sym.dot.c ]))]
  }
]

#v(12pt)
#today

#v(6pt)
#for p in paragraphs [
  #p
  #v(6pt)
]
