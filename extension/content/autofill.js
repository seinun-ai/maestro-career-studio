/* Maestro CS Companion — profile autofill engine.
 *
 * Shared content-script module. The profile filler remains byte-for-byte close
 * to the proven engine while publishing its entry point explicitly.
 */

// ============================================================
// WHAT THIS FILE PUBLISHES
// ============================================================
(() => {
  const ns = (window.careerStudioCompanion ??= {});


/** Runs IN THE PAGE (all frames). Best-effort fill of form fields from the
 * autofill profile. Handles text inputs, native selects, radios, and
 * ARIA/react-select/select2-style comboboxes (types the value, waits for the
 * option list, clicks the best match). Identity rules (name/email/phone)
 * additionally overwrite non-empty values that disagree with the profile —
 * ATS resume-parse prefills are guesses, the profile is truth. Returns
 * {filled: [{label, value, note?}], eeoFilled: [{field, label, value}],
 * corrected: [{label, was, value}], already: [{label, value}], seen: N}.
 *
 * `already` is the fields that turned out to need nothing: the control holds
 * the value this fill would have written — a re-run on a wizard step, or an
 * ATS prefill that agrees with the profile. Reported so the strip can say
 * "already filled" instead of "0 filled" over a form that is visibly full.
 *
 * `employment` and `skills` come from the RESUME (GET /api/autofill/
 * employment-blocks and /skills), not from the profile: they are the answers
 * that change per application. */
async function fillFormFromProfile(
  profile, employment, eeoEnabled = false, skills = [], consentForms = false
) {
  const p = profile.personal ?? {};
  // Work authorization: the same dual-read the backend's `get_work_auth`
  // performs (services/autofill_profile.py). The extension reads the profile
  // JSON directly, so the two are consistent by BEHAVIOUR, not by shared code.
  //
  // A profile is "new shape" if it carries ANY typed key. Detecting on one or
  // two chosen keys would send a profile holding only `sponsorship_now` down
  // the legacy branch, which reads neither typed key — discarding a knockout
  // answer the user did supply. `work_auth` is hand-editable and may be a
  // string or a list, hence the object check before `in`.
  const rawW = (profile.work_auth && typeof profile.work_auth === "object")
    ? profile.work_auth
    : {};
  const w = ["status", "authorized_now", "sponsorship_now", "sponsorship_future",
    "authorization_expires_on", "countries_authorized"].some((k) => k in rawW)
    ? rawW
    : {
      authorized_now: rawW.authorized_to_work,
      // The legacy flag was never time-scoped. Map it to the FUTURE half —
      // the question employers actually gate on — and leave `sponsorship_now`
      // absent rather than inventing it: an OPT holder needs no sponsorship
      // now and does need it later, which is why the field split at all.
      sponsorship_future: rawW.requires_sponsorship,
    };
  // Education is a list (most recent first); legacy profiles stored one object.
  const eds = Array.isArray(profile.education)
    ? profile.education
    : profile.education && typeof profile.education === "object"
      ? [profile.education]
      : [];
  const pref = profile.preferences ?? {};
  // Standing eligibility answers: the questions nearly every US application
  // asks and that nothing else in the profile can derive. Structured rather
  // than left to the custom Q&A presets, because a preset matches by substring
  // on the label and every employer words these differently — "have you
  // previously been employed by X", "have you worked with us before" and "do
  // you currently work for X" are ONE question that would need one preset each.
  const el = profile.eligibility ?? {};
  const custom = Array.isArray(profile.custom) ? profile.custom : [];
  const emp = Array.isArray(employment) ? employment : [];
  // The resume's skills, flat and already de-duplicated by
  // routers/autofill._resume_skills. Kept in resume order, which is what the
  // cap below selects on.
  const skillList = (Array.isArray(skills) ? skills : [])
    .map((skill) => String(skill ?? "").trim())
    .filter(Boolean);
  // How many skills we are willing to type into one form. A master resume
  // carries 75 and no application wants all of them; each one costs a write,
  // a commit and a readback. Whatever is left over is REPORTED, never dropped
  // silently — see the token branch in the fill loop.
  const SKILL_TOKEN_MAX = 10;

  const norm = (s) => (s ?? "").toLowerCase().replace(/\s+/g, " ").trim();
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const eeoContext = ns.createEeoContext(profile, norm);
  const {
    rules: EEO_RULES,
    isEeoLabel,
    optionWordsFor: eeoOptionWordsFor,
  } = eeoContext;

  // Option-keyword sets per canonical answer, used for selects/radios.
  const OPTION_WORDS = {
    yes: [/^yes\b/i, /\bi am authorized\b/i, /\bi do\b/i],
    no: [/^no\b/i, /\bi am not\b/i, /\bi do not\b/i, /\bwill not\b/i],
    decline: [/decline/i, /don'?t wish/i, /prefer not/i, /not to (self.)?identify/i, /no answer/i],
  };

  // The typed profile stores yes/no answers as booleans; the Settings selects
  // still write them as "yes"/"no" strings. Canonicalize to the OPTION_WORDS
  // keys once, at the source, so every writer downstream — select, radio,
  // combobox, plain text, and the report shown to the user — sees one
  // representation. Without this a `false` stringifies to "false", which
  // matches no option AND is falsy, so the rule would additionally be tagged
  // missing_source: a real "no" reported as a question nobody answered.
  const yesNo = (v) => (v === true ? "yes" : v === false ? "no" : v);

  // Degree lists rarely match the profile text verbatim ("Master of Science"
  // vs "Master's Degree") — match on the level keyword instead.
  const DEGREE_LEVELS = [
    /ph\.?\s?d|doctor/i,
    /master|\bm\.?s\.?c?\b|mba|m\.?eng/i,
    /bachelor|\bb\.?s\.?c?\b|\bb\.?a\.?\b|b\.?eng/i,
    /associate/i,
    /high school|ged|diploma/i,
  ];

  const MONTHS = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];
  // A date, split into its parts. Every shape the two sources actually hold has
  // to parse, and the widest of them is the one that matters: the employment
  // payload passes `resume_json.experience[*].start_date` through verbatim
  // (routers/autofill._employment_blocks) and the resume data model is
  // "Mon YYYY" — see services/ats/resume_indexer.parse_month_year. This used to
  // accept only a leading ISO year, so every real employment date parsed to
  // NOTHING; that is what made `emp-start-month` look valueless, sent matchRule
  // scanning past it, and wrote the whole string into Workday's two-digit month
  // spinner. ISO and slash forms still parse: the profile's education years and
  // a hand-edited settings/autofill.json are free text.
  //
  // `month` and `day` come back as ISO two-digit NUMBERS, never as a name. It is
  // the one form every consumer can convert FROM — a numeric widget takes it
  // as-is and an option list is matched against all four renderings — whereas a
  // name has to be un-parsed before a numeric control can use it. "" means the
  // date does not carry that part; it is never a guess.
  const dateParts = (s) => {
    const text = String(s ?? "").trim();
    const none = { year: "", month: "", day: "" };
    // Bound-checked, so "2018-2021" in a year box yields the year and NOT month
    // 20 — a two-digit capture that happens to be numeric is not a month.
    const twoDigit = (raw, max) => {
      const n = Number.parseInt(raw ?? "", 10);
      return Number.isInteger(n) && n >= 1 && n <= max
        ? String(n).padStart(2, "0") : "";
    };
    // 2021, 2021-06, 2021/06, 2021-06-01. Unanchored at the end, as before, so
    // a longer timestamp still yields its date.
    const iso = /^(\d{4})(?:[-/](\d{1,2})(?:[-/](\d{1,2}))?)?/.exec(text);
    if (iso) {
      const month = twoDigit(iso[2], 12);
      return { year: iso[1], month, day: month ? twoDigit(iso[3], 31) : "" };
    }
    // 06/2021, 6-2021.
    const numeric = /^(\d{1,2})[-/](\d{4})$/.exec(text);
    if (numeric) return { year: numeric[2], month: twoDigit(numeric[1], 12), day: "" };
    // March 2021, Mar 2021, Sept. 2021. Matched on the first three letters,
    // which are unique across all twelve months.
    const named = /^([a-z]{3,9})\.?\s+(\d{4})$/i.exec(text);
    if (named) {
      const stem = named[1].slice(0, 3).toLowerCase();
      const idx = MONTHS.findIndex((m) => m.slice(0, 3).toLowerCase() === stem);
      if (idx >= 0) return { year: named[2], month: twoDigit(idx + 1, 12), day: "" };
    }
    return none;
  };
  // A current job has no end date. A free-text "End Date" box takes the word
  // "Present"; a date PART cannot hold it, so a part control gets "" — which
  // skips the field while still consuming the DOM-order slot.
  const empEndText = (x) => (x.current ? "Present" : (x.end_date ?? ""));
  const empEndDate = (x) => (x.current ? "" : (x.end_date ?? ""));

  // Which PART of a date a split widget wants. Both forms have to be matched
  // because neither covers the other. The vendor's sub-control identifier —
  // "…datesectionmonth-input" (Workday), "…rcf3214_month" (Oracle),
  // "icims_0_startdate_month" (iCIMS) — carries no word boundary before the
  // part, since "n" and "_" are word characters, so `\bmonth\b` matches none of
  // them. The plain word is meanwhile the ONLY signal on Oracle's day select,
  // whose id says "_date". labelFor() folds `name` and `id` into the label, so
  // both live in the same string.
  //
  // Uniform on purpose. Only `datesectionday` is reachable through today's
  // consumers — the two in-order rules below are guarded off every label
  // naming a start or an end, and every live "datesectionyear"/"…month" label
  // names one. Pruning the other two would make the three parts mean different
  // things, which is a trap for the next rule that matches on PART_RE.
  const PART_RE = {
    year: /datesectionyear|[_\-.]year\b|\byear\b/i,
    month: /datesectionmonth|[_\-.]month\b|\bmonth\b/i,
    day: /datesectionday|[_\-.]day\b|\bday\b/i,
  };
  // Any of the three, for the rules that hold a WHOLE date: those must decline a
  // control that asked for one part of one. Without this, matchRule scanning
  // past an unfillable `emp-start-month` handed the month spinner to
  // `emp-start-date`, which is the live not_stuck on every Workday date widget.
  const ANY_DATE_PART_RE =
    /datesection(year|month|day)|[_\-.](year|month|day)\b|\b(year|month|day)\b/i;
  // An employment block, named however the vendor names it: Oracle only in the
  // container text ("professional experience (1)* required."), iCIMS only in the
  // control id ("icims_0_startdate_date"), Workday in both.
  const EMP_SECTION_RE =
    /professional\s*experience|work\s*(experience|history)|employment|start\s*date|end\s*date/i;
  // The same idea WITHOUT the date words, for the rules that are not about
  // dates. An education block renders "Start Date" and "End Date" too, so
  // those two alternatives above only earn their place where the rule is
  // already narrowed to a date part; anywhere else they make the section test
  // mean "…or any field near a date", which is most of a form.
  const EMP_BLOCK_NAME_RE =
    /professional\s*experience|work\s*(experience|history)|employment|employer/i;
  // labelFor() includes the fieldset legend, so a generic "Start Month" select
  // inside an EDUCATION block must not consume an employment date slot — it
  // would corrupt the field AND shift every later entry by one.
  const NOT_EDUCATION = /educat|school|attend|enroll/i;
  // …and additionally off any label that names its own end of the range, for
  // the DOM-order fallback that has no other way to tell From from To.
  const NOT_EDUCATION_OR_SIDED = /educat|school|attend|enroll|start|end/i;
  // A rule holding a YEAR must decline a control asking for a smaller part. The
  // education rules match "start date"/"end date" as well as "…year", and
  // "education-193--startdate-datesectionmonth-input" satisfies the first while
  // asking for the second — so without this the education START YEAR lands in a
  // month box. Same for a "Graduation Month" against the `graduat` alternative.
  const NOT_MONTH_OR_DAY_PART =
    /datesection(month|day)|[_\-.](month|day)\b|\b(month|day)\b/i;
  // An open question that happens to mention the same noun as a rule is not
  // that rule's field. "What skills would you like to develop?" is an essay
  // box, and ten chips typed into it would be an answer nobody wrote. Scoped to
  // the FIRST segment for the same reason as the employer and location rules:
  // labelFor() appends the legend and container text last, so an interrogative
  // after the first "|" belongs to the section, not to this control.
  const OPEN_QUESTION =
    /^[^|]*(\?|\b(what|which|why|how|describe|tell)\b)/i;
  // "Is this job the one you are still in?" — Workday's own two spellings, the
  // visible label and the control id, and NOTHING looser. `/currently work/`
  // additionally matches the live "do you currently work for pwc
  // (pricewaterhousecoopers)?", which asks about the FIRM and which no resume
  // field answers; it would have been ticked for anyone whose most recent job
  // is still in progress. Verified against all 247 live signatures: this
  // matches the three currently-work-here boxes and nothing else.
  const CURRENT_JOB_RE = /\bi currently work here\b|\bcurrentlyworkhere\b/i;

  const optionWordsFor = (kind, value) => {
    if (kind === "degree") {
      const level = DEGREE_LEVELS.find((re) => re.test(String(value)));
      if (level) return [level];
    }
    if (kind === "month") {
      // `value` is the ISO month number ("06"). Match the four renderings a
      // real option list uses — "June", "Jun", "6", "06" — which is the whole
      // point: Oracle's list is Jan…Dec and iCIMS's is 01…12, so no single
      // house format is right on both.
      const idx = Number.parseInt(value, 10) - 1;
      if (idx >= 0 && idx < MONTHS.length) {
        return [new RegExp(`^${MONTHS[idx].slice(0, 3)}`, "i"), new RegExp(`^0?${idx + 1}$`)];
      }
    }
    const eeoWords = eeoOptionWordsFor(kind, value);
    if (eeoWords) return eeoWords;
    return OPTION_WORDS[value] ?? [new RegExp(value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i")];
  };

  const fullName = [p.first_name, p.last_name].filter(Boolean).join(" ");
  // Present-tense sponsorship, and ONLY present-tense. "now or in the future"
  // is the standard US knockout: it reads like a "now" question and is answered
  // by the FUTURE flag, because any future need means yes — hence the lookahead
  // that stops a bare "now" from claiming it. The gap is [^|] because labelFor
  // joins up to eight label sources with "|", and the time qualifier has to
  // come from the SAME source as "sponsor" to qualify it (same reasoning as the
  // shared policy patterns).
  const NOW_WORDS = "currently|presently|at this time|\\bnow\\b(?!\\s+or\\b)";
  const SPONSORSHIP_NOW_RE = new RegExp(
    `(${NOW_WORDS})[^|]*sponsor|sponsor[^|]*(${NOW_WORDS})`, "i");
  // Ordered: first matching rule wins for a given field.
  const RULES = [
    { id: "first-name", re: /first\s*name|given\s*name/i, value: p.first_name, identity: true },
    { id: "last-name", re: /last\s*name|family\s*name|surname/i, value: p.last_name, identity: true },
    { id: "full-name", re: /full\s*name|your\s*name|^name\b|legal name/i, value: fullName },
    { id: "email", re: /e-?mail/i, value: p.email, identity: true },
    // Guards BEFORE the broad /phone/ rule: extension/fax must never get the
    // phone number, and "phone country code" selects want the country.
    { id: "phone-ext-fax", re: /extension|\bext\.?\b|fax/i, skip: true },
    { id: "phone-country-code", re: /phone.*(country|code)|country.*code|dial.*code/i, value: p.country },
    // `formatTolerant`: the already-holds check may ignore punctuation for
    // this field. Phone formatting is presentation — "(555) 123-4567" IS
    // "5551234567" — where a name's apostrophe or an email's dot is the datum
    // itself, so no other identity rule gets this flag.
    { id: "phone", re: /phone|mobile|cell/i, value: p.phone, identity: true,
      formatTolerant: true },
    // Line 2 BEFORE the broad address rule: /^address\b/ also matches
    // "Address 2" (word boundary sits before the "2"), which duplicated
    // line 1 into both fields. No address_2 in the profile → skip the
    // field entirely (extension/fax guard pattern), never duplicate.
    // \bapt\b / \bsuite\b, not apt\b / suite: "adapt"/"suited" must not match.
    // \bunit\b alone matched "Business Unit" org fields — require an
    // address-style qualifier (unit no./number/#) for the bare word.
    { id: "address-2",
      re: /(address|street).*(line\s*)?\b2\b|line\s*2|\bapt\b|apartment|\bsuite\b|\bste\b|\bunit\s*(no\.?|number|#)/i,
      ...(p.address_2 ? { value: p.address_2 } : { skip: true }) },
    { id: "address", re: /address\s*line|street|^address\b/i, value: p.address },
    { id: "city", re: /\bcity\b|locality/i, value: p.city },
    { id: "state", re: /\bstate\b|province|region/i, value: p.state },
    { id: "postal-code", re: /zip|postal/i, value: p.postal_code },
    { id: "country", re: /country/i, value: p.country },
    { id: "linkedin", re: /linked\s*in/i, value: p.linkedin },
    { id: "github", re: /git\s*hub/i, value: p.github },
    { id: "website", re: /website|portfolio|personal\s*site|blog/i, value: p.website },
    // Education: a list, most recent first. A repeated form block takes the
    // entry matching its position among the visible blocks of its family — see
    // `blockKeyOf` at the fill loop. On a page that names no blocks the fields
    // fall back to DOM order instead, one entry each. (We can't click "Add
    // another" for you; add the blocks first, then fill.)
    { id: "edu-school", re: /school|university|college|institution/i, values: eds.map((x) => x.school) },
    { id: "edu-degree", re: /\bdegree\b/i, values: eds.map((x) => x.degree), kind: "degree" },
    { id: "edu-discipline", re: /discipline|major|field of study|area of study|concentration/i, values: eds.map((x) => x.discipline) },
    { id: "edu-gpa", re: /\bgpa\b|grade point|overall result/i, values: eds.map((x) => x.gpa) },
    // `part` narrows a WHOLE date to the piece the control asked for, at write
    // time — see datePartValue. The rules hold whole dates so the narrowing has
    // one home and the native-control override has something to work from, but
    // each part keeps its OWN rule, and therefore its own list counter: a block
    // that renders a month box beside a year box has to consume ONE entry, not
    // two.
    //
    // Workday labels its education years "firstyearattended"/"lastyearattended"
    // — the top-ten failure this task was called on. There is no month or day
    // rule here because the profile's education fields are `start_year` and
    // `end_year`; a rule that can never answer is not worth the false precision.
    { id: "edu-end-year", re: /graduat|last\s*year\s*attend|education.*end\s*(year|date)/i,
      not: NOT_MONTH_OR_DAY_PART, values: eds.map((x) => x.end_year), part: "year" },
    { id: "edu-start-year", re: /first\s*year\s*attend|education.*start\s*(year|date)/i,
      not: NOT_MONTH_OR_DAY_PART, values: eds.map((x) => x.start_year), part: "year" },
    // Employment (design Part 2d): repeated blocks resolve through the block,
    // exactly like education above. Add blocks on the page first, then fill.
    // Descriptions arrive server-normalized as plain text.
    // `^[^|]*\bcompany\b` — the word in the label's FIRST segment, which is the
    // field's own label. Siemens labels the box "Company" and nothing else, so
    // the most important field of an employment block reported `no_rule` on the
    // highest-volume host in the corpus; Workday's "companyname" id already
    // matched through `company\s*name`. A bare /\bcompany\b/ cannot be used:
    // labelFor() appends the legend and container text LAST, so every leak
    // lands after the first `|` — live, "…have you worked with us before,
    // including any company acquired by…" would have taken an employer name.
    // The `not:` handles the compounds that DO name themselves first.
    { id: "emp-employer",
      re: /employer(\s*name)?\b|company\s*name|^[^|]*\bcompany\b/i,
      not: /parent\s*company|company\s*(website|url|size|information|details)/i,
      values: emp.map((x) => x.employer) },
    { id: "emp-title", re: /job\s*title|position\s*title|role\s*title|title.*(position|role)/i, values: emp.map((x) => x.title) },
    // A conjunction because neither half is safe alone: "location" is also the
    // applicant's own city ("location (city)* | candidate-location"), a
    // preference ("preferred location") and a relocation question, while the
    // section name is on every field of the block. First segment for the same
    // reason as the employer rule above. Siemens's employment and education
    // blocks BOTH render a bare "Location" and neither label names its section,
    // so this declines both rather than guess — the block tells us which block,
    // never which KIND of block.
    { id: "emp-location", all: [EMP_BLOCK_NAME_RE, /^[^|]*\blocation\b/],
      not: NOT_EDUCATION, values: emp.map((x) => x.location) },
    { id: "emp-start-month", re: /start.*month|month.*start/i, not: NOT_EDUCATION,
      values: emp.map((x) => x.start_date), part: "month", kind: "month" },
    { id: "emp-start-year", re: /start.*year|year.*start/i, not: NOT_EDUCATION,
      values: emp.map((x) => x.start_date), part: "year" },
    { id: "emp-end-month", re: /end.*month|month.*end/i, not: NOT_EDUCATION,
      values: emp.map(empEndDate), part: "month", kind: "month" },
    { id: "emp-end-year", re: /end.*year|year.*end/i, not: NOT_EDUCATION,
      values: emp.map(empEndDate), part: "year" },
    // A day is unanswerable from either source — the resume model is "Mon YYYY"
    // and the profile's education fields are years — so this rule exists to SAY
    // so: narrowing yields "" and the field reports missing_source, naming the
    // control and the gap instead of leaving it an anonymous no_rule. It is a
    // real valued rule rather than a bare `missingSource` one precisely so it
    // WINS the field: matchRule scans past a valueless rule, and `start\s*date`
    // in `earliest-start-date` matches iCIMS's "icims_0_startdate_date", which
    // would drop the user's availability date into a past job's day select.
    //
    // One rule, not a start/end pair: today every value is "" either way, and
    // the interleaved list already matches the only layout the corpus shows
    // (a From widget rendered before its To widget) should a day ever arrive.
    { id: "emp-day", all: [EMP_SECTION_RE, PART_RE.day], not: NOT_EDUCATION,
      values: emp.flatMap((x) => [x.start_date, empEndDate(x)]),
      perEntry: 2, part: "day" },
    // Oracle Recruiting Cloud names its experience date parts with a generated
    // counter — "…rcf3214_year" is the From year and "…rcf3215_year" the To year
    // — and puts the only human text in a container naming the BLOCK
    // ("professional experience (1)* required."), not the field. No amount of
    // label parsing separates the two, so DOM order is the only signal there is:
    // within a block, every ATS renders From before To. Hence the interleaved
    // start,end,start,end list handed out in DOM order.
    //
    // Last resort by construction: `not:` excludes every label that DOES name a
    // start or an end, so a page carrying that signal never reaches this.
    //
    // `perEntry: 2` is what makes that safe. The list still reads From before
    // To, but each BLOCK indexes from its own base, so the assumption shrinks
    // from "no From box on the page is ever rendered without its To" — which
    // nothing could test — to "not within one block". A block that breaks it
    // still fills wrongly; it can no longer shift every block after it.
    { id: "emp-year-in-order", all: [EMP_SECTION_RE, PART_RE.year], not: NOT_EDUCATION_OR_SIDED,
      values: emp.flatMap((x) => [x.start_date, empEndDate(x)]),
      perEntry: 2, part: "year" },
    { id: "emp-month-in-order", all: [EMP_SECTION_RE, PART_RE.month], not: NOT_EDUCATION_OR_SIDED,
      values: emp.flatMap((x) => [x.start_date, empEndDate(x)]),
      perEntry: 2, part: "month", kind: "month" },
    // `not:` on the whole-date rules: "March 2021" in a two-digit month spinner
    // is the live not_stuck on every Workday date widget. It reached them
    // because matchRule scans past a rule it cannot fill, so an unparseable
    // month handed the spinner to whichever broader rule came next.
    { id: "emp-start-date", re: /(work|employment|job|position).*start\s*date|start\s*date.*(work|employment|position)/i,
      not: ANY_DATE_PART_RE, values: emp.map((x) => x.start_date), part: "full" },
    { id: "emp-end-date", re: /(work|employment|job|position).*end\s*date|end\s*date.*(work|employment|position)/i,
      not: ANY_DATE_PART_RE, values: emp.map(empEndText), part: "full" },
    // The same fact as `emp-end-date`, asked as a tick box. HR-1: a DERIVED
    // answer is registered — its own rule, its own id in telemetry, its own
    // authorization flag — rather than inferred at the write site, so the
    // derivation is auditable and no other rule inherits permission to tick a
    // box by growing a value.
    //
    // Provenance, end to end: the resume's `end_date` really does hold the
    // literal string "Present"; `routers/autofill._employment_blocks` reads
    // that (and an absent end date) as `current: true` with `end_date` blanked
    // to null; this reads that flag rather than re-deriving it, which is what
    // `empEndText`/`empEndDate` above already do. WHICH job is the block's
    // answer, not this rule's.
    //
    // "no" is a real answer, not an absent one: it says this job is not the
    // current one, and it is what makes a past job's box report
    // `skipped_checkbox` (recognised and deliberately untouched) instead of
    // vanishing from telemetry through the consumed-empty-slot path.
    { id: "emp-current", re: CURRENT_JOB_RE, tickWhenYes: true,
      values: emp.map((x) => (x.current ? "yes" : "no")) },
    { id: "emp-description", re: /duties|responsibilit|(role|work|job|position).*description|description.*(duties|role|work|position)/i, values: emp.map((x) => x.description) },
    // Skills. `tokens` is a LIST for ONE control — the third answer shape in
    // this table, after a scalar `value` and a per-block `values`. It exists
    // because the control does: `type to add skills | search | skills--skills`
    // is one box on both Workday hosts that holds as many skills as you type
    // into it, one Enter at a time.
    //
    // First segment only (`^[^|]*`), like the employer and location rules:
    // labelFor() appends the legend and container text LAST, so Siemens's
    // "42340-search__field | skills" names its SECTION rather than itself, and
    // matching it would put the resume's skills into the widget's search box.
    { id: "skills", re: /^[^|]*\bskills?\b/i, not: OPEN_QUESTION, tokens: skillList },
    // The two-part, time-scoped question a US application actually asks. An OPT
    // holder answers YES to "authorized now" and YES to "now or in the future",
    // and NO to "currently" — one timeless flag could not say that, and a wrong
    // answer here fails the application silently.
    //
    // `not:` on the broad rule, NOT merely putting the narrow one first:
    // matchRule keeps SCANNING past a rule with no answer behind it, so with
    // ordering alone an unknown `sponsorship_now` falls through to the future
    // answer instead of reporting missing_source. The guard makes the two
    // predicates disjoint, which is what actually decides the field; the narrow
    // rule is first by the table's specific-before-broad convention.
    // ---- standing eligibility answers (profile.eligibility) ----
    //
    // Each is a knockout question on a real application, and each is UNSET by
    // default: an absent answer reports missing_source and the field is left
    // blank, which is the whole point of storing them rather than guessing.
    //
    // "Are you 18 years of age or older?" — the wording is remarkably stable,
    // but the number has to be bounded on both sides. `\b18\b` alone matches
    // "18 months of experience" and a 2018 date fragment; requiring the age
    // noun beside it is what keeps this off every other field with an 18 in it.
    { id: "over-18",
      re: /\b(?:are|am)\s+you\b[^?|]{0,40}\b18\b|\b18\s*(?:\+|years?|yrs?)\b[^?|]{0,20}\b(?:of\s*age|old(?:er)?)\b|\bat\s*least\s*18\b|\blegal\s*working\s*age\b/i,
      value: yesNo(el.over_18), kind: "yesno" },
    // "Have you previously been employed by <this employer>?" — the single most
    // common unanswered question in the corpus, seen on six hosts and worded
    // differently on every one: "have you worked with us before", "are you
    // currently or have you previously been employed by Doosan", "do you
    // currently work for PwC", plus Workday's own `candidateIsPreviousWorker`.
    //
    // A conjunction, not an alternation, and that is what makes it safe. It
    // needs the employment word, a time marker AND a question addressed to the
    // applicant — so "I currently work here" (the work-history tick box, which
    // has its own rule and its own derived answer) is missing the third and
    // cannot be captured. Getting that wrong would tick a box about a past job
    // using an answer about this employer.
    { id: "previously-employed-here",
      all: [/\b(?:employ|work)/i,
        /\b(?:previously|formerly|ever|before|current\s+or\s+former|currently|past)\b|previousworker/i,
        /\b(?:have|has|are|did|do)\s+you\b|candidateispreviousworker|previousworker/i],
      value: yesNo(el.previously_employed_here), kind: "yesno" },
    // Non-competes and the family of agreements asked about in the same breath.
    { id: "non-compete",
      re: /non-?\s?compete|non-?\s?solicit|restrictive\s+(?:covenant|employment\s+agreement)/i,
      value: yesNo(el.non_compete), kind: "yesno" },
    { id: "sponsorship-now", re: SPONSORSHIP_NOW_RE, value: yesNo(w.sponsorship_now), kind: "yesno" },
    { id: "sponsorship-future", re: /sponsor/i, not: SPONSORSHIP_NOW_RE, value: yesNo(w.sponsorship_future), kind: "yesno" },
    { id: "work-auth", re: /authoriz|legally\s.*work|eligible\s.*work|right to work/i, value: yesNo(w.authorized_now), kind: "yesno" },
    ...(eeoEnabled ? EEO_RULES : []),
    // The SAME pattern the never-fill policy uses to admit this field, read
    // from it rather than restated. They are one decision — "this asks what you
    // want, not what you earn" — and the copy that lived here had already
    // drifted from the policy's: "what is your desired annual base salary or
    // hourly rate?" was blocked by the policy AND unmatched here, so the field
    // was refused twice for the same missing wording.
    { id: "salary", re: ns.salaryExpectationRe, value: pref.desired_salary },
    { id: "notice-period", re: /notice\s*period/i, value: pref.notice_period },
    // `not:` for the same reason as the employment date rules above, and it
    // matters more here: this one matches on "start date" alone, so iCIMS's
    // "icims_0_startdate_date" day select is squarely inside it, and an
    // availability date written there is a claim about a past job.
    { id: "earliest-start-date", re: /start\s*date|available.*start|availability date/i,
      not: ANY_DATE_PART_RE, value: pref.earliest_start_date },
    { id: "willing-to-relocate", re: /relocat/i, value: pref.willing_to_relocate, kind: "yesno" },
    { id: "how-heard", re: /hear(d)?\s*about/i, value: pref.how_heard },
    // The application's own agreement boxes, and ONLY while the standing
    // consent is on — the rule does not exist otherwise, so there is nothing
    // for a later edit to accidentally enable.
    //
    // `tickWhenYes` is the same authorization the derived "I currently work
    // here" box uses, and it is the right one: the permission lives on the
    // rule, so no other rule can acquire it by growing a value. The writer
    // still looks before it clicks — a box that arrives ticked is left alone —
    // and a click a framework cancels is reported as "didn't stick", never as
    // filled.
    ...(consentForms
      ? [{ id: "consent-forms", re: ns.consentFormRe, tickWhenYes: true, value: "yes" }]
      : []),
    ...custom
      .filter((c) => c.question && c.answer)
      .map((c) => ({ id: "custom", re: null, question: norm(c.question), value: c.answer })),
    // A rule with no answer behind it is TAGGED, not dropped. This used to
    // .filter(), which is what collapsed missing_source into no_rule — see the
    // ObservationOutcome Literal in schemas/autofill_telemetry.py.
  ].map((r) => (r.skip || r.value || (r.values && r.values.some(Boolean))
    || r.tokens?.length
    ? r
    : { ...r, missingSource: true }));

  const labelFor = (input) => {
    const bits = [];
    if (input.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(input.id)}"]`);
      if (lab) bits.push(lab.innerText);
    }
    const wrap = input.closest("label");
    if (wrap) bits.push(wrap.innerText);
    bits.push(
      input.getAttribute("aria-label"),
      input.getAttribute("placeholder"),
      input.name,
      input.id,
    );
    // Common ATS pattern: the question text lives in a preceding sibling/legend.
    const fieldset = input.closest("fieldset");
    if (fieldset?.querySelector("legend")) bits.push(fieldset.querySelector("legend").innerText);
    const container = input.closest("div, li, tr");
    if (container) {
      const q = container.querySelector('[class*="label" i], [class*="question" i]');
      if (q) bits.push(q.innerText);
    }
    return norm(bits.filter(Boolean).join(" | ")).slice(0, 400);
  };

  // First matching rule wins — EXCEPT that a rule with no answer behind it must
  // not shadow a later rule that can actually fill the field. Those rules used
  // to be filtered out of the table entirely, so a custom Q&A sitting after an
  // empty `salary` won "expected salary" on its own; keeping them for
  // missing_source has to preserve that. Remember the first one and keep
  // scanning: it is the answer only when nothing else can fill.
  const matchRule = (labelText) => {
    let missing = null;
    for (const rule of RULES) {
      if (rule.not && rule.not.test(labelText)) continue;
      // `all` is a conjunction, where `re` is a single alternation. A date PART
      // control is only identifiable from two independent signals — which
      // section it sits in and which part it wants — and neither is safe alone:
      // "professional experience" matches every field of the block, and "year"
      // matches a graduation year in any other section. One regex could say
      // that with lookaheads; two named patterns say it legibly.
      const hit = (rule.re && rule.re.test(labelText))
        || (rule.all && rule.all.every((re) => re.test(labelText)))
        || (rule.question && labelText.includes(rule.question));
      if (!hit) continue;
      if (!rule.missingSource) return rule;
      missing ??= rule;
    }
    return missing;
  };

  // KEEP IN SYNC with fillAnswersByQid's copy, from here through commitValue —
  // injected functions are self-contained, so all three blocks exist twice.
  const setNativeValue = (input, value) => {
    const proto = input instanceof HTMLTextAreaElement
      ? window.HTMLTextAreaElement.prototype
      : input instanceof HTMLSelectElement
        ? window.HTMLSelectElement.prototype
        : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(input, value);
    else input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  };

  // A site that REFORMATS what we wrote still took it: "(555) 123-4567" is the
  // phone number we typed, rendered its way. Equality AFTER stripping, never a
  // substring test — an added digit or a truncation means the field holds
  // something we did not write, and "2019-08" vs "08/2019" reorders the digits.
  //
  // NFKD + \p{M} FOLDS accents rather than deleting them. Dropping "é" instead
  // of mapping it to "e" would score every ATS that stores "Jose" for "José" a
  // failure, and that error lands entirely on non-ASCII names and cities — a
  // measurement bias, not just noise. Scripts with no ASCII form (CJK,
  // Cyrillic) still strip to "": deliberate, and handled by the empty guard
  // below rather than by inventing a match between two unrelated values.
  const sameIgnoringFormat = (actual, wrote) => {
    const strip = (s) => String(s).normalize("NFKD").replace(/\p{M}/gu, "")
      .toLowerCase().replace(/[^a-z0-9]/g, "");
    const left = strip(actual);
    // Both sides stripping to "" is NOT a match: a punctuation-only answer
    // against an emptied field would otherwise read as a success.
    return left !== "" && left === strip(wrote);
  };

  // The outcomes that mean the value landed. A positive set rather than a
  // `!== "not_stuck"` test at each call site: asking "is it not THE failure"
  // holds only while there is exactly one, and the vocabulary already carries
  // another outcome that deliberately writes nothing.
  const COMMIT_OK = new Set(["filled", "filled_normalized"]);

  // A controlled input (React/Angular) that rejects or normalizes our value
  // does not revert in the tick that wrote it; it reverts on a later render.
  // Reading back on the same tick therefore reads back our own write and says
  // "stuck" almost always. Two clean animation frames means `filled` reports a
  // value that survived the re-render, not one we merely assigned.
  //
  // Resolves the telemetry outcome rather than a boolean, because that readback
  // sees three genuinely different endings and only one of them is a failure:
  // empty (rejected), byte-equal (filled), reformatted (filled_normalized).
  // Collapsing the last two inflates not_stuck with sites that worked.
  const valueHolds = (input, value) => new Promise((resolve) => {
    let frames = 0;
    // rAF is not serviced in a backgrounded tab. If the user switches tabs
    // mid-fill this would never settle and the Fill button would hang until the
    // panel is reloaded, so an unverifiable write is reported not-stuck instead.
    // Not a hard bound: a backgrounded tab also throttles setTimeout to ≥1s,
    // and to once a minute under intensive throttling — this bounds the wait,
    // it does not promise 1s.
    const timer = setTimeout(() => resolve("not_stuck"), 1000);
    const settle = (outcome) => { clearTimeout(timer); resolve(outcome); };
    const check = () => {
      // isConnected, not just the value: querySelectorAll handed us a static
      // snapshot, and a widget that re-renders (blur is a classic trigger)
      // replaces the nodes of fields still ahead in the loop. A detached node
      // keeps whatever we assign it forever — value alone would call that
      // `filled` for a field the user sees empty. It is checked FIRST: a
      // detached node holding our value still reformats to it, and must not be
      // rescued by the normalization branch below.
      if (!input.isConnected) return settle("not_stuck");
      if (input.value !== value) {
        return settle(sameIgnoringFormat(input.value, value)
          ? "filled_normalized"
          : "not_stuck");
      }
      if (++frames >= 2) return settle("filled");
      requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
  });

  // The full write → commit → verify ladder for a text field.
  const commitValue = async (input, value, { blur = true } = {}) => {
    // preventScroll: focus() scrolls the element into view by default, so a
    // 25-field fill would visibly walk the page and park on the last input.
    input.focus({ preventScroll: true });
    setNativeValue(input, value);
    // ATS forms built out of custom components often listen for keystrokes
    // rather than the standard `input` event. key: "Unidentified" because a
    // real character key risks a widget appending it to the value we just
    // wrote, on top of the `input` event.
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Unidentified", bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keyup", { key: "Unidentified", bubbles: true }));
    // input.blur(), not dispatchEvent(new FocusEvent("blur")): blur does not
    // bubble, and the native call fires the framework's own handler the way a
    // user leaving the field would. Without it the field stays dirty-but-
    // untouched, so blur-triggered validation never runs and a form that gates
    // submit on validity stays disabled while visibly showing our value.
    //
    // `blur: false` is for one shape and one reason, both measured on a live
    // Workday form (deluxe.wd5, 2026-08-08). A split date is several inputs
    // inside ONE widget, and the widget validates when focus leaves the WIDGET
    // — not the section. Blurring after the month, while the year is still
    // empty, hands it a half-written date, which it discards: the month came
    // back empty ~400ms later and the field ended as "MM/2006". Writing both
    // sections first and blurring once left "08/2011" standing. Moving focus
    // to a SIBLING section is harmless, because focus never left the widget.
    //
    // The caller owns the deferred blur — see `pendingBlur` in the fill loop.
    if (blur) input.blur();
    // Every event above carries isTrusted:false — a framework that checks it
    // cannot be satisfied from an extension, and those fields report not_stuck
    // honestly rather than being worked around. NOT the cause of the date bug
    // above: the same untrusted write holds perfectly once the blur is moved.
    return valueHolds(input, value);
  };
  // BELOW the guarded span on purpose: `test_both_copies_of_the_commit_ladder
  // _stay_identical` compares setNativeValue → valueHolds → commitValue, and
  // the AI path has no token inputs to write, so this must not be inside it.

  // The other half of a token commit: the box EMPTYING is the success.
  //
  // A token widget takes what is in its box, turns it into a chip, and clears
  // itself. `valueHolds` asks the opposite question and would call every
  // successful tokenization not_stuck. The 1s bound is the same as its, for the
  // same reason: rAF is not serviced in a backgrounded tab, so an unverifiable
  // write is reported unstuck instead of hanging the Fill button forever.
  //
  // There is deliberately NO isConnected branch, which is the one place this
  // departs from valueHolds. A chip lives in a different node from the box, so
  // whether the BOX is still on the page is not evidence about the chip in
  // either direction — and a node the widget re-rendered away keeps our text,
  // so it reaches the bound and reports not_stuck regardless. The case that
  // check would really catch, a node detaching under a write, is already caught
  // by the valueHolds call below, before Enter is ever pressed.
  const tokenCommitted = (input) => new Promise((resolve) => {
    let waiting = true;
    const timer = setTimeout(() => { waiting = false; resolve("not_stuck"); }, 1000);
    const check = () => {
      // The timeout has already answered, so stop RE-ARMING. Unlike valueHolds,
      // which settles after two clean frames either way, this one waits for a
      // change that may never come — so without this the callback would go on
      // rescheduling itself every frame for the life of the page, long after
      // the promise it belongs to resolved.
      if (!waiting) return;
      if (input.value === "") {
        waiting = false;
        clearTimeout(timer);
        return resolve("filled");
      }
      requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
  });

  // One value into a token input: type it, prove it landed, then commit it.
  //
  // The proof is not optional. A controlled input that REJECTS our write clears
  // itself on a later tick, and so does a widget that accepted it — both end
  // empty, so "the box is empty now" on its own would report `filled` for a
  // field the user finds with no chips in it. `valueHolds` is what separates
  // them: it is the standard readback, run BEFORE Enter, and text that could
  // not survive two frames is text the widget never had.
  //
  // No blur here, unlike commitValue: blurring a token widget's search box
  // clears it, so a blur between skills would throw the next one away. The
  // caller blurs once, after the last.
  const commitToken = async (input, value) => {
    input.focus({ preventScroll: true }); // see commitValue — don't walk the page
    setNativeValue(input, value);
    const typed = await valueHolds(input, value);
    if (!COMMIT_OK.has(typed)) return typed;
    // Enter is the commit. A real character key is not: `commitValue` sends
    // "Unidentified" precisely so a widget cannot append it to the value, and
    // here we want the widget to act on the key.
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
    return tokenCommitted(input);
  };

  // Narrow a whole date to the part THIS control asked for. "" means the date
  // does not carry that part — never a substitute for one.
  //
  // Precedence, strongest first:
  //   1. `input.type`. A native date control's value format is defined by HTML
  //      and enforced by the browser, so it beats both the rule and the label:
  //      <input type="month"> holds "2018-07" and nothing else, whatever the
  //      "Month" label beside it reads, and obeying that label would write "07"
  //      into a control that cannot hold it.
  //   2. `rule.part`, which the rule table resolved from the label — the
  //      vendor's sub-control identifier first, then the plain word (PART_RE).
  const datePartValue = (input, part, raw) => {
    const { year, month, day } = dateParts(raw);
    if (input.type === "month") return year && month ? `${year}-${month}` : "";
    if (input.type === "date") {
      return year && month && day ? `${year}-${month}-${day}` : "";
    }
    if (part === "year") return year;
    if (part === "month") return month;
    if (part === "day") return day;
    // "full": hand back exactly what the source held, "Present" included.
    return raw;
  };

  // How well does an option's visible text match the profile value?
  // Exact > prefix > substring > token overlap, each weighted by how close
  // the lengths are — so "United States" prefers "United States of America"
  // over "United States Minor Outlying Islands". 0–100.
  const scoreOption = (text, value) => {
    const t = norm(text);
    const v = norm(value);
    if (!t || !v) return 0;
    if (t === v) return 100;
    const ratio = Math.min(t.length, v.length) / Math.max(t.length, v.length);
    if (t.startsWith(v) || v.startsWith(t)) return 60 + 30 * ratio;
    if (t.includes(v) || v.includes(t)) return 45 + 25 * ratio;
    const optWords = new Set(t.split(/\W+/).filter((x) => x.length > 1));
    const valWords = v.split(/\W+/).filter((x) => x.length > 1);
    if (!valWords.length) return 0;
    const hits = valWords.filter((x) => optWords.has(x)).length;
    return (hits / valWords.length) * (35 + 15 * ratio);
  };

  // Pick the best option for a rule: kind keyword sets first (yes/no, EEO),
  // then generic text scoring with a floor so we never pick a wild guess.
  const bestOption = (options, rule) => {
    if (rule.kind) {
      const words = optionWordsFor(rule.kind, String(rule.value));
      const hit = options.find((o) => words.some((wre) => wre.test(o.text)));
      if (hit) return hit;
      // No fuzzy fallback for a date part. A month has exactly twelve
      // well-known renderings and the patterns above cover all four forms of
      // each; if none is on offer, this is not a month list. The scorer below
      // would then pick whatever merely shares letters with the month's name —
      // "Marketing" scores 45 against "March" — and a near miss on an
      // employment date is a date the user never gave us, not an approximation.
      if (rule.kind === "month") return null;
    }
    // A protected-class option, matched on the category the form is actually
    // offering rather than on the decoration around it: Workday spells "Asian"
    // as "3-Asian (Not Hispanic or Latino) (United States of America)", which
    // the exact bar below refuses outright — so with the opt-in ON the field
    // was still never filled. The comparison stays EXACT on what remains, so
    // "Asian" continues not to match "Asian Indian".
    if (rule.eeo && rule.value) {
      const wanted = eeoContext.canonicalOptionText(String(rule.value));
      const exact = wanted
        && options.find((o) => eeoContext.canonicalOptionText(o.text) === wanted);
      if (exact) return exact;
    }
    let best = null;
    let bestScore = 0;
    for (const o of options) {
      const s = scoreOption(o.text, String(rule.value));
      if (s > bestScore) { best = o; bestScore = s; }
    }
    // 100 is scoreOption's EXACT tier — normalized equality and nothing else.
    // On a protected-class question that is the only acceptable bar, and it is
    // the same one the EEO module applies to exact option labels: "Asian" is a
    // different statement from "Asian Indian", which the scorer rates 72.5 as a
    // prefix, and "no" is a different statement from "I prefer not to answer",
    // which it rates 47 for containing the letters of "not". A near miss here
    // is a false answer, not an approximate one, and a blank the user fills in
    // themselves is the correct failure.
    //
    // The floor stays 40 everywhere else. The scorer's tolerance is the whole
    // reason "United States" finds "United States of America", and most of the
    // rule table depends on it.
    return bestScore >= (rule.eeo ? 100 : 40) ? best : null;
  };

  const isVisible = (el) =>
    !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);

  // Protected-class disclosures need a stronger standard than the generic
  // geometry check: select2 hides native selects in clipped 1×1 boxes that
  // still have client rects. Check the control and every ancestor for CSS or
  // accessibility hiding, and require meaningful rendered bounds.
  const isStrictlyVisible = (el) => {
    if (!isVisible(el)) return false;
    const bounds = el.getBoundingClientRect();
    if (bounds.width <= 1 || bounds.height <= 1) return false;
    for (let node = el; node; node = node.parentElement) {
      if (node.hidden || node.getAttribute?.("aria-hidden") === "true") return false;
      const style = getComputedStyle(node);
      const opacity = Number.parseFloat(style.opacity);
      if (
        style.display === "none"
        || style.visibility === "hidden"
        || style.visibility === "collapse"
        || style.contentVisibility === "hidden"
        || (!Number.isNaN(opacity) && opacity <= 0.01)
        || (style.clip && style.clip !== "auto")
        || (style.clipPath && style.clipPath !== "none")
      ) {
        return false;
      }
    }
    return true;
  };

  // react-select / select2 / plain ARIA comboboxes: a text input that opens a
  // filtered option list instead of accepting free text.
  const isCombobox = (input) =>
    input instanceof HTMLInputElement &&
    (input.getAttribute("role") === "combobox" ||
      input.hasAttribute("aria-autocomplete") ||
      // Workday's select/search inputs carry NO combobox ARIA at all — no
      // role, no aria-autocomplete, nothing on an ancestor the selector below
      // names. The one signal is the vendor's own widget-type attribute, read
      // off a live form (bah.wd1, 2026-08-08): <input id="phoneNumber--
      // countryPhoneCode" data-uxi-widget-type="selectinput"
      // placeholder="Search">. That miss is why 55 not_stuck events carried a
      // rule_id: the profile HAD the answer and it was typed into a box that
      // takes no free text. The telemetry label's "| search |" segment is the
      // placeholder and is deliberately NOT the signal — a label pattern would
      // reroute every site's honest search box. The multiselect variant is
      // matched on the same family; both open a [role="option"] popup.
      /^(multi)?selectinput$/.test(
        input.getAttribute("data-uxi-widget-type") ?? "") ||
      !!input.closest(
        '[role="combobox"], [class*="select__" i], [class*="select2" i], [class*="autocomplete" i]'
      ));

  // Workday's dropdowns are BUTTONS, not selects or inputs: <button
  // aria-haspopup="listbox" type="button" id="country--country"> whose visible
  // text is the committed value ("Select One" until one commits). Verified
  // live twice (homedepot.wd5 2026-08-06, bah.wd1 2026-08-08). The guards are
  // from the same dumps: the header's utility chrome (Settings, the account
  // menu) carries aria-haspopup too, but always with a data-automation-id and
  // type="submit", while every form dropdown has an explicit type="button"
  // and no automation id. A button with NO type attribute defaults to
  // "submit", so the type test also refuses those — no live form dropdown
  // omits it.
  const isListboxButton = (el) =>
    el instanceof HTMLButtonElement
    && el.getAttribute("aria-haspopup") === "listbox"
    && el.type !== "submit"
    && !el.getAttribute("data-automation-id");

  // The committed value is the button's own text; these are the empty states.
  // norm() runs first, so case and whitespace are already folded.
  const LISTBOX_PLACEHOLDER = /^(select( one)?|choose( one)?|—|-)?$/;

  const listboxButtonText = (button) =>
    String(button.innerText ?? button.textContent ?? "").trim();
  const listboxButtonEmpty = (button) =>
    LISTBOX_PLACEHOLDER.test(norm(listboxButtonText(button)));

  // An option that is not a choice. Live on Workday (bah.wd1, 2026-08-08): a
  // multiselect renders each ALREADY-CHOSEN value as
  // `[data-automation-id="selectedItem"]` inside a
  // `[data-automation-id="selectedItemList"]`, and marks it `role="option"`.
  // Those are chips, not offers — clicking one un-picks a value the user or an
  // earlier field already committed, in a completely different control.
  const isChosenChip = (node) =>
    !!node.closest('[data-automation-id="selectedItemList"], [data-automation-id="selectedItem"]');

  const listboxOptions = (input) => {
    for (const attr of ["aria-controls", "aria-owns"]) {
      const id = input.getAttribute(attr);
      const list = id ? document.getElementById(id) : null;
      const nodes = list ? [...list.querySelectorAll('[role="option"]')] : [];
      if (nodes.length) return nodes;
    }
    // The unscoped fallback, and the reason it is last. `[role="option"]` is
    // document-wide, so it collects every OPEN popup on the page plus the
    // chips above — measured live: one open dropdown returned 62 nodes, one of
    // which belonged to the phone-country-code widget three fields away. The
    // scoped branches are what keep a write inside its own control; this is
    // for the widgets that publish no relationship at all, and it at least
    // refuses the chips.
    return [...document.querySelectorAll('[role="option"]')]
      .filter((node) => isVisible(node) && !isChosenChip(node));
  };

  // A popup's own "no answer yet" row. Never a legitimate choice: picking it
  // writes the placeholder back as though it were the user's answer, and on a
  // required field that reads as filled while the form still refuses it.
  // Matched on the same text bar as the button's own empty state.
  const isPlaceholderOption = (text) => LISTBOX_PLACEHOLDER.test(norm(text));

  const fireMouseSequence = (el) => {
    for (const type of ["pointerdown", "mousedown", "mouseup", "click"]) {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    }
  };

  const fillCombobox = async (input, rule) => {
    input.focus({ preventScroll: true }); // see commitValue — don't walk the page
    if (rule.kind) {
      // Canonical values ("not_veteran") are not typeable — open the full
      // list and pick by keywords instead.
      fireMouseSequence(input);
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    } else {
      setNativeValue(input, String(rule.value));
    }
    // Options may load async (remote school lists etc.) — poll briefly.
    for (let waited = 0; waited < 1600; waited += 200) {
      await sleep(200);
      const nodes = listboxOptions(input);
      if (!nodes.length) continue;
      const options = nodes.map((el) => ({ el, text: el.innerText ?? "" }))
        // A placeholder row is not an offer — see isPlaceholderOption.
        .filter((o) => o.text.trim() && !isPlaceholderOption(o.text));
      const best = bestOption(options, rule);
      if (best) {
        fireMouseSequence(best.el);
        await sleep(100);
        return { ok: true, text: best.text.trim().slice(0, 60) };
      }
      break; // options visible but nothing matches — don't guess
    }
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    // Blur explicitly on the failure path: react-select/select2 clear their
    // search box on blur, and leaving that to the NEXT field's focus() would
    // make the end state depend on whether another field happens to follow.
    // Blur here so the note we record describes what the user will actually
    // find — an empty control, not free text sitting in the box.
    input.blur();
    return { ok: false, text: String(rule.value) };
  };

  // A button dropdown, driven the only way it can be: open the popup, read the
  // options it renders, click the best one. There is nothing to type into and
  // nothing to set — `setNativeValue` has no target here, which is why this is
  // its own writer rather than a branch of fillCombobox.
  //
  // The readback is the button's own TEXT, because that is where the widget
  // prints its committed value. A click the framework cancelled leaves the
  // placeholder standing, and that is reported honestly rather than as filled.
  const fillListboxButton = async (button, rule) => {
    const before = listboxButtonText(button);
    button.focus({ preventScroll: true }); // see commitValue — don't walk the page
    fireMouseSequence(button);
    // Same ladder as the combobox's keyboard open: some builds render the
    // popup on ArrowDown rather than on the click alone.
    button.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    for (let waited = 0; waited < 1600; waited += 200) {
      await sleep(200);
      const nodes = listboxOptions(button);
      if (!nodes.length) continue;
      const options = nodes.map((el) => ({ el, text: el.innerText ?? "" }))
        // A placeholder row is not an offer — see isPlaceholderOption.
        .filter((o) => o.text.trim() && !isPlaceholderOption(o.text));
      const best = bestOption(options, rule);
      if (!best) break; // options visible but nothing matches — don't guess
      fireMouseSequence(best.el);
      await sleep(100);
      // The option click is only a request; the widget decides. Text that did
      // not change is a write that did not land.
      const after = listboxButtonText(button);
      return after !== before
        ? { ok: true, text: after.slice(0, 60) }
        : { ok: false, text: best.text.trim().slice(0, 60) };
    }
    // Close what we opened. A popup left standing covers the next field, and
    // on a wizard step it covers the page's own Continue button.
    button.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    button.blur();
    return { ok: false, text: String(rule.value) };
  };

  /** Which split-date WIDGET this control is a section of, or null.
   *
   * Measured on a live Workday form (deluxe.wd5, 2026-08-08): a date is one
   * `[data-automation-id="dateInputWrapper"]` containing several
   * `role="spinbutton"` inputs — `…-dateSectionMonth-input`,
   * `…-dateSectionYear-input` — each carrying `aria-valuetext` of "MM"/"YYYY"
   * while empty. The widget validates when focus leaves the WIDGET, so the
   * sections have to be written before anything blurs out of it.
   *
   * The wrapper is the identity where there is one; the id prefix is the
   * fallback, because it is what actually distinguishes one date from another
   * (`workExperience-6--startDate` vs `…--endDate`) and vendors other than
   * Workday publish no wrapper at all. Returns null for an ordinary input,
   * which is every control this does not apply to. */
  const dateWidgetOf = (input) => {
    if (input.getAttribute("role") !== "spinbutton") return null;
    const section = /^(.*)-dateSection(?:Month|Year|Day)-input$/.exec(input.id || "");
    if (section) return section[1];
    const wrapper = input.closest('[data-automation-id="dateInputWrapper"]');
    return wrapper ? (wrapper.id || "dateInputWrapper") : null;
  };

  // The one date section whose blur is still owed, if any. Held rather than
  // performed so that the sibling sections of the same widget can be written
  // first — see commitValue's `blur: false`.
  let pendingBlur = null;
  const flushPendingBlur = () => {
    // isConnected: a widget that re-rendered between the write and here has
    // replaced the node, and blurring a detached input does nothing anyway.
    if (pendingBlur?.input?.isConnected) pendingBlur.input.blur();
    pendingBlur = null;
  };

  const filled = [];
  const eeoFilled = [];
  const corrected = [];
  // Fields already holding the answer this fill would write. RENDERED, never
  // sent: no telemetry observation is emitted for an entry here, because the
  // frozen outcome vocabulary (schemas/autofill_telemetry.py) has no value for
  // a write that never happened and a batch carrying an unknown outcome 422s
  // whole. EEO controls never land here — an answer already on a
  // protected-class control is the user's own and is claimed nowhere.
  const already = [];
  const recordFilled = (item) => filled.push(item);
  let seen = 0;
  const doneRadioGroups = new Set();

  const observations = [];
  const host = location.hostname;
  const radioObsKeys = new Set(); // one observation per radio group+outcome, not per button
  const kindOf = (input) => {
    if (input instanceof HTMLSelectElement) return "select";
    if (input instanceof HTMLTextAreaElement) return "textarea";
    // Before the type tests: a button reports type "button"/"submit", neither
    // of which those name, but the order is what a reader checks first.
    if (isListboxButton(input)) return "combobox";
    if (input.type === "radio") return "radio";
    if (input.type === "checkbox") return "checkbox";
    if (isCombobox(input)) return "combobox";
    return "text";
  };
  // options: TEXTS only, selects/radios only, ≤30 (mirrors the AI-path caps).
  const optionTexts = (input, kind) => {
    if (kind === "select") {
      return [...input.options]
        .filter((o) => o.value !== "")
        .map((o) => (o.textContent ?? "").trim())
        .filter(Boolean)
        .slice(0, 30);
    }
    if (kind === "radio" && input.name) {
      return [...document.querySelectorAll(
        `input[type="radio"][name="${CSS.escape(input.name)}"]`)]
        .map((r) => labelFor(r).slice(0, 80))
        .filter(Boolean)
        .slice(0, 30);
    }
    // A popup's options, if it happens to be OPEN when this is called — which
    // is the case for exactly one caller: the observe() at the end of a
    // listbox-button write, whose snap failure is the row that most needs to
    // say what the page offered. Nothing is opened to collect them: a
    // telemetry read may not drive the page, so a closed popup reports
    // nothing rather than being poked into rendering.
    if (kind === "combobox" && isListboxButton(input)) {
      const texts = listboxOptions(input)
        .map((el) => String(el.innerText ?? "").trim())
        .filter(Boolean)
        .slice(0, 30);
      return texts.length ? texts : null;
    }
    return null;
  };
  // NEVER include values here — telemetry carries labels/kinds/options only.
  const observe = (input, kind, labelText, rule, outcome) => {
    if (kind === "radio") {
      const key = `${input.name || labelText}::${outcome}`;
      if (radioObsKeys.has(key)) return;
      radioObsKeys.add(key);
    }
    const obs = { label: labelText.slice(0, 160), kind, rule_id: rule?.id ?? null, host, outcome };
    const opts = optionTexts(input, kind);
    if (opts && opts.length) obs.options = opts;
    observations.push(obs);
  };

  // `button` is in the walk for ONE shape: Workday's listbox dropdowns
  // (isListboxButton). Every other button on the page — submit, the header's
  // utility menus, a page's own controls — is dropped by isFormJunk below.
  // Before this, 5 of 18 controls on a Workday step were not merely unfillable
  // but ABSENT from telemetry in every outcome, so no evidence pass over that
  // table could see them.
  const inputs = document.querySelectorAll("input, textarea, select, button");
  // A control the loop below never looks at, so the block pre-pass must not
  // either — a disabled clone would otherwise make its block "exist".
  const isFormJunk = (input) => {
    if (input.disabled || input.readOnly) return true;
    // A BUTTON is junk unless it is one of Workday's listbox dropdowns — and
    // the type ladder below cannot express that, because such a button's own
    // type IS "button". Answered here, ahead of it, so the two rules do not
    // fight: everything the walk newly reaches is decided in one place.
    if (input instanceof HTMLButtonElement) return !isListboxButton(input);
    return input.type === "hidden"
      // `password` is on the never-fill policy (content/policy.js), but that
      // list matches LABEL TEXT — so a password box labelled in another
      // language, or mislabelled "Email", was protected only by no rule
      // happening to match it. The type is the fact; the label is a
      // description of it. Nothing this extension fills is ever a password, so
      // exclude it structurally here and leave the policy regex as the second
      // gate.
      || ["file", "submit", "button", "image", "reset", "password"].includes(input.type);
  };

  // ---- which repeated block a control belongs to -----------------------
  //
  // Every vendor that repeats a block publishes the block's identity in the
  // control names; only the shape differs. `family` groups the blocks that
  // repeat together, `id` distinguishes them:
  //
  //   Workday   workexperience-192--location      → workexperience / 192
  //   Siemens   company | 42343-2-0 | … | company → 42343 / 0  (…-sample: the
  //             prototype, which is an id like any other and simply never
  //             turns out to be visible)
  //   iCIMS     icims_0_degree, icims_1_degree    → icims / 0, icims / 1
  //   iCIMS/ORC … | professional experience (1)*  → experience / 1
  //
  // The FAMILY matters as much as the id: a page's education blocks are
  // numbered independently of its employment blocks, so one page-wide sequence
  // would give the first education block entry 2 on a form that renders two
  // jobs first. Where a vendor numbers ALL its repeated sections in one
  // sequence (iCIMS's `icims_<n>_`), family and id agree with that and the
  // rules keep the sections apart, as they always have.
  const BLOCK_PATTERNS = [
    /\b([a-z]+)-(\d+)--/,
    /\b(\d{3,})-\d+-(\d+|sample)\b/,
    /\b([a-z]+)_(\d+)_/,
    /(experience|employment|education|history)[^|]*\((\d+)\)/,
  ];
  const blockKeyOf = (labelText) => {
    for (const re of BLOCK_PATTERNS) {
      const m = re.exec(labelText);
      if (m) return { family: m[1], key: `${m[1]}\u0000${m[2]}` };
    }
    return null;
  };

  // Entry numbers, decided ONCE before anything is written. Deciding per
  // control as we went is what `rule._n` did, and it made every rule count
  // separately: a block that renders no start-date inputs left `emp-start-month`
  // un-advanced, so the NEXT block — already reading its title and employer
  // from the second job — got the first job's start date.
  //
  // Visibility is judged per BLOCK, not per control, and with the plain
  // geometry check rather than the loop's `!isSelect && !isVisible` variant.
  // That variant exists so select2's offscreen native select still gets
  // written, and it must keep doing so — but a block whose ONLY control is an
  // offscreen select is a template, not a job, and may not claim an entry.
  const labelByInput = new Map();
  const blockOrder = [];
  const visibleBlocks = new Set();
  for (const input of inputs) {
    if (isFormJunk(input)) continue;
    const labelText = labelFor(input);
    labelByInput.set(input, labelText);
    const block = labelText && blockKeyOf(labelText);
    if (!block) continue;
    if (!blockOrder.some((b) => b.key === block.key)) blockOrder.push(block);
    if (isVisible(input)) visibleBlocks.add(block.key);
  }
  const blockEntries = new Map();
  const perFamily = new Map();
  for (const block of blockOrder) {
    if (!visibleBlocks.has(block.key)) continue;
    const next = perFamily.get(block.family) ?? 0;
    blockEntries.set(block.key, next);
    perFamily.set(block.family, next + 1);
  }
  // Nth control of THIS rule within THIS block, for the rules whose list holds
  // more than one slot per entry (see `perEntry`).
  const withinBlock = new Map();

  for (const input of inputs) {
    if (isFormJunk(input)) continue;
    seen += 1;
    const isSelect = input instanceof HTMLSelectElement;
    const kind = kindOf(input);
    const labelText = labelByInput.get(input);
    if (!labelText) continue; // unlabeled junk stays out of telemetry too
    // FIRST, ahead of the EEO opt-in, matchRule, and the visibility gate below:
    // a never-fill control is a statement about the CONTROL, so no user
    // setting, rule table, or rendering detail may change the answer. An EEO
    // self-identification SIGNATURE reported eeo_disabled while the opt-in was
    // off, which reads as "turn the opt-in on and we will handle this" — and we
    // never will.
    if (ns.isPolicyBlocked(labelText, { consentForms })) {
      observe(input, kind, labelText, null, "policy_blocked");
      continue;
    }
    const rule = matchRule(labelText);
    // labelFor() is composite: an ordinary Skills control can inherit a nearby
    // "Gender" heading. A matched token rule is intrinsically multi-value and
    // cannot be a scalar protected-class disclosure, so its explicit shape
    // outranks incidental EEO wording from the surrounding container.
    const isEeoField = !rule?.tokens && isEeoLabel(labelText);
    if (isEeoField && ns.shouldSkipEeoControl({
      input,
      kind,
      labelText,
      enabled: eeoEnabled,
      rule,
      isStrictlyVisible,
      observe,
    })) continue;
    // Enterprise forms keep invisible clones of whole sections (per-country
    // field groups, wizard steps) — filling those looks like success while
    // the visible field stays empty. Hidden native selects stay available for
    // select2-style widgets, except EEO controls: protected-class disclosures
    // must always be visible to the user before the extension can fill them.
    const hidden = !isSelect && !isVisible(input);
    if (hidden) {
      // Log invisible fields ONLY when a rule matched — every page carries
      // hidden clone junk; a matched-but-hidden field is the interesting case.
      // missingSource excluded alongside skip: `hidden` means "we had an answer
      // and could not reach the field". A field we could not have filled anyway
      // is not the interesting case, and before these rules were retained it
      // logged nothing here either.
      if (rule && !rule.skip && !rule.missingSource) {
        observe(input, kind, labelText, rule, "hidden");
      }
      continue;
    }
    if (!rule) { observe(input, kind, labelText, null, "no_rule"); continue; }
    if (rule.skip) { observe(input, kind, labelText, rule, "skip_rule"); continue; }
    // Recognised the field, have no answer for it. Never write, always report.
    if (rule.missingSource) {
      observe(input, kind, labelText, rule, "missing_source");
      continue;
    }

    // List rules (education, employment) resolve through the block the control
    // sits in: block N of its family gets resume entry N, counting visible
    // blocks only. Where no block can be identified — a flat form with one
    // Employer box and one Job Title box, which is most of the corpus — fields
    // are handed entries in DOM order, per rule, as they always were.
    let value = rule.value;
    if (rule.values) {
      // Slots per entry: 1 normally, 2 for the interleaved start,end lists that
      // carry iCIMS's and Oracle's unlabelled From/To pairs. Reading those
      // straight through assumed a From box is never rendered without its To;
      // indexing from the BLOCK's base drops the assumption, because a block
      // that breaks it can no longer shift the block after it.
      const perEntry = rule.perEntry ?? 1;
      const block = blockKeyOf(labelText);
      let idx;
      if (block) {
        const entry = blockEntries.get(block.key);
        // A block no visible control belongs to is a template, not a job. It
        // must claim no entry — including via a hidden native <select>, which
        // the visibility gate above deliberately lets through.
        if (entry === undefined) continue;
        const slotKey = `${rule.id} ${block.key}`;
        const nth = withinBlock.get(slotKey) ?? 0;
        withinBlock.set(slotKey, nth + 1);
        idx = entry * perEntry + Math.min(nth, perEntry - 1);
      } else {
        idx = rule._n ?? 0;
        rule._n = idx + 1;
      }
      value = rule.values[idx];
      // A consumed-empty list slot emits nothing. Deliberately NOT
      // missing_source despite the surface symmetry — the reasoning is in
      // test_a_block_past_the_end_of_the_list_reports_nothing.
      if (!value) continue;
    }
    // A date rule holds the WHOLE date and narrows it here, where the control
    // is finally known.
    if (rule.part) {
      const narrowed = datePartValue(input, rule.part, value);
      // We have the date and it does not carry the part this control wants: a
      // year-only "2019" meeting a month spinner, any resume date meeting a day
      // select. That is a gap in the SOURCE rather than in the rules — unlike
      // the consumed-empty slot above, this block DOES belong to an entry we
      // hold — and it is the one thing a writer must never paper over.
      // Inventing a month or a day states a fact about the user's history they
      // never gave us, on a record an employer may verify.
      if (!narrowed) {
        observe(input, kind, labelText, rule, "missing_source");
        continue;
      }
      value = narrowed;
    }
    // `eeo` travels with the answer because bestOption is reached from two
    // branches — the select loop below and fillCombobox — and neither passes
    // the rule itself. The verdict is label-based except for the explicit token
    // shape above, which cannot carry one protected-class scalar answer.
    const res = { kind: rule.kind, value, eeo: isEeoField };

    const label = labelText.slice(0, 60);
    if (isEeoField) {
      await ns.handleEeoControl({
        context: eeoContext,
        input,
        kind,
        isSelect,
        isCombobox: isCombobox(input),
        // Workday renders its voluntary-disclosure dropdowns as the same
        // listbox buttons as the rest of the form, so the EEO module needs
        // both the predicate and the writer — the consent gate and the
        // exact-match bar stay entirely its own.
        isListboxButton: isListboxButton(input),
        listboxButtonEmpty,
        listboxButtonText,
        fillListboxButton,
        rule,
        res,
        labelText,
        label,
        filled,
        eeoFilled,
        observe,
        bestOption,
        setNativeValue,
        optionWordsFor,
        labelFor,
        doneRadioGroups,
        fillCombobox,
        commitValue,
        commitOk: COMMIT_OK,
      });
      continue;
    }
    // A `tokens` rule holds a LIST for one control, and only a token input can
    // carry that. `kind` is exactly the right test: it reports "text" for a
    // plain input and something else for every control that holds one value —
    // a select holds one option, a checkbox one bit, a combobox one snapped
    // choice — and "text" is what telemetry recorded for the live Workday
    // signature this writer was built for. Siemens renders Skills as a
    // multi-select over a fixed taxonomy instead; writing there would state ONE
    // skill for a person who supplied ten, so it is recognised and declined.
    if (rule.tokens) {
      if (kind !== "text") {
        observe(input, kind, labelText, rule, "skip_rule");
        continue;
      }
      const wanted = rule.tokens;
      const written = [];
      let outcome = "not_stuck";
      for (const token of wanted.slice(0, SKILL_TOKEN_MAX)) {
        outcome = await commitToken(input, token);
        // Stop at the first refusal. The readback is bounded by a one-second
        // timeout, so continuing would spend ten seconds typing into a control
        // that has already said no — and leave our text sitting in it.
        if (!COMMIT_OK.has(outcome)) break;
        written.push(token);
      }
      // react-select and friends clear the search box on blur, so blur here
      // rather than leaving the end state to depend on whether another field
      // happens to follow (see fillCombobox's failure path).
      input.blur();
      const skipped = wanted.length - written.length;
      observe(input, kind, labelText, rule, written.length ? "filled" : outcome);
      recordFilled({
        label,
        // 120, not the 60 every other branch uses: this echoes a LIST, and 60
        // characters truncates it after the third skill — which reads as if the
        // fill stopped there.
        value: written.join(", ").slice(0, 120),
        // Naming the SKIPPED count is the whole point of capping out loud. The
        // user cannot tell 10-of-14 from 10-of-75 by looking at the chips, and
        // the ones that matter for this application may be the ones dropped.
        note: !written.length
          ? "may not have registered, add your skills manually"
          : skipped
            ? `${written.length} of ${wanted.length} added, ${skipped} skipped; add any that matter manually`
            : undefined,
      });
      continue;
    }
    if (isSelect) {
      const options = [...input.options]
        .filter((o) => o.value !== "") // skip "Select…" placeholders
        .map((o) => ({ el: o, text: o.textContent ?? "" }));
      const best = bestOption(options, res);
      if (best && input.value !== best.el.value) {
        setNativeValue(input, best.el.value);
        recordFilled({ label, value: best.text.trim().slice(0, 60) });
        observe(input, kind, labelText, rule, "filled");
      } else if (best && input.value === best.el.value) {
        // Already at the option we would pick — a re-run, or an agreeing ATS
        // prefill. Without this the strip said "0 filled" over a full form.
        already.push({ label, value: best.text.trim().slice(0, 60) });
      }
      // Select-no-match: no frozen outcome — emit nothing.
    } else if (input.type === "radio") {
      const groupKey = `${input.name}::${res.value}`;
      if (doneRadioGroups.has(groupKey)) continue;
      const words = optionWordsFor(res.kind, String(res.value));
      // Spread: querySelectorAll returns a NodeList, which has no .some().
      const group = [...(input.name
        ? document.querySelectorAll(`input[type="radio"][name="${CSS.escape(input.name)}"]`)
        : [input])];
      for (const radio of group) {
        const rl = labelFor(radio);
        if (words.some((wre) => wre.test(rl))) {
          if (radio.checked) {
            // The matching button is already selected. Before this branch the
            // checked button was clicked AGAIN and reported `filled`, so a
            // re-run inflated the count with writes that wrote nothing.
            already.push({ label, value: rl.slice(0, 40) });
          } else {
            radio.click();
            recordFilled({ label, value: rl.slice(0, 40) });
            observe(input, kind, labelText, rule, "filled");
          }
          doneRadioGroups.add(groupKey);
          break;
        }
      }
    } else if (input.type === "checkbox") {
      // The second exception, and the only other one: a box whose answer we
      // DERIVED. `tickWhenYes` is the authorization and it lives on the rule,
      // so a later rule cannot acquire it by accident. Protected-class
      // checkbox authorization is owned independently by the EEO module.
      if (rule.tickWhenYes && res.value === "yes") {
        // click() TOGGLES, so a box that already carries the right answer must
        // not be clicked: a resumed application, or the user's own click before
        // pressing Fill, arrives ticked. It matters here because an "I currently
        // work here" ticked onto a job that
        // ended in 2021 is a false statement on a record employers verify,
        // rather than an omission.
        if (!input.checked) {
          input.click();
          const ticked = input.checked === true;
          observe(input, kind, labelText, rule, ticked ? "filled" : "not_stuck");
          recordFilled({
            label,
            value: "ticked",
            // Provenance the user can check, which is the point of HR-1: the
            // one thing to re-read is the end date on that job.
            note: ticked
              ? "derived from your resume; this job has no end date"
              : "may not have registered, check the box",
          });
        } else {
          // Ticked already, and the resume agrees this job is current: the
          // derived answer is on the page. Same re-run honesty as the other
          // branches; no derivation note, because nothing was derived now.
          already.push({ label, value: "ticked" });
        }
        continue;
      }
      // too risky to guess consent/subscribe checkboxes
      observe(input, kind, labelText, rule, "skipped_checkbox");
      continue;
    } else if (isListboxButton(input)) {
      // Fill-only-if-empty, the same bar every identity combobox takes: the
      // button's text IS its answer, and an answer already standing is the
      // user's or a prior run's. `already` rather than a silent skip, so a
      // re-run on a wizard step says "nothing new to fill" instead of "0
      // filled" over a page that is visibly complete.
      if (!listboxButtonEmpty(input)) {
        already.push({ label, value: listboxButtonText(input).slice(0, 60) });
        continue;
      }
      const popup = await fillListboxButton(input, res);
      observe(input, kind, labelText, rule, popup.ok ? "filled" : "combobox_snap_failed");
      recordFilled({
        label,
        value: popup.text,
        note: popup.ok ? undefined : "no matching option, choose it manually",
      });
    } else if (isCombobox(input)) {
      if (input.value) {
        // Fill-only-if-empty stands (§11 item 8c defers combobox overwrite),
        // but a value that IS ours is reported rather than silently skipped.
        // Byte equality first for the same CJK/Cyrillic reason as the text
        // branch: sameIgnoringFormat strips those scripts to "" and refuses.
        if (input.value === String(res.value)
          || sameIgnoringFormat(input.value, String(res.value))) {
          already.push({ label, value: String(input.value).slice(0, 60) });
        }
        continue;
      }
      const combo = await fillCombobox(input, res);
      observe(input, kind, labelText, rule, combo.ok ? "filled" : "combobox_snap_failed");
      recordFilled({
        label,
        value: combo.text,
        note: combo.ok ? undefined : "no matching option, enter it manually",
      });
    } else if (!input.value) {
      // Controlled inputs (React/Angular) can reject or clear the value —
      // report honestly instead of claiming a fill that didn't take.
      //
      // A date SECTION defers its blur: blurring here hands the widget a
      // half-written date and it discards the section (see commitValue). The
      // deferred blur is flushed when the fill reaches a different widget, and
      // once more at the end of the run.
      const widget = dateWidgetOf(input);
      if (widget && pendingBlur && pendingBlur.widget !== widget) flushPendingBlur();
      let outcome = await commitValue(input, String(res.value), { blur: !widget });
      if (widget) pendingBlur = { widget, input };
      // Workday's month spinbutton keeps "6" for the "06" we wrote, and the
      // readback's stripped comparison calls that a miss — leading zeros are
      // significant in postal codes and requisition ids, so it refuses to fold
      // them in general (test_a_dropped_leading_zero_stays_not_stuck). Inside a
      // date PART that reasoning does not apply: month 6 and month 06 are the
      // same month, and the digits cannot mean anything else.
      if (!COMMIT_OK.has(outcome) && rule.part && rule.part !== "full"
        && Number.parseInt(input.value, 10) === Number.parseInt(value, 10)) {
        outcome = "filled_normalized";
      }
      const ok = COMMIT_OK.has(outcome);
      observe(input, kind, labelText, rule, outcome);
      recordFilled({
        label,
        value: String(res.value),
        // No hedge on filled_normalized: the value landed, the site just
        // renders it its own way, and hedging a success teaches the user to
        // distrust the ones that worked.
        note: ok ? undefined : "may not have registered, check the field",
      });
    } else if (rule.identity && !rule.formatTolerant
      ? norm(input.value) === norm(String(res.value))
      : input.value === String(res.value)
        || sameIgnoringFormat(input.value, String(res.value))) {
      // The field already holds this answer. THREE bars, because "same value"
      // is not one question:
      // - identity fields compare under norm(), the SAME bar the correction
      //   branch below uses, so the two branches partition exactly. Identity
      //   punctuation is semantic — "O'Brien" is not "OBrien" and
      //   "j.doe@corp.com" is not "jdoe@corp.com" — so the stripped
      //   comparison would swallow corrections the identity feature exists
      //   to make (a resume-parse prefill is a guess; the profile is truth).
      // - the `formatTolerant` identity rule (phone) keeps the stripped bar,
      //   ahead of the correction branch on purpose: "(555) 123-4567" for
      //   "5551234567" is our number rendered the site's way, and
      //   "correcting" it would churn against the site's own formatter on
      //   every run.
      // - everything else takes byte equality FIRST — sameIgnoringFormat
      //   strips CJK/Cyrillic to "" and refuses the match, so without it a
      //   re-run over a field holding "東京" reported "0 filled" again —
      //   then the stripped comparison for formatting-only differences.
      already.push({ label, value: String(input.value).slice(0, 60) });
    } else if (rule.identity && norm(input.value) !== norm(String(res.value))) {
      // Identity fields are profile-owned: an ATS prefill (resume-parse
      // guess, e.g. Jobvite splitting the PDF header name) that disagrees
      // with the profile gets overwritten, loudly — silently keeping a
      // wrong prefill is how "Jordan Example" became "Jordan".
      const was = input.value.slice(0, 40);
      setNativeValue(input, String(res.value));
      corrected.push({ label, was, value: String(res.value) });
      observe(input, kind, labelText, rule, "corrected");
    }
  }
  // The last date widget's blur, owed since its final section was written. The
  // loop flushes on moving to a different widget; this is the one at the end,
  // and it is what makes the date validate at all when the run finishes on a
  // date field — which on a Workday experience block it usually does.
  flushPendingBlur();
  return { filled, eeoFilled, corrected, already, seen, observations };
}
// Historical sentinel retained for source-level diagnostics; the harness now
// executes this module's published function directly.
// ---- end fillFormFromProfile ----


  ns.fillFormFromProfile = fillFormFromProfile;
})();
