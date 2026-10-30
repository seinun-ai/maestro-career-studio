# Form questions by country: sources

Phase 2 of `docs/plans/2026-10-30-country-form-questions.md` (Task 2.1). Every country fact Phase 3
builds on, checked on 2026-10-30 against the source that owns it: a government, a regulator, the
law's text, or the standard's owner. No government owns what application forms ask, so for those
conventions the source is two independent job boards or ATS vendors. No employer is named, and
no real application is quoted.

**How it was checked.** Four research passes, one per country group, each wrote one section below.
I then re-read nine of the riskiest rows on their source pages myself, and all nine matched:
- Google's UAE address data (UAE 23–24);
- Home Affairs' work restrictions (AU A1);
- the UK–Ireland Common Travel Area memorandum, paragraphs 8 and 17, and the gov.ie page (Europe 8);
- the IND's EU/EEA/Swiss page and its salary criterion (Europe 5, 25);
- u.ae's work permits page (UAE 1, 3);
- IRCC's page on changing employers (CA C6);
- the PIB release on the Labour Codes (India 1i);
- Naukri's job-posting guide (India 1a).

Some pages block scripted reads, so they were read in a browser; each section says which. The MOHRE
pages were read from March 2026 archive copies because mohre.gov.ae refused connections: re-check
them live before release.

| Group | Rows | Verified | Contested | Not found |
|---|---|---|---|---|
| Canada and Australia | 40 | 36 | 2 | 2 |
| United Arab Emirates | 32 | 25 | 6 | 1 |
| Europe: citizenship, CEFR, pay | 34 | 24 | 6 | 4 |
| India | 19 | 12 | 4 | 3 |
| **All** | **125** | **97** | **18** | **10** |

## What the sources change in the design

Each change below is proposed for Phase 3; the owner reviews them in Task 2.2. Nothing is built
from a contested or not-found row: each one is resolved by cutting what rests on it (see the next
section).

**Answers from citizenship** (design §1, "Derived answers")
1. EU, EEA and Swiss citizens in Germany, the Netherlands and Ireland: **verified**, with no
   transitional limits in force. The list is the EU 27, plus Iceland, Liechtenstein and Norway (EEA),
   plus Switzerland (the EU–Swiss free movement agreement, in force since 2002). Europe 1–7.
2. "A UK citizen: the same in Ireland" becomes **a British citizen**: that is the memorandum's
   wording (paragraph 8). Other British nationality classes, such as British National (Overseas),
   are not shown to be covered. Proposal: the citizenship choice for `GB` reads "British citizen".
   The memorandum is not legally binding (paragraph 17); Ireland's own statute was not checked.
   Europe 8.
3. An Irish citizen in the UK: **verified** in statute (Immigration Act 1971 s.3ZA). Europe 9.
4. A British citizen in Germany or the Netherlands is **never derived**. The Withdrawal Agreement
   exception turns on residence before 2021, which citizenship cannot show. This confirms the
   design. Europe 10–12.
5. **New, verified rule:** GCC nationals in the UAE. "Treated as UAE nationals in all employment
   procedures" and they need no residence visa. So citizens of Bahrain, Kuwait, Oman, Qatar and
   Saudi Arabia are derived as authorized in the UAE, with no sponsorship. UAE 5.

**Each country's status list** (design §1, `work_status`)
6. Canada: the list in its section, with 11 choices: citizen, permanent resident, open work permit,
   post-graduation work permit, IEC Working Holiday, employer-specific work permit, study permit,
   maintained status, exempt from a work permit, visitor or no status, other. CA C1–C20.
7. Australia: Home Affairs has **no "temporary visa with full / limited work rights" category**.
   Only citizens, permanent residents and New Zealand citizens on a subclass 444 visa have no work
   conditions. The list uses named visas instead: Skills in Demand (482, which replaced TSS on
   7 Dec 2024), Temporary Graduate (485), Student (500), Working Holiday (417/462), bridging visa,
   other temporary visa, visitor. AU A1–A12.
8. UAE: the draft list changes.
   - Golden and Green visas become **two choices**: different terms, and only Golden has its own
     MOHRE permit.
   - **Freelance permit is cut.** It is a work permit, not a residence status, and its holder "is,
     in no way, an employee".
   - **Added:** student visa, virtual (remote) work visa, and other residence.
   - "Employment visa" is yes only for the current sponsor.

   UAE 1–22.
9. **The UAE meaning of "authorized to work".** Every private-sector hire, Emiratis included, needs
   a MOHRE work permit, and the employer files it. A literal "needs no employer action" is never
   true there. Proposal: in the UAE, authorized means **can take the job without the employer
   sponsoring a residence visa**. It is the only reading under which an Emirati answers Yes, which
   the citizenship rule already gives. UAE 1, 4–6.
10. **A status never fills the Yes/No answers.** Many statuses are "yes, with a limit": a study
    permit's hours, a single employer, six months per employer. Collapsing them to Yes or No would
    be a guess. The status is stored and filled where a form asks for it; the three Yes/No answers
    stay the user's, and only citizenship derives them, as designed. No new "work limit" field.
11. **The expiry date is asked only for statuses that have one.** It is not asked for a New Zealand
    citizen in Australia, Canadian maintained status, or UAE and GCC nationals. Each status in the
    data says whether it has an expiry. CA C18, AU A3, UAE 4–5.
12. **Canada's sponsorship wording.** IRCC never says "sponsor" for work permits. The equivalent is
    needing an employer-specific permit, through an LMIA or an LMIA-exempt offer of employment.
    Canada's two sponsorship questions get a hint that says so. CA C3–C9.

**Address** (design phase 2 item; `markets.yaml` `asks_state`)
13. UAE: the Emirate line is **required** (7 emirates). Google's format has **no postcode and no
    city line**. So `AE` gets `asks_state: true` with the label "Emirate". The Contact "Postal code"
    answer becomes per country, like "State", so readiness does not count it for a UAE home. City
    stays, because forms ask it. UAE 23–24.

**Pay** (design: the `pay_terms` pack)
14. Australia: SEEK asks candidates for base pay **excluding super**, and ads use both "+ super" and
    "package including super". Expected pay is therefore stored as base excluding super, and the
    fill converts only when a form says "package". The Superannuation Guarantee is 12%. AU A13–A18.
15. Netherlands: expected pay is **gross per month, excluding the 8% holiday allowance**, not gross
    annual; the IND and Dutch job boards both use monthly gross. An annual figure is never converted
    silently. Europe 25–28.
16. Germany: gross annual is **verified**. Europe 23.
17. UAE: the basic + housing + transport split appears in **offer letters, not in application
    forms**. Housing and transport can also be given in kind or folded into pay. The UAE asks one
    figure: **expected total monthly salary in AED**. The split is cut. Salaries carry no income
    tax. UAE 25–32.
18. India: current and expected CTC are **annual amounts, stored in rupees** and converted to lakhs
    per annum where a form asks for that. Current CTC is optional, since boards let you leave it
    out. The fixed/variable split is cut: only one board asks it. No Indian law defines CTC. India
    1a–1i.
19. **Current pay reaches Indian forms only.** The EU Pay Transparency Directive bars employers from
    asking about current or past pay. Germany, the Netherlands and Ireland had not transposed it on
    2026-10-30; the Netherlands targets 1 Jan 2027. So current CTC is an India per-country answer,
    never one that every country's form reads. Europe 29–34.

**India's other answers** (design: the `india_basics` pack)
20. Experience: **total experience in years and months**. "Relevant experience" is not a stored
    answer anywhere; employers ask it per job, so the Companion asks it at fill time. India 3a–3b.
21. Notice: forms offer fixed buckets (15 days or less, 1, 2 or 3 months, more than 3). Notice is
    **stored in days and rounded up** to the form's bucket, never down, because claiming a shorter
    notice is a knockout misstatement.
    - "Serving notice" (Yes/No) and the last working day (a date) are kept.
    - Once that date has passed, the serving answer shows as out of date.

    India 2a–2d.
22. Current location (one city) and preferred locations (a list, up to 10): **verified**. India
    4a–4b.

**Languages** (design: the `cefr` pack)
23. CEFR is A1–C2, grouped as Basic, Independent and Proficient user (the Council of Europe). Each
    language gets **a CEFR level, beside today's separate "Native speaker" answer**, which stays
    separate: C2 is not native.
    - German and Dutch forms often use a verbal scale ("fließend", "vloeiend") with no standard
      mapping to CEFR.
    - The fill picks the nearest option and flags it for review.
    - A verbal answer never sets a stored CEFR level.

    Europe 14–22.

## Contested and not-found rows

None of them is built on:
- **Cut with the choice that needed them:**
  - CA C11 (graduates awaiting a permit: covered by "other");
  - AU A11 (full work rights);
  - UAE 7 (the no-objection certificate) and UAE 29–30 and 32 (the pay split);
  - India 1d (fixed/variable) and 3b (relevant experience).
- **Answered by the user, never filled for them:**
  - UAE 14, 19 and 20 (Green permit type, student and virtual work visas);
  - AU A19–A20 (Australian right-to-work wording: Australia keeps the generic permit wording).
- **Handled at fill time:**
  - India 1c (the unit: stored in rupees, converted per form) and 2a (the bucket set: round up);
  - Europe 20 and 22 (the verbal language scales: nearest option, flagged);
  - Europe 27 (Dutch annual figures: never converted silently).
- **Not used by any question:**
  - India 1g (no legal definition of CTC: the user's figure is stored), 2e and 2f;
  - Europe 16 (legacy CEFR names), 17, 19, 21 and 24;
  - Europe 28 (the Dutch 13th month: stored pay is monthly, excluding extras).
- **Re-check later:** Europe 13 (Switzerland). The rule rests on the treaty being in force, which is
  verified; the June 2026 vote is reported only by secondary sources.

## Facts that will go stale

Each needs a re-check before a release that ships its country:
- the Australian Superannuation Guarantee rate and Skills in Demand thresholds (indexed each July);
- Canada's study-permit hours;
- the UAE Labour Law amendments and the MOHRE service pages;
- the EU Pay Transparency Directive's transposition in DE, NL and IE;
- the job-board form scripts cited for India (their URLs carry build hashes).

---

## Canada and Australia

Research date: 2026-10-30. Every row was read on the page named in Source. The "Checked" column gives the page's own date: canada.ca "Page details" date, immi.homeaffairs.gov.au "Last updated", ATO "Last updated", Justice Laws "current to".
Home Affairs and the ATO block the plain fetch tool, so those pages were read in a real browser. Nothing was taken from a blog, law firm or migration agent. Those sites were used only to find the government page.

| # | Fact | Finding | Source | Checked | Status |
|---|---|---|---|---|---|
| C1 | CA citizen: right to work | Charter s.6(2)(b): every citizen and every permanent resident has the right "to pursue the gaining of a livelihood in any province". | https://laws-lois.justice.gc.ca/eng/const/page-12.html | 2026-10-30 | verified |
| C2 | CA permanent resident | PRs "can live, work or study anywhere in Canada". They cannot vote and cannot hold some jobs that need a high-level security clearance. | https://www.canada.ca/en/immigration-refugees-citizenship/services/new-immigrants/pr-card/understand-pr-status.html | 2026-10-30 (page 2026-04-09) | verified |
| C3 | CA work permit types | There are two types. **Employer-specific** ("Most common"): "You need a job offer", and the employer "may need a labour market impact assessment (LMIA)". **Open** ("For special circumstances"): no job offer, "work for most compliant employers", "only eligible in certain situations". | https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/permit/temporary/need-permit.html | 2026-10-30 (page 2026-05-25) | verified |
| C4 | CA open work permit | You can work for any employer except those on the non-compliant list or in the sex-trade businesses the page names. The employer files no LMIA, no offer of employment and no compliance fee. The permit may still limit the type of work or the location. Eligible groups: PGWP applicants; IEC Working Holiday; destitute students; family members of PR applicants and of work-permit holders; spouses of international students; sponsored family members; refugees, asylum claimants and protected persons; victims of workplace abuse; people in crisis; Indigenous Peoples; PR applicants; temporary resident permit holders; Quebec investors. Hong Kong graduates is marked Closed. | https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/open-work-permit.html | 2026-10-30 (page 2026-03-31) | verified |
| C5 | CA employer-specific work permit | It "lets you work in Canada under the conditions of the permit until the expiry date". The permit names the employer, location and occupation. "Most jobs need an LMIA." The employer must find out whether the job needs an LMIA or is LMIA-exempt. | https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/employer-specific.html | 2026-10-30 (page 2026-03-31) | verified |
| C6 | CA changing employer | An employer-specific permit holder "must apply for a new work permit, if you're eligible" to change jobs or employers. "Open work permit holders can change employers at any time while their work permit is valid." IEC participants must first check whether they can change employers. | https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/extend/change-jobs-employers.html | 2026-10-30 (page 2026-10-08) | verified |
| C7 | CA LMIA, the main "sponsorship" route | An LMIA "is a document that an employer in Canada may need to get before hiring a foreign worker". A positive LMIA shows a foreign worker is needed. "Once an employer gets the LMIA, the worker can apply for a work permit." | https://ircc.canada.ca/english/helpcentre/answer.asp?qnum=163 | 2026-10-30 (modified 2026-09-28) | verified |
| C8 | CA LMIA-exempt route (International Mobility Program) | "In most cases" the employer pays a $230 employer compliance fee and submits an offer of employment through the Employer Portal. A worker who already holds an open work permit needs neither. The page also flags a Quebec-only LMIA exemption for extensions "Starting March 13, 2026". | https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/hire-temporary-foreign/international-mobility-program/how-to-hire.html | 2026-10-30 (page 2026-04-23) | verified |
| C9 | CA "needs sponsorship" equivalent | Canada's version of "needs employer sponsorship" is needing an **employer-specific work permit**. The new employer gives a job offer plus either a positive LMIA (C7) or an LMIA-exempt offer of employment with the fee (C8). Changing employer means a new permit (C6). The IRCC work-permit pages read for this research do not use the word "sponsor" for this. | C3, C5, C6, C7, C8 | 2026-10-30 | verified (built from five pages) |
| C10 | CA PGWP | IRCC lists PGWP applicants among the groups eligible for an **open** work permit (C4). "You can't get a PGWP if you already had one after completing an earlier program of study." Extensions are on paper and only where the permit was cut short by passport validity. | https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/work/after-graduation/about.html | 2026-10-30 (page 2026-03-09) | verified |
| C11 | CA graduate waiting on a work permit | The work-without-a-permit page lists "recent graduates who have applied for a work permit" as people who may not need a permit. I did not read the conditions behind this (IRPR R186(w)). | https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/work-without-permit.html | 2026-10-30 (page 2026-05-25) | contested (listed, conditions not read) |
| C12 | CA study permit: off-campus hours | "You can work up to 24 hours per week" off campus during regular academic sessions, and unlimited hours during scheduled breaks. Conditions: full-time at a DLI, program started, post-secondary program of at least 6 months leading to a credential, valid permit (or extension applied for), work conditions printed on the permit, and a SIN. | https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/work/work-off-campus.html | 2026-10-30 (page 2026-04-15) | verified |
| C13 | CA study permit: start date of the 24-hour rule | "Starting November 8, 2024", eligible students may work part time, up to 24 hours a week, during a session and full time in scheduled breaks. Students "must stop working off campus as soon as their full-time status becomes part-time". The authority is IRPR R186(v). | https://www.canada.ca/en/immigration-refugees-citizenship/corporate/publications-manuals/operational-bulletins-manuals/temporary-residents/study-permits/campus-work.html | 2026-10-30 (page 2025-04-23) | verified |
| C14 | CA co-op placements (2026 change) | "As of April 1, 2026, eligible post-secondary international students no longer need a separate work permit" for required work placements such as co-ops and internships. | https://www.canada.ca/en/immigration-refugees-citizenship/news/notices/simplifying-co-op-work-permit-requirement-post-secondary-international-students.html | 2026-10-30 (page 2026-04-09) | verified |
| C15 | CA International Experience Canada | **Working Holiday** gives an open work permit. **Young Professionals** and **International Co-op (Internship)** give employer-specific permits, and both need a job offer. | https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/iec/about.html | 2026-10-30 (page 2026-10-23) | verified |
| C16 | CA IEC is LMIA-exempt | IEC permits are exempt from the LMIA under IRPR R204(d), exemption code C21. This covers the employer-specific categories too. | https://www.canada.ca/en/immigration-refugees-citizenship/corporate/publications-manuals/operational-bulletins-manuals/temporary-residents/foreign-workers/exemption-codes/international-experience.html | 2026-10-30 (page 2025-12-24) | verified |
| C17 | CA IEC season status | Ages 18 to 35 (18 to 30 in some countries). "The pools for the 2026 season are closed." The 2027 season has not opened. | https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/iec.html | 2026-10-30 (page 2026-10-21) | verified |
| C18 | CA maintained status | Someone who applied to extend before the permit expired is authorized to keep working "under the same conditions as your original work permit". The letter runs 365 days, and the person can keep working past it until a decision. It does not apply to a first work permit, to an application made after expiry, or to TRP applicants. | https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/extend/after-apply.html | 2026-10-30 (page 2026-10-14) | verified |
| C19 | CA working without a permit | "Most foreign nationals need a work permit to work in Canada. Some workers, such as business visitors, foreign representatives and military personnel, are exempt." The page also lists full-time study-permit holders working on or off campus. | https://www.canada.ca/en/immigration-refugees-citizenship/services/work-canada/work-without-permit.html | 2026-10-30 (page 2026-05-25) | verified |
| C20 | CA visitor / no status | IRPR 183(1)(b): every temporary resident must "not work, unless authorized by this Part or Part 11". | https://laws-lois.justice.gc.ca/eng/regulations/SOR-2002-227/section-183.html | 2026-10-30 (current to 2026-09-30, last amended 2026-07-15) | verified |
| A1 | AU who has no work conditions | "Only Australian citizens, permanent residents and New Zealand citizens holding Special Category (subclass 444) visas have no conditions placed on working in Australia. Other visas carry conditions." Conditions can limit the type of work, the hours, or the job. Workers check them in VEVO. | https://immi.homeaffairs.gov.au/visas/working-in-australia/work-rights-and-exploitation/work-restrictions | 2026-10-30 (updated 4 May 2026) | verified |
| A2 | AU visitor | "A Visitor visa or Electronic Travel Authority (ETA) does not allow you to work in Australia." | same as A1 | 2026-10-30 (updated 4 May 2026) | verified |
| A3 | AU NZ citizen (subclass 444) | This is a temporary visa to "visit, study, stay, and work" for a New Zealand citizen who meets the criteria. It is usually applied for at each entry and is free. The holder can stay "for as long as you are a New Zealand citizen". "When you leave Australia your visa will cease", so a new one is needed on each entry. The holder must keep meeting the character requirements. | https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/special-category-visa-subclass-444 | 2026-10-30 (updated 8 Sep 2026) | verified |
| A4 | AU employer-sponsored visa: current name | **Skills in Demand visa (subclass 482)**. It "lets an employer sponsor a suitably skilled worker". Basic eligibility: "Have an approved sponsor and be nominated for the visa". Streams: Core Skills, Specialist Skills, Labour Agreement, plus Subsequent entrant for family. Stay is up to 4 years, or 5 for Hong Kong passport holders. Income thresholds were indexed from 1 July 2026. | https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skills-in-demand-visa-subclass-482 | 2026-10-30 (updated 27 Oct 2026) | verified |
| A5 | AU SID replaced TSS | "On December 7 2024, the Skills in Demand (SID) visa replaced the Temporary Skills Shortage (TSS) visa." TSS is listed under Repealed Visas. | https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/repealed-visas/temporary-skill-shortage-medium-term-visa-subclass-482 | 2026-10-30 (updated 7 Dec 2024) | verified |
| A6 | AU SID work condition | The holder must "work only for your sponsor or associated entity, unless you are exempt". After a layoff: "you have up to 180 days to find a new employer or make arrangements to leave Australia". The holder can apply for permanent residence if eligible. | https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skills-in-demand-visa-subclass-482/core-skills-stream | 2026-10-30 (updated 12 Oct 2026) | verified |
| A7 | AU Student visa (500): hours | "work up to 48 hours a fortnight when your course of study or training is in session". "student visa holders can work unlimited hours when their course is not in session". Students in a master's by research or a doctoral degree, and their families, have no work limit. | https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/student-500 | 2026-10-30 (updated 22 Oct 2026) | verified |
| A8 | AU Working Holiday (417): per-employer limit | "You can do any kind of work on this visa. Usually, you can only work for the same employer for 6 months." | https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/work-holiday-417/first-working-holiday-417 | 2026-10-30 (updated 23 Sep 2026) | verified |
| A9 | AU Work and Holiday (462): per-employer limit | Same wording as 417: any kind of work, and "Usually, you can only work for the same employer for 6 months." | https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/work-holiday-462/first-work-holiday-462 | 2026-10-30 (updated 23 Sep 2026) | verified |
| A10 | AU Temporary Graduate (485) | It "allows international students to live, study and work after you have finished your studies". Current streams: **Post-Vocational Education Work** (up to 18 months) and **Post-Higher Education Work** (usually 2 to 3 years). The page says "You can work in Australia" and states no hour or employer limit. | https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/temporary-graduate-485 | 2026-10-30 (updated 14 Dec 2024) | verified |
| A11 | AU "temporary visa with full work rights" as a category | Home Affairs has no such category. A1 says only citizens, PRs and 444 holders have no work conditions, and every other visa "carry conditions" that the holder checks in VEVO. "Full work rights" is job-form wording, not a government term. I did not find a job board or ATS document that defines it. | A1; searched SEEK and SEEK Pass help, Home Affairs | 2026-10-30 | contested |
| A12 | AU Bridging visa A | "You might be allowed to work in Australia depending on the visa conditions that apply to your BVA. Your grant letter will tell you about these conditions." While the substantive visa is in effect, its conditions apply. | https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/bridging-visa-a-010 | 2026-10-30 (updated 23 Sep 2024) | verified |
| A13 | AU Superannuation Guarantee rate | General SG is **12.00%** for 1 Jul 2025 to 30 Jun 2026, **12.00%** for 1 Jul 2026 to 30 Jun 2027, and **12.00%** "1 July 2027 onwards". It was 11.50% in 2024–25. Norfolk Island has its own transitional rates. | https://www.ato.gov.au/tax-rates-and-codes/key-superannuation-rates-and-thresholds/super-guarantee | 2026-10-30 (updated 17 Apr 2026, QC18123) | verified |
| A14 | AU Payday Super (2026 change) | "From 1 July 2026 the minimum super guarantee is calculated as a percentage of each eligible employee's qualifying earnings", paid each payday. Before that it was a percentage of ordinary time earnings, paid quarterly. The 2026–27 maximum contribution base is $270,830 a year. | same as A13 | 2026-10-30 (updated 17 Apr 2026) | verified |
| A15 | AU pay-ad convention, job board 1 (SEEK, employer guidance) | The structured pay range indexes the ad for search and "is not automatically shown on your ad". What candidates see is the free-text "Pay shown on your ad" box, up to 50 characters. SEEK's own examples are "$75,000 + Super + Salary packaging" and "$76k-$83k + super \| 9 day fortnight \| hybrid". | https://au.employer.seek.com/hiring-advice/article/why-its-important-to-include-salary-in-your-job-ad | 2026-10-30 (no article date; footer 2026) | verified |
| A16 | AU pay-ad convention, SEEK API for ATS vendors | Pay types: Hourly rate, Monthly salary, Annual salary, Annual plus commission. "the monetary values in minimumAmount and maximumAmount are not visible in search results nor on the job ad". Super goes in the 50-character description, for example "$100k–$120k + super + bonus". The structured range has **no field** for whether super is included. | https://developer.seek.com/use-cases/job-posting/salary | 2026-10-30 (no date on page) | verified |
| A17 | AU candidate side (SEEK profile) | SEEK tells candidates to set their profile minimum as "The base salary amount which excludes bonuses and super." | https://help.au.seek.com/article/What-Minimum-Salary-requirement-should-I-select-for-my-SEEK-profile | 2026-10-30 (updated 14/4/2026) | verified |
| A18 | AU pay-ad convention, job board 2 (Indeed Australia) | The guide describes two styles. Some businesses "pay tax-exempt payments on top of the quoted salary" ("salary plus superannuation"). Others "offer their employees a salary package" and "deduct ... superannuation contributions from the quoted salary package amount". Its example: "Salary package: $60,000 including superannuation". The guide's 10.5% SG figure is out of date; see A13. | https://au.indeed.com/career-advice/pay-salary/how-to-calculate-take-home-pay | 2026-10-30 (updated 13 Nov 2025) | verified (stale rate noted) |
| A19 | SEEK's own note on whether advertised salaries include super | A search snippet says SEEK's salary-index methodology PDF flags super as unknown in hirer-entered ranges. The PDF returned 404, so this is unconfirmed. | https://au.seek.com/about/files/About%20the%20SEEK%20ASI.pdf (404) | 2026-10-30 | not found |
| A20 | AU right-to-work question as job forms ask it | I could not find a job-board or ATS document listing the standard Australian right-to-work answer options. Searched: SEEK help, SEEK Pass help, SEEK employer advice, and the exact phrase of SEEK's screening question. | n/a | 2026-10-30 | not found |

Counts: 36 verified (19 Canada, 17 Australia), 2 contested (C11, A11), 2 not found (A19, A20).

### Proposed data

The values are strings so that "depends" is legal next to "Yes" and "No". Each `why` gives the source row that settles the value, or says why it is "depends".

```yaml
CA:
  work_status:
    - key: citizen
      label: Canadian citizen
      authorized_now: "Yes"        # C1
      sponsorship_now: "No"        # C1: right to work, no permit
      sponsorship_future: "No"
    - key: permanent_resident
      label: Permanent resident
      authorized_now: "Yes"        # C2 "work ... anywhere in Canada"
      sponsorship_now: "No"
      sponsorship_future: "No"
    - key: open_work_permit
      label: Open work permit
      authorized_now: "Yes"        # C4 any employer except non-compliant list; may limit occupation/location
      sponsorship_now: "No"        # C4/C8 employer files no LMIA, no offer, no fee
      sponsorship_future: depends  # open permits expire; what comes next (PR, another open permit, employer-specific) is personal
    - key: post_graduation_work_permit
      label: Post-graduation work permit (PGWP)
      authorized_now: "Yes"        # C4 (open work permit), C10
      sponsorship_now: "No"        # open permit
      sponsorship_future: depends  # C10: one PGWP per person, never renewed as a PGWP; next basis not settled by source
    - key: iec_working_holiday
      label: International Experience Canada – Working Holiday
      authorized_now: "Yes"        # C15 open work permit
      sponsorship_now: "No"
      sponsorship_future: depends  # time-limited participation; next basis not settled
    - key: employer_specific_work_permit
      label: Employer-specific work permit   # IEC Young Professionals / International Co-op also land here (C15, C16)
      authorized_now: depends      # C5: yes, but only for the employer, occupation and location on the permit
      sponsorship_now: "Yes"       # C6: any other employer means a new permit; C7/C8: LMIA or LMIA-exempt offer of employment
      sponsorship_future: depends  # could stay employer-tied or move to PR/open permit; not settled
    - key: study_permit
      label: Study permit (off-campus work up to 24 hours a week during sessions)
      authorized_now: depends      # C12/C13: only if eligible and the permit carries work conditions; 24 h/week in session, unlimited in scheduled breaks; stops if part-time
      sponsorship_now: depends     # a full-time job beyond 24 h/week in session would need another basis; not settled
      sponsorship_future: depends
    - key: maintained_status
      label: Maintained status (applied to extend before my permit expired)
      authorized_now: depends      # C18: yes, but only "under the same conditions" as the expired permit
      sponsorship_now: depends     # inherits the underlying permit's answer
      sponsorship_future: depends
    - key: work_permit_exempt
      label: Authorized to work without a work permit   # e.g. business visitor, foreign representative (C19)
      authorized_now: depends      # C19: only for the exempt activity
      sponsorship_now: depends
      sponsorship_future: depends
    - key: visitor_or_no_status
      label: Visitor / no work authorization
      authorized_now: "No"         # C20 IRPR 183(1)(b)
      sponsorship_now: depends     # employer-specific route needs one (C9), but the person may qualify for an open permit (C4); not settled
      sponsorship_future: depends
    - key: other
      label: Other status
      authorized_now: depends
      sponsorship_now: depends
      sponsorship_future: depends

AU:
  work_status:
    - key: citizen
      label: Australian citizen
      authorized_now: "Yes"        # A1 no work conditions
      sponsorship_now: "No"
      sponsorship_future: "No"
    - key: permanent_resident
      label: Australian permanent resident
      authorized_now: "Yes"        # A1
      sponsorship_now: "No"
      sponsorship_future: "No"
    - key: nz_citizen_special_category
      label: New Zealand citizen (Special Category visa, subclass 444)
      authorized_now: "Yes"        # A1, A3
      sponsorship_now: "No"        # A1: no work conditions
      sponsorship_future: "No"     # A3: holds for as long as the person is an NZ citizen (re-granted each entry, subject to character)
    - key: skills_in_demand_482
      label: Skills in Demand visa (subclass 482)
      authorized_now: depends      # A6: yes, but only for the sponsor or an associated entity, unless exempt
      sponsorship_now: "Yes"       # A4 + A6: any other employer must be an approved sponsor and nominate
      sponsorship_future: depends  # A6: may apply for permanent residence if eligible; not settled
    - key: temporary_graduate_485
      label: Temporary Graduate visa (subclass 485)
      authorized_now: "Yes"        # A10 "You can work in Australia"
      sponsorship_now: depends     # A10 lists no employer limit, but A1 says all visas other than citizen/PR/444 carry conditions; check VEVO
      sponsorship_future: depends  # visa is time-limited (18 months to ~3 years)
    - key: student_500
      label: Student visa (subclass 500)
      authorized_now: depends      # A7: yes, max 48 h/fortnight in session, unlimited out of session; research master's/doctoral no limit
      sponsorship_now: depends
      sponsorship_future: depends
    - key: working_holiday
      label: Working Holiday (subclass 417) or Work and Holiday (subclass 462) visa
      authorized_now: depends      # A8/A9: any kind of work, but usually max 6 months with one employer
      sponsorship_now: depends     # a role longer than 6 months with one employer needs permission or another visa; not settled
      sponsorship_future: depends
    - key: bridging_visa
      label: Bridging visa
      authorized_now: depends      # A12: work rights depend on the BVA's grant conditions (or the substantive visa's while in effect)
      sponsorship_now: depends
      sponsorship_future: depends
    - key: other_temporary_visa
      label: Other temporary visa
      authorized_now: depends      # A1: every other visa carries conditions; VEVO shows them
      sponsorship_now: depends
      sponsorship_future: depends
    - key: visitor
      label: Visitor visa or ETA
      authorized_now: "No"         # A2
      sponsorship_now: depends     # not settled: depends on which visa the person could move to
      sponsorship_future: depends

  pay:
    super_guarantee_rate: 0.12     # A13, 1 July 2025 onward; scheduled 12.00 for 2026-27 and 2027 onward
    super_basis_from_2026_07_01: qualifying_earnings   # A14 (was ordinary time earnings)
    pay_expectation_basis: base_excluding_super        # A17: SEEK profile minimum = base excl. bonuses and super
    ad_conventions:                # A15, A16, A18; neither SEEK's range nor its API marks which convention an ad uses
      - base_plus_super            # "$X + super"
      - package_including_super    # "$X package including super"
```

### Notes

1. **A binary `authorized_now` cannot hold the most common non-citizen answers.** Five statuses are "yes, with a limit": CA study permit (24 h/week), CA employer-specific permit (one employer), AU student (48 h/fortnight), AU working holiday (usually 6 months per employer) and AU SID (sponsor only). Collapsing these to Yes or No is either a guess or a false answer. Two options fit the never-guess rule:
   - Add a `work_limit` field per status, for example `hours_per_week` / `hours_per_fortnight` / `single_employer` / `max_months_per_employer`.
   - Leave `authorized_now` unknown for these statuses and let the user answer.

   Either way, "depends" in the YAML must never be auto-filled.
2. **For employer-tied statuses, `sponsorship_now` means something different.** On a CA employer-specific permit or an AU SID visa, the person is authorized today, but only for the current employer. A form from a *different* employer is really asking "will we have to act?", and the sources say yes (C6, A4/A6). The US list mixes these two ideas (`h1b` is authorized now and needs sponsorship). The CA and AU lists keep the same pattern deliberately.
3. **Canada has no "sponsorship" step for work permits.** The employer-side act is a positive LMIA (C7) or, for LMIA-exempt roles, an offer of employment through the Employer Portal plus a $230 fee "in most cases" (C8). A Canadian form that says "sponsorship" means this. The app's help text should say so instead of borrowing US wording.
4. **The PGWP is just an open work permit.** It answers exactly like `open_work_permit` today (C4). It is listed separately for three reasons: people know it by name, it is once-only (C10), and its expiry date matters. If the list must stay short, merge it into `open_work_permit`.
5. **IEC is three different permits, not one status.** Working Holiday is open. Young Professionals and International Co-op are employer-specific but LMIA-exempt (C15, C16). The list therefore has `iec_working_holiday`, and the other two use `employer_specific_work_permit`. The 2026 IEC pools are closed (C17).
6. **2026 changes to keep current:**
   - CA co-op placements no longer need a separate permit for eligible post-secondary students, from 1 Apr 2026 (C14).
   - AU SID income thresholds were indexed from 1 Jul 2026 (A4).
   - Payday Super started on 1 Jul 2026. SG is now a percentage of "qualifying earnings", not ordinary time earnings (A14).
   - The AU 485 stream names changed to Post-Vocational Education Work and Post-Higher Education Work (A10).
   - The CA 24 h/week limit has been in force since 8 Nov 2024 (C13) and still stands on the page updated 2026-04-15 (C12).
7. **`authorization_expires_on` does not fit some statuses:**
   - AU subclass 444 has no expiry date. It ceases when the holder leaves Australia and is granted again on entry (A3).
   - CA maintained status runs until IRCC decides, not to a fixed date (C18).
   - Both should store "none / not applicable", not an empty date.
8. **"Full work rights" is not a government term (A11).** Home Affairs says only citizens, PRs and 444 holders have no work conditions. Every other visa, including the 485, carries conditions shown in VEVO. If the app wants a generic "temporary visa, no work limits" key for AU forms, its label must come from a cited job-form source. I could not find one (A20). The proposed list uses named visas plus `other_temporary_visa`.
9. **Pay including super:**
   - On SEEK, both the hirer's structured range and its API have no "includes super" field. The super convention lives only in the ad's free text, for example "+ super" (A15, A16).
   - SEEK asks candidates to state their minimum as base *excluding* super (A17).
   - Indeed Australia describes both "salary plus superannuation" and "salary package ... including superannuation" (A18).
   - So the app should store an AU pay expectation as base excluding super, and convert only when an ad's text clearly says "package" or "including super": base = package / 1.12 at the current rate (A13).
   - It should never infer the convention from an ad that gives a bare number.
   - From 1 Jul 2026, SG is calculated on qualifying earnings, so "base × 12%" is an approximation, not the legal amount (A14).
10. **Out of scope or not checked:**
    - CA on-campus work rules beyond "may not need a work permit" (C19).
    - The conditions behind R186(w) for graduates waiting on a PGWP (C11).
    - AU partner and other temporary visas.
    - Whether the 485 carries any work condition in VEVO.
    - How Australian job forms word the right-to-work question (A20).

---

## United Arab Emirates

Access notes: u.ae, icp.gov.ae, tax.gov.ae and Google's address data were read live on 2026-10-30. uaelegislation.gov.ae (the official legislation portal) blocks scripted fetches and was read in a real browser. mohre.gov.ae refused every connection on 2026-10-30 (connection refused or timeouts from fetch, curl and the browser), so the MOHRE service pages were read from Wayback Machine copies of the MOHRE URL. The snapshot date is given in each row; re-check them live before shipping.

### 1. Residence and work statuses

| # | Fact | Finding | Source | Checked | Status |
|---|---|---|---|---|---|
| 1 | Who may work, and the permit rule | Decree-Law 33/2021 Art. 6(1): no one may work in the State, and no employer may recruit or employ a worker, until the Ministry (MOHRE) has issued a work permit. u.ae: it is "illegal for a person to work in the UAE without a valid work permit". The permit belongs to the employer: the "Worker" is defined as a person "authorised by the Ministry" to work for a licensed establishment (Art. 1). | https://uaelegislation.gov.ae/en/legislations/1541 (Art. 1, Art. 6) ; https://u.ae/en/information-and-services/jobs/Sector-of-employment/employment-in-the-private-sector/work-permits | 2026-10-30; law page "last update listed 29 Jul 2024", 3 amendments; u.ae updated 19 Oct 2026 | verified |
| 2 | Scope of the labour law | Art. 3: the law covers private-sector establishments, employers and workers. It does not cover federal or local government employees, the armed forces, police and security, or domestic workers. Government jobs and domestic work follow other rules, not researched here. | https://uaelegislation.gov.ae/en/legislations/1541 (Art. 3) | 2026-10-30; last update 29 Jul 2024 | verified |
| 3 | MOHRE work permit types | The Executive Regulation (Cabinet Resolution 1/2022, Art. 6(1)) lists 12 types, (a) to (l): (a) recruitment from outside the State; (b) transfer, for a non-national moving between establishments; (c) for those sponsored by their parents, which u.ae and MOHRE call "family sponsorship" / "Dependents Sponsored by Family Members"; (d) temporary; (e) mission; (f) part-time; (g) juvenile, age 15 to 18; (h) training and student employment; (i) national / GCC citizens; (j) holders of golden residency; (k) national trainee; (l) freelance. u.ae lists 13 because it adds the private teacher permit. Several are valid for 2 years: transfer, family sponsorship, golden, UAE/GCC national, and recruitment from abroad. | https://uaelegislation.gov.ae/en/legislations/1547 (Art. 6) ; https://u.ae/en/information-and-services/jobs/Sector-of-employment/employment-in-the-private-sector/work-permits | 2026-10-30; regulation "last update listed 03 Feb 2022"; u.ae 19 Oct 2026 | verified (12 in the regulation, 13 on u.ae) |
| 4 | Emirati citizen | Employers hiring Emiratis "obtain a UAE national work permit from MoHRE" (u.ae). That is regulation type (i). No visa is involved. **Implies:** authorized_now = Yes (needs no visa), sponsorship = No. The employer still files the national work permit (row 1). | https://u.ae/en/information-and-services/jobs/Sector-of-employment/employment-in-the-private-sector/emiratis-employment-in-private-sector ; regulation Art. 6(1)(i) | 2026-10-30; u.ae updated 15 Oct 2026 | verified |
| 5 | GCC national | GCC nationals in the private sector are "treated as UAE nationals in terms of all employment procedures" (Cabinet Resolution 72/5 of 2007). The employer obtains a MOHRE work permit (Cabinet Resolution 292 of 2015), and the worker "may commence work immediately in the UAE, without the need to obtain a residence visa". GCC citizens need no visa to enter. **Implies:** authorized_now = Yes, sponsorship = No. The employer files the national/GCC permit. GCC hires do not count toward Emiratisation quotas. | https://u.ae/en/information-and-services/jobs/Sector-of-employment/employment-in-the-private-sector/gcc-nationals-working-in-the-private-sector ; https://u.ae/en/information-and-services/visa-and-emirates-id/Visa-information/do-you-need-an-entry-permit-or-a-visa-to-enter-the-uae | 2026-10-30; u.ae 15 Oct 2026 / 13 Jul 2026 | verified |
| 6 | Employment (work) residence visa | "The employer must apply for the standard work visa", which is for government and private-sector employees. A "normal employment visa" is valid for 2 years and can be renewed. The visa is tied to the employer that sponsors it. **Implies:** authorized_now = **depends**: Yes for the current sponsoring employer, but a new private employer must obtain a transfer work permit (row 3 (b)) and apply for the work visa. sponsorship (for a new employer) = Yes. | https://u.ae/en/information-and-services/visa-and-emirates-id/Types-of-visas/residence-visa-for-working-in-the-uae | 2026-10-30; updated 07 Aug 2026 | verified (rule); implication derived |
| 7 | Changing employers: is a no-objection certificate (NOC) needed? | Art. 49: when a contract ends under the law, the worker may move to another employer under conditions set by the Executive Regulation. Regulation Art. 27 sets those conditions: the contract term expired without renewal, or the contract was ended under Arts. 42/45. Neither text mentions the first employer's consent. MOHRE's transfer-permit conditions (no active work permit; apply within 90 days of the previous permit's cancellation; an official job offer signed by both parties) list no NOC or consent. **No primary page says in words that an NOC is not required.** That reading rests on its absence from the law, the regulation and the service conditions. | https://uaelegislation.gov.ae/en/legislations/1541 (Art. 49) ; https://uaelegislation.gov.ae/en/legislations/1547 (Art. 27) ; MOHRE "Issuance of a New Work Permit - Transfer Work Permit" https://www.mohre.gov.ae/en/services/transfer-work-permit-2022 (read via Wayback snapshot 2026-03-26) | 2026-10-30 | contested (only part stated) |
| 8 | Moving during probation | Art. 9(3): a worker on probation who moves to another UAE employer must give the original employer at least one month's written notice. The new employer compensates the original employer for recruitment costs unless agreed otherwise. Art. 9(6): a foreign worker who leaves the State without following these rules gets no new work permit for one year. MOHRE's transfer page points new employers to Art. 9(3)–(4). | https://uaelegislation.gov.ae/en/legislations/1541 (Art. 9) | 2026-10-30; last update 29 Jul 2024 | verified |
| 9 | Family / dependant residence visa | "Both, employers and employees with valid UAE residence visas can sponsor residence visas for their families." The family's residence permits are linked to the sponsor's: if the sponsor's visa is cancelled, the dependants' visas are cancelled too, with a 6-month grace period. | https://u.ae/en/information-and-services/visa-and-emirates-id/Types-of-visas/Residence-visa/residence-visa-for-family-members | 2026-10-30; updated 28 Sep 2026 | verified |
| 10 | Family visa holder working | Yes, on a separate permit. MOHRE "Dependents Sponsored by Family Members" permit (regulation type (c)): the employer applies. Conditions: the worker "must have a valid residence permit for his relatives"; holds no active work permit; no electronic quota needed; all skill levels and professions; full-time, part-time, temporary, flexible or remote contracts; valid 2 years. u.ae: it "enables companies to hire residents under family sponsorship from within the UAE". The required documents list no NOC from the family sponsor. **Implies:** sponsorship = No (residence stays with the family sponsor). authorized_now = Yes in the "no new visa needed" sense; the employer files this permit. | MOHRE https://www.mohre.gov.ae/en/services/work-permits-for-dependents-sponsored-by-family-members-2022 (Wayback snapshot 2026-03-26) ; u.ae work permits page (row 1) | 2026-10-30; u.ae 19 Oct 2026 | verified |
| 11 | Golden visa | A long-term, renewable residence visa valid for 5 or 10 years, with "the privilege of not needing a sponsor". It lets holders "live, work or study in the UAE", sponsor family, and stay outside the UAE for more than 6 months. Categories: investors (public or real-estate investment), entrepreneurs, exceptional talents, outstanding students and graduates, humanitarian pioneers, frontline heroes. ICP FAQ: "residency without a sponsor". | https://u.ae/en/information-and-services/visa-and-emirates-id/Types-of-visas/golden-visa ; https://icp.gov.ae/en/faq/ | 2026-10-30; u.ae updated 28 Jul 2026 | verified |
| 12 | Golden visa holder taking a private job | The employer must obtain the "Work Permit for Holders of Golden Residency" (regulation type (j)). MOHRE conditions: the candidate must hold a valid golden visa and "must not possess a valid residence visa" (i.e. no other residence); no bank guarantee; no quota; valid 2 years. **Implies:** sponsorship = No, authorized_now = Yes (no visa needed; the employer files the golden permit). | https://uaelegislation.gov.ae/en/legislations/1547 (Art. 6(1)(j)) ; MOHRE https://mohre.gov.ae/en/services/work-permits-of-golden-visa-holders-2022 (Wayback snapshot 2026-03-08) ; u.ae work permits page | 2026-10-30 | verified |
| 13 | Green visa | A 5-year renewable residence. ICP: it "enables holders to live and work in the UAE without the need for a sponsor"; "No sponsor is required within the UAE". Three categories. (1) Skilled workers: **must have a valid employment contract within the UAE**, MOHRE skill level 1–3, a bachelor's degree or above, and at least AED 15,000 a month. (2) Freelancers / self-employed: a MOHRE freelance or self-employment permit, a degree or diploma, and at least AED 360,000 a year in freelance income over the previous 2 years. (3) Investors / partners. u.ae lists the same three categories and lists the page under "Investor visa". **Implies:** sponsorship = No (ICP). authorized_now = Yes (ICP: "live and work"). | https://icp.gov.ae/en/services/uae-green-residency/ ; https://u.ae/en/information-and-services/visa-and-emirates-id/Types-of-visas/Investor-visa/Green-visa | 2026-10-30; ICP content date 12 Sep 2026 (footer 29/10/2026); u.ae 28 Jul 2026 | verified |
| 14 | Which MOHRE permit a new employer files for a Green visa holder | Not found. The regulation and u.ae have no Green-specific permit type (unlike Golden, type (j)). It is also not stated whether a skilled-worker Green visa survives a change of employer, given the "valid employment contract" condition. Searched: u.ae work permits page, regulation Art. 6, ICP Green guide, ICP FAQ, and u.ae/icp/mohre site searches. | as rows 3 and 13 | 2026-10-30 | not found |
| 15 | Freelance permit | A MOHRE **work permit, not a residence status** (regulation type (l)). It is issued to individuals who freelance independently, "with self-sponsorship for expat individuals", with no employer sponsorship and no employment contract, in a manner that the person "is, in no way, an employee" of the clients. A freelancer's residence is their own (e.g. the Green visa's freelancer category, row 13). **Implies:** the permit alone does not authorize employment as someone's employee: authorized_now = depends on the person's residence; sponsorship = depends. | https://uaelegislation.gov.ae/en/legislations/1547 (Art. 6(1)(l)) ; u.ae work permits page | 2026-10-30 | verified |
| 16 | Jobseeker visit visa | Issued "without requiring a host/sponsor in the country, for one trip", valid 60, 90 or 120 days. Eligibility: MOHRE skill level 1–3, or a graduate within 2 years of a top-500 university; a bachelor's degree or equivalent; a financial guarantee. The page does not say whether the holder may work. | https://u.ae/en/information-and-services/visa-and-emirates-id/Types-of-visas/Visit-visa/jobseeker-visit-visa | 2026-10-30; updated 28 Sep 2026 | verified |
| 17 | Visit visa holders (any kind) and work | No visit- or tourist-visa page says whether the holder may work (checked: Visit visa, Tourist visa, jobseeker visit visa). The rule comes from rows 1 and 6: working without a valid work permit is illegal, and the employer must apply for the work visa. **Implies:** authorized_now = No, sponsorship = Yes. | rows 1, 6 ; https://u.ae/en/information-and-services/visa-and-emirates-id/Types-of-visas/Visit-visa ; https://u.ae/en/information-and-services/visa-and-emirates-id/Types-of-visas/tourist-visa | 2026-10-30; tourist page 01 Oct 2026 | verified (via the general permit rule; no visit-specific sentence) |
| 18 | Outside the UAE / no UAE visa | MOHRE's "recruitment of workers from outside the State" permit (regulation type (a)), plus the employer applies for the work visa. **Implies:** authorized_now = No, sponsorship = Yes. | rows 3, 6 | 2026-10-30 | verified |
| 19 | Student visa | The sponsor is a UAE-resident parent or the accredited university or college. The u.ae page says nothing about work. A "training and student employment" permit exists, but u.ae describes it as for "a 15-year old student who is already in the UAE", valid 3 months. Whether a university student may take a job, and on which permit, is not stated. **Implies:** depends for both answers. | https://u.ae/en/information-and-services/visa-and-emirates-id/Types-of-visas/residence-visa-for-studying-in-the-uae ; u.ae work permits page ; regulation Art. 6(1)(h) | 2026-10-30; updated 28 Sep 2026 | contested (only part stated) |
| 20 | Virtual work (remote) visa | "Residence visa for working outside the UAE": a one-year, self-sponsored visa to live in the UAE "while working for a company outside the UAE". The page does not say whether the holder may work for a UAE employer. **Implies:** depends for both answers. | https://u.ae/en/information-and-services/visa-and-emirates-id/Types-of-visas/Residence-visa/residence-visa-for-working-outside-the-uae | 2026-10-30; updated 07 Aug 2026 | contested (only part stated) |
| 21 | Other residence types | u.ae "Types of visas" lists: Golden, Visit, Work, Residence (families of employees, families of university students, the retired, working outside the UAE), Student, Investor (incl. Green), Tourist, Transit, Medical, Blue. The work-visa page also names the domestic worker's visa. None of the investor, retired or Blue visa pages was checked for a right to take a job. | https://u.ae/en/information-and-services/visa-and-emirates-id/residence-visas ; https://u.ae/en/information-and-services/visa-and-emirates-id/Types-of-visas/Residence-visa | 2026-10-30; no date shown | verified (list only) |
| 22 | Golden and Green: one choice or two | **Two.** Rows 11–14 show different durations (5 or 10 years vs 5), a different MOHRE route (Golden has its own permit type (j); Green has none), and a different link to employment (the skilled-worker Green requires a valid UAE employment contract; Golden has no such condition). Both are sponsor-free, so their yes/no work-permit answers match. | rows 11–14 | 2026-10-30 | verified (facts); recommendation derived |

### 2. Address

| # | Fact | Finding | Source | Checked | Status |
|---|---|---|---|---|---|
| 23 | Emirate line | `"require":"AS"` (street address and state are required). `"state_name_type":"emirate"`. `"sub_keys":"أبو ظبي~إمارة الشارقةّ~الفجيرة~ام القيوين~إمارة دبيّ~إمارة رأس الخيمة~عجمان"`. Latin names (`sub_lnames`): Abu Dhabi~Sharjah~Fujairah~Umm Al Quwain~Dubai~Ras al Khaimah~Ajman. ISO ids (`sub_isoids`): AZ~SH~FU~UQ~DU~RK~AJ. The URL redirects to www.gstatic.com/chrome/autofill/libaddressinput/chromium-i18n/ssl-address/data/AE. | https://chromium-i18n.appspot.com/ssl-address/data/AE | 2026-10-30; no date in data | verified |
| 24 | Postcode and city | `"fmt":"%N%n%O%n%A%n%S"` (name, organisation, street address, emirate). There is **no `%Z` (postcode) and no `%C` (city/locality)**, and no `zip` or `zip_name_type` key. Chrome's format therefore has no postcode and no city line; the emirate is the last line. | same | 2026-10-30 | verified (per Google metadata only; no UAE postal authority page checked) |

### 3. Gulf pay terms

| # | Fact | Finding | Source | Checked | Status |
|---|---|---|---|---|---|
| 25 | Basic wage | Art. 1: "Basic Wage" is the wage set in the employment contract, paid monthly, weekly, daily, hourly or piece-meal, and "does not include any other allowances or benefits in kind". | https://uaelegislation.gov.ae/en/legislations/1541 (Art. 1) | 2026-10-30; last update 29 Jul 2024 | verified |
| 26 | Total wage | The law's term for the total is plain **"Wage"** (Art. 1). It is the basic wage plus the cash allowances and benefits in kind due under the contract or the law. It may include in-kind benefits or their cash equivalent, effort or risk allowances, cost-of-living allowances, and sales or profit percentages. The law has no "total wage" term. | same (Art. 1) | 2026-10-30 | verified |
| 27 | Gratuity on basic wage | Art. 51(2): a foreign full-time worker with at least 1 year of continuous service gets a gratuity "calculated according to the basic wage": 21 days' wage for each of the first 5 years, 30 days' wage for each year after that, capped at 2 years' wage (51(6)). Art. 51(5): it is computed on the last basic wage. Art. 51(1): national workers get pension and social security instead. u.ae: the gratuity "will not include allowances such as housing, transportation, utilities, furniture etc." | same (Art. 51) ; https://u.ae/en/information-and-services/jobs/Sector-of-employment/employment-in-the-private-sector/end-of-service-benefits-for-employees-in-the-private-sector | 2026-10-30; u.ae updated 15 Oct 2026 | verified |
| 28 | Housing allowance | Art. 13(4): the employer must provide adequate licensed accommodation, "or pay him housing allowance, or include it in the wage". So housing can be in kind, a separate cash allowance, or folded into the wage. | https://uaelegislation.gov.ae/en/legislations/1541 (Art. 13) | 2026-10-30 | verified |
| 29 | Transport allowance | No article of the law defines or requires a transport allowance. It is only one of the possible allowances inside "Wage" (row 26). u.ae names "transportation" among the allowances excluded from the gratuity. | rows 26, 27 | 2026-10-30 | contested (named, not defined or required) |
| 30 | Packages split into basic + housing + transport (+ total) | Two independent Gulf sources show the split, **in offers, not in application forms**. (1) GulfTalent (Gulf job board), "Dubai Job Offer Letters": many companies break total pay into basic salary, accommodation allowance and transport allowance. It adds that not all companies segment pay this way and some call the whole amount "basic salary". (2) Talentera (MENA ATS vendor), offer-letter template: "Basic salary: [Amount & Currency] per [month/year]" plus "Allowances: [Housing] [Transport] [Utilities] [Mobile] [Other] – total". A third source: Qureos (GCC hiring platform / ATS) UAE salary calculator fields "Basic Monthly Salary", "Housing Allowance", "Transport Allowance", "Other Allowance". **No source found showing an application form that asks the candidate for this split.** Searched: Bayt, GulfTalent and Naukrigulf pages; exact-phrase searches for "current basic salary" / "current housing allowance". | https://www.gulftalent.com/resources/dubai-jobs-guide/accepting-a-job-offer ; https://www.talentera.com/en/blog/employment-offer-letter-mena-guide/ ; https://www.qureos.com/salary-calculators/uae | 2026-10-30; Talentera dated 23 Feb 2026; others undated | contested (the split is shown for packages and offers; not shown on forms) |
| 31 | Personal income tax | u.ae: "The UAE does not levy income tax on individuals." FTA Corporate Tax guide CTGTNP1 (natural persons), §3.8.1: a wage, including any cash or in-kind benefit from the employer, "is not subject to Corporate Tax". So a salary carries no income tax. | https://u.ae/en/information-and-services/finance-and-investment/taxation ; https://tax.gov.ae/Datafolder/Files/Guides/CT/Taxation%20of%20natural%20persons%20-%2025%2011%202023.pdf | 2026-10-30; u.ae no date (© 2024 footer); FTA guide file dated 25 Nov 2023 | verified |
| 32 | "The package is net" | True of income tax (row 31). For UAE and GCC nationals it may not be net: Art. 51(1) puts nationals under pensions and social security legislation, and u.ae's GCC page says employers register GCC staff in their home countries' social insurance schemes. Employee contribution rates were not checked. | rows 5, 27, 31 | 2026-10-30 | contested (net of tax: yes; net of pension deductions for nationals: not checked) |

### Proposed data

```yaml
AE:
  pack: gulf
  # How to read the permit answers here. In the UAE private sector every hire,
  # Emiratis included, needs a MOHRE work permit that the employer files
  # (Decree-Law 33/2021 Art. 6). So:
  #   authorized_now = may take a UAE job without the employer sponsoring a
  #                    residence (work) visa; only the employer's work permit
  #                    is needed.
  #   sponsorship    = the employer must sponsor a residence (work) visa.
  # "depends" = the sources do not settle it: leave the answer unknown and
  # ask the user, never fill it.
  work_status:
    - key: uae_national
      label: "UAE national (Emirati)"
      authorized_now: "yes"
      sponsorship: "no"
      employer_files: "UAE national work permit"
      has_expiry: false
    - key: gcc_national
      label: "GCC national"
      authorized_now: "yes"
      sponsorship: "no"
      employer_files: "National / GCC citizen work permit"
      has_expiry: false
    - key: work_visa
      label: "Work visa (employment residence visa)"
      authorized_now: depends   # yes for the current sponsoring employer only
      sponsorship: "yes"        # for a new employer: transfer work permit + work visa
      employer_files: "Transfer work permit, then the work visa"
      has_expiry: true
    - key: family_visa
      label: "Residence visa on family sponsorship"
      authorized_now: "yes"
      sponsorship: "no"
      employer_files: "Work permit for dependents sponsored by family members"
      has_expiry: true          # follows the family sponsor's residence
    - key: golden_visa
      label: "Golden visa"
      authorized_now: "yes"
      sponsorship: "no"
      employer_files: "Work permit for holders of golden residency"
      has_expiry: true          # 5 or 10 years
    - key: green_visa
      label: "Green visa"
      authorized_now: "yes"     # ICP: live and work without a sponsor
      sponsorship: "no"
      employer_files: unknown   # no Green-specific permit type found
      has_expiry: true          # 5 years
    - key: student_visa
      label: "Student visa"
      authorized_now: depends
      sponsorship: depends
      has_expiry: true
    - key: virtual_work_visa
      label: "Virtual work visa (residence for working outside the UAE)"
      authorized_now: depends
      sponsorship: depends
      has_expiry: true
    - key: other_residence
      label: "Other residence visa (investor, retired, Blue visa, other)"
      authorized_now: depends
      sponsorship: depends
      has_expiry: true
    - key: visit_visa
      label: "Visit visa (including the jobseeker visit visa)"
      authorized_now: "no"
      sponsorship: "yes"
      has_expiry: true
    - key: no_visa
      label: "No UAE visa (outside the UAE)"
      authorized_now: "no"
      sponsorship: "yes"
      has_expiry: false
  # Freelance is a MOHRE work permit, not a residence status: model it as a
  # separate yes/no ("Do you hold a MOHRE freelance work permit?") if it is
  # needed. It does not authorise employment as an employee.

  address:
    asks_state: true
    state_label: "Emirate"
    state_required: true          # require: "AS"
    states:                       # key = ISO 3166-2:AE subdivision; label = sub_lnames
      - {key: AZ, label: "Abu Dhabi"}
      - {key: SH, label: "Sharjah"}
      - {key: FU, label: "Fujairah"}
      - {key: UQ, label: "Umm Al Quwain"}
      - {key: DU, label: "Dubai"}
      - {key: RK, label: "Ras al Khaimah"}
      - {key: AJ, label: "Ajman"}
    asks_postcode: false          # no %Z in fmt
    asks_city: false              # no %C in fmt; forms may still ask one

  pay:
    currency: AED
    period: month
    fields:
      - key: basic
        label: "Basic salary"       # law: "Basic Wage" (Art. 1); gratuity basis (Art. 51)
      - key: housing
        label: "Housing allowance"  # Art. 13(4): may be provided in kind or included in the wage
        allow_provided: true
      - key: transport
        label: "Transport allowance"
        allow_provided: true        # e.g. a company car
      - key: other
        label: "Other allowances"   # optional: utilities, mobile, education ...
        optional: true
      - key: total
        label: "Total monthly salary"  # law: "Wage" = basic + cash allowances + in-kind benefits
    income_tax_on_salary: false     # u.ae; FTA CTGTNP1 §3.8.1
```

### Notes

- **What `authorized_now` can mean in the UAE.** Every private-sector job needs a MOHRE work permit that the employer files, for Emiratis and GCC nationals too (rows 1, 4, 5). So a US-style "authorized, no employer action needed" is never true here. The answer that separates statuses is whether the employer must **sponsor a residence (work) visa**. The YAML adopts that reading. It is a design decision for the owner to confirm, because a form's wording may mean something else.
- **The draft list gets these wrong:**
  - `golden_or_green_visa` should be two choices (row 22).
  - `freelance_permit` is a MOHRE work permit (regulation type (l)), not a residence status. By definition its holder "is, in no way, an employee", so it does not authorize the jobs the app applies to. A freelancer's residence is usually the Green visa's freelancer category, which `green_visa` covers.
  - The list is missing a student visa, the virtual (remote) work visa, and a catch-all for other residences (investor, retired, Blue).
  - `employment_visa` cannot carry a fixed authorized_now. It is Yes only for the current sponsor; a new employer files a transfer permit and a new work visa.
- **The draft's pay fields get these wrong:**
  - Housing and transport are not always cash. Art. 13(4) allows accommodation in kind or housing included in the wage, and GulfTalent mentions a company car instead of a transport allowance. The fields need "provided" or "included" options, not just a number.
  - Some employers quote the whole amount as "basic", so basic + housing + transport may not exist as separate figures.
  - The law's word for the total is "Wage", and it includes in-kind benefits.
  - No source was found showing that application **forms** ask for the split (row 30). Treat the four-field split as the offer convention and keep the forms' own single "expected salary" answer as a fallback.
- **Address:** the Emirate is required. Google's format has no postcode and no city line. Arabic `sub_keys` are the data keys; use the ISO ids or `sub_lnames` for English UIs.
- **NOC:** the claim that a resident changing employers needs no NOC rests on its absence from Art. 49, Regulation Art. 27 and the MOHRE transfer-permit conditions; no primary page states it. Probation moves carry notice and compensation duties (Art. 9).
- **Government and free zones:** the labour law and MOHRE permits cover the private sector only (Art. 3). Government jobs, domestic workers, and free zones with their own employment regimes were not researched. A user applying to those employers may face different rules.
- **Freshness:**
  - The uaelegislation.gov.ae page for Decree-Law 33/2021 says its last update was listed on 29 Jul 2024, with 3 amendments. A MOHRE download link names a consolidated "and its amendments" PDF whose file timestamp looks like late 2025. A later amendment to Arts. 1, 6, 9, 13, 49 or 51 cannot be ruled out; the PDF could not be fetched because MOHRE refused connections.
  - The Executive Regulation page shows 03 Feb 2022, and later amending resolutions were not checked.
  - The MOHRE service pages were read from March 2026 Wayback snapshots; re-check them live.
  - The u.ae pages carry 2026 update dates, the newest 19 Oct 2026.
- **Translation:** the English regulation calls type (c) "Permit for those who are sponsored by their parents". u.ae says "family sponsorship" and MOHRE says "Dependents Sponsored by Family Members". The Arabic text prevails (portal disclaimer).

---

## Europe: citizenship, CEFR, pay

Research date: 2026-10-30. Primary sources only for rules; job boards / recruiters only for "what forms ask" conventions. No employer is named. CEFR descriptor text is paraphrased, not copied.

| # | Fact | Finding | Source | Checked | Status |
|---|---|---|---|---|---|
| 1 | EU citizens need no work permit in another EU state | Your Europe says an EU national generally does not need a work permit to work anywhere in the EU. Self-employed people never need one. The only caveat on the page is Liechtenstein, which sets quotas on EU, Norwegian and Icelandic nationals who live and work in Liechtenstein. That caveat does not touch DE, NL or IE. | https://europa.eu/youreurope/citizens/work/work-abroad/work-permits/index_en.htm | 2026-10-30; page "Last checked: 03/09/2026" | verified |
| 2 | EU and EEA member list | **EU (27):** AT, BE, BG, HR, CY, CZ, DK, EE, FI, FR, DE, GR, HU, IE, IT, LV, LT, LU, MT, NL, PL, PT, RO, SK, SI, ES, SE. **EEA (30)** is the 27 plus Iceland, Liechtenstein and Norway. Switzerland is in EFTA but not in the EEA. The IND adds that the UK has not been an EU/EEA member since 31 Jan 2020, and that Andorra, Monaco, San Marino and Vatican City nationals are not EU/EEA citizens. | https://www.government.nl/themes/international-cooperation/european-union/eu-eea-efta-and-schengen-area-countries ; https://ind.nl/en/member-states-eu-eea | 2026-10-30; no date shown on either page | verified |
| 3 | Switzerland's basis | The Agreement between the EC and its Member States and the Swiss Confederation on the free movement of persons was concluded at Luxembourg on 21 Jun 1999 and entered into force on 1 Jun 2002. It is in force for the Netherlands with no end date. Your Europe states that under this agreement Swiss nationals are free to live and work in the EU. | https://verdragenbank.overheid.nl/en/Treaty/Details/009215 ; Your Europe page in row 1 | 2026-10-30; treaty page shows no modified date | verified |
| 4 | Germany: EU/EEA/Swiss right to work | The Federal Foreign Office says EU citizens and citizens of Iceland, Liechtenstein, Norway and Switzerland have the right to live and work in Germany and only need to register locally after arrival. The statutory basis is § 2 FreizügG/EU: EU citizens who come as employees have a right of entry and residence and need no visa or residence title (§ 2(4)). § 12 extends the Act to EEA nationals. | https://www.auswaertiges-amt.de/en/visa-service/buergerservice/faq/02-arbeiten-606704 ; https://www.gesetze-im-internet.de/freiz_gg_eu_2004/__12.html ; https://www.gesetze-im-internet.de/englisch_freiz_gg_eu/englisch_freiz_gg_eu.html | 2026-10-30; AA page has no date ("© 1995–2026"); the English FreizügG translation reflects the 2015 amendment only | verified |
| 5 | Netherlands: EU/EEA/Swiss right to work | The IND says EU/EEA/Swiss citizens are free to work in the Netherlands and the employer does not need a work permit (TWV). They need no residence permit, because a valid EU/EEA/Swiss passport or ID card proves lawful residence. No IND registration is needed unless the IND ended an earlier residency. | https://ind.nl/en/residence-permits/eu-eea-or-swiss-citizens/staying-in-the-netherlands-as-an-eu-eea-or-swiss-citizen | 2026-10-30; page "last updated 10 July 2026" | verified |
| 6 | Ireland: EU/EEA/Swiss right to work | The Department of Enterprise says all non-EEA nationals need a valid employment permit (with listed exceptions), so EEA nationals need none. It names Iceland, Norway and Liechtenstein as the non-EU EEA states. It says the European Communities and Swiss Confederation Act 2001 allows free movement of workers between Switzerland and Ireland without employment permits. | https://enterprise.gov.ie/en/what-we-do/workplace-and-skills/employment-permits/employment-permit-eligibility/who-needs-an-employment-permit- | 2026-10-30; page shows "2021" and cites the Employment Permits Act 2024 | verified |
| 7 | Transitional limits in force on 2026-10-30 | **None found for DE, NL or IE.** The last EU worker transition was Croatia's. The Commission said those arrangements end irrevocably on 30 Jun 2020. The current DE, NL and IE pages in rows 4–6 state the free-movement rule with no nationality exceptions. | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:52015DC0233 (COM(2015) 233, 29.5.2015) plus rows 4–6 | 2026-10-30 | verified |
| 8 | British citizens in Ireland (CTA) | The UK–Ireland CTA Memorandum of Understanding of 8 May 2019, para 8, gives British citizens in Ireland and Irish citizens in the UK the right to work, including self-employment, with no permission required. Para 17 says the MoU is not itself legally binding. The Department of Foreign Affairs says Irish and British citizens continue to travel, live and work between the UK and Ireland as before. **The wording is "British citizens", not "UK nationals".** | https://assets.publishing.service.gov.uk/media/5cd29d56ed915d50b5a206d1/CTA-MoU-UK.pdf (via https://www.gov.uk/government/publications/memorandum-of-understanding-between-the-uk-and-ireland-on-the-cta) ; https://www.gov.ie/en/department-of-foreign-affairs/publications/living-and-working/ | 2026-10-30; MoU published 8 May 2019; DFA page "Last updated 25 April 2024" | verified |
| 9 | Irish citizens in the UK | Immigration Act 1971 s. 3ZA(1): an Irish citizen does not need leave to enter or remain in the UK. The only exceptions are a deportation order, exclusion or an international travel ban (3ZA(2)–(4)). The section was inserted by the Immigration and Social Security Co-ordination (EU Withdrawal) Act 2020 from 31 Dec 2020. MoU para 8 (row 8) states the right to work. The gov.uk CTA guidance confirms the right to work. | https://www.legislation.gov.uk/ukpga/1971/77/section/3ZA ; https://www.gov.uk/government/publications/common-travel-area-guidance | 2026-10-30; legislation.gov.uk is up to date to 29 Oct 2026; CTA guidance "Last updated 1 January 2026" | verified |
| 10 | British citizens in Germany after Brexit | **There is no citizenship-based right.** To work in Germany a UK national needs a work visa or residence permit. A UK national may enter as a jobseeker but cannot start work until holding one. A UK national living in Germany legally since before 1 Jan 2021 needs no work visa or permit (Withdrawal Agreement), and the Aufenthaltsdokument-GB is the proof. The Federal Foreign Office lists Great Britain among nationalities that may apply for the permit after arrival, which is still a permit. | https://www.gov.uk/guidance/living-in-germany ; Federal Foreign Office page in row 4 ; https://www.gesetze-im-internet.de/freiz_gg_eu_2004/__16.html | 2026-10-30; gov.uk "Last updated 11 December 2025" | verified |
| 11 | British citizens in the Netherlands after Brexit | **There is no citizenship-based right.** The Withdrawal Agreement does not apply to UK nationals who only started living in the Netherlands after 31 Dec 2020. They must apply for a residence permit for a set purpose. A UK national living in the Netherlands legally since before 1 Jan 2021 needs no work permit or visa. Anyone else "may need a work permit or work visa". | https://ind.nl/en/living-in-the-netherlands-after-brexit ; https://www.gov.uk/guidance/living-in-the-netherlands | 2026-10-30; IND "last updated 30 July 2025"; gov.uk "Last updated 23 December 2025" | verified |
| 12 | Scope of the Withdrawal Agreement exception | Art. 10(1)(b) covers UK nationals who exercised the right to reside in a Member State before the end of the transition period (31 Dec 2020) and continue to reside there. Art. 10(1)(d) covers UK frontier workers on the same terms, and Art. 10(1)(e) covers family members. Art. 24 keeps their Art. 45 TFEU worker rights. **Coverage depends on residence history, not citizenship.** | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:12019W/TXT(02) | 2026-10-30 | verified |
| 13 | Recent Swiss change | The EU–Swiss free movement agreement is still listed in force (row 3). Secondary sources (swissinfo, EY) report that Swiss voters rejected the "No 10-million Switzerland" initiative on 14 Jun 2026 by about 54.8%, so it did not trigger an end to free movement. I did not check a Swiss federal (admin.ch) page. | https://verdragenbank.overheid.nl/en/Treaty/Details/009215 ; vote: https://www.swissinfo.ch/eng/swiss-politics/june-14-2026-votes-results-from-across-switzerland/91505856 (secondary) | 2026-10-30 | contested (the vote is secondary only) |
| 14 | CEFR levels and groups | There are six levels, A1–C2, in three broad groups: **Basic User (A1, A2)**, **Independent User (B1, B2)** and **Proficient User (C1, C2)**. The levels are defined by "can-do" descriptors. | https://www.coe.int/en/web/common-european-framework-reference-languages/level-descriptions ; https://www.coe.int/en/web/common-european-framework-reference-languages/table-1-cefr-3.3-common-reference-levels-global-scale | 2026-10-30; no date shown | verified |
| 15 | CEFR short descriptors (global scale, Table 1) | The global scale has one holistic descriptor per level. They are paraphrased in the YAML below. The official wording is on the coe.int page and is not copied here. | coe.int Table 1 page (row 14) | 2026-10-30 | verified (paraphrased) |
| 16 | CEFR legacy level names (Breakthrough, Waystage, Threshold, Vantage, Effective Operational Proficiency, Mastery) | Not confirmed from a primary source. The coe.int HTML pages do not use these names. The 2001 CEFR PDF (rm.coe.int/1680459f97) returned 403 to fetch. Only third-party sites list the names. | Searched coe.int pages and site:coe.int | 2026-10-30 | not found |
| 17 | C2 is not "native speaker" | A journal article quotes CEFR 2001 p. 36 as saying C2 is not meant to imply native or near-native competence. Secondary analyses say the 2020 Companion Volume removed native-speaker wording from descriptors. I could not open the primary PDF. | https://dislaw-journal.uibk.ac.at/ds/article/view/63 (secondary, quotes CoE 2001 p. 36) | 2026-10-30 | contested (secondary quoting the primary) |
| 18 | Europass (EU CV format) language levels | Europass self-assessment uses the CEFR grids from A1 to C2. A person picks a level for five skills: listening, reading, spoken interaction, spoken production and writing. Neither Europass page states whether the Europass CV has a separate "mother tongue" field. | https://europass.europa.eu/en/common-european-framework-reference-language-skills ; https://europass.europa.eu/en/node/605 | 2026-10-30; no date shown | verified (grid); mother-tongue field not found |
| 19 | Germany: language scale in the BA Jobbörse profile | Not found. The candidate profile needs a login, which I did not create, and no public arbeitsagentur.de page describing its language scale turned up. In a sample of 25 software-developer ads in the BA Jobsuche on 2026-10-30, the ads that stated a level used CEFR in free text (for example "C1-Niveau"), sometimes mixed with "gute … Kenntnisse". The ads had no structured language-level field. | https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=1&was=Softwareentwickler (observed) | 2026-10-30 | not found (profile scale) |
| 20 | Germany: how CVs and forms state language level | **StepStone** (job board) recommends the GER/CEFR A1–C2 scale as the more precise option and gives its own labels: A1 Einstieg, A2 Grundlagen, B1 Mittelstufe, B2 Gute Mittelstufe, C1 Fortgeschrittene Kenntnisse, C2 Exzellente Kenntnisse. It also shows the verbal terms Grundkenntnisse, fließend, verhandlungssicher and Muttersprache. Its only explicit pairing is "C1 – fließend", and it gives no formal mapping. **stellenmarkt.de** (job board) presents CEFR and the verbal categories (Grundkenntnisse, fließend, verhandlungssicher, Muttersprache) as alternatives. It maps none of the verbal terms, groups C1/C2 as "bilingual and native", and itself recommends verbal terms such as "verhandlungssicher". **The two systems coexist and no standard mapping exists.** | https://www.stepstone.de/magazin/artikel/sprachkenntnisse-im-lebenslauf ; https://www.stellenmarkt.de/karrieremagazin/sprachkenntnisse-lebenslauf | 2026-10-30; StepStone "Aktualisiert 06.06.2025"; stellenmarkt "15.07.2024" | contested (no shared mapping) |
| 21 | Netherlands: language scale in the werk.nl CV | Not found. The werk.nl CV (Werkmap) needs a DigiD login. werk.nl vacancy search has a "Taal" filter, but I did not check its options. | https://www.werk.nl/nl/vacatures/ (observed) | 2026-10-30 | not found |
| 22 | Netherlands: how CVs and forms state language level | **YoungCapital** (job board) recommends ERK/CEFR levels and gives the table A1 Matig, A2 Redelijk, B1 Goed, B2 Uitstekend, C1 Vloeiend, C2 Moedertaal. Its FAQ says C2 means mother tongue. **Robert Half NL** (recruitment agency, not a board or ATS) uses Moedertaal / Vloeiend / Goed / Voldoende / Basis and separately A1–A2 basiskennis, B1–B2 zelfstandig gebruiker, C1–C2 "gevorderde tot bijna moedertaalniveau". It gives no conversion between them. **The two sources disagree on where "vloeiend" and "moedertaal" sit.** | https://www.youngcapital.nl/sollicitatietips/cv/talen-cv ; https://www.roberthalf.com/nl/nl/inzichten/carriere-ontwikkeling/je-talenkennis-op-je-cv-vermelden-zo-pak-je-het-aan | 2026-10-30; no dates shown | contested |
| 23 | Germany: expected pay = gross annual | **StepStone** (job board) recommends always stating the Gehaltsvorstellung as an annual salary, gross. It allows a monthly figure but calls it easy to misread about extras such as Weihnachtsgeld and Urlaubsgeld. **JobTeaser** (career/job platform) says the Gehaltsvorstellung is always given as gross annual pay (Jahresbruttogehalt). **ingenieur.de** (VDI job board) also defines it as the expected Bruttojahresgehalt including all extras. | https://www.stepstone.de/magazin/artikel/gehaltsvorstellung-darum-gibst-du-sie-als-jahresgehalt-an ; https://www.jobteaser.com/de/advices/gehaltsvorstellung-in-der-bewerbung-formulieren-so-geht-s ; https://www.ingenieur.de/karriere/gehalt/welches-gehalt-gebe-ich-bei-der-bewerbung-an/ | 2026-10-30; StepStone "Aktualisiert 08.01.2025"; JobTeaser "23. Juni 2025"; ingenieur.de "16.03.2022" | verified (convention) |
| 24 | Germany: ATS field | Personio (ATS) has an "expected salary" system attribute on its application form, according to Personio community threads. I could not confirm a period or unit, because support.personio.de returned 403. | https://community.personio.com/recruiting-29/how-to-remove-expected-salary-2726 (vendor community) | 2026-10-30 | contested (period unknown) |
| 25 | Netherlands: expected pay = gross monthly | **Nationale Vacaturebank** (job board) gives average pay as "bruto per maand", and its vacancy cards show monthly-scale ranges. **Indeed NL** (job board) listings showed "€ … – € … per maand" or "bruto per maand". The sample was small: 3 strings across 2 searches. The **IND** (regulator) sets the highly skilled migrant salary criterion as "gross per month" and excludes vacation allowance from what counts. | https://www.nationalevacaturebank.nl/vacatures/functie/embedded-software-developer (observed) ; https://nl.indeed.com/jobs?q=software+ontwikkelaar&l=Utrecht (observed) ; https://ind.nl/en/required-amounts-income-requirements | 2026-10-30; IND amounts labelled 2026 | verified (convention) |
| 26 | Netherlands: holiday allowance (vakantiegeld) | The minimum is **8% of the gross annual salary** of the past year, paid at least once a year (mostly May or June). An employee earning more than 3× the minimum wage may agree in writing to no or lower holiday allowance. A cao can exclude it if pay is at least 108% of the minimum wage. | https://www.rijksoverheid.nl/onderwerpen/vakantiedagen-en-vakantiegeld/vraag-en-antwoord/hoe-hoog-is-mijn-vakantiegeld | 2026-10-30; no date shown | verified |
| 27 | Netherlands: does an annual figure include the 8%? | No single convention found. Rijksoverheid computes vakantiegeld as 8% *on top of* the gross annual salary, so "brutojaarsalaris" as a base excludes it. Secondary salary sites say employers quote annual figures both with and without it. A form asking for an annual figure is ambiguous unless it says "incl./excl. vakantiegeld". | Rijksoverheid page in row 26 ; secondary: salaristabel.nl, Randstad | 2026-10-30 | contested |
| 28 | Netherlands: 13th month | No primary source found. Secondary sources (FNV, salaristabel.nl, MKB Servicedesk) say there is no statutory right and that it comes only from the cao, the contract or company rules. I found no rijksoverheid.nl page. | Searched rijksoverheid.nl "dertiende maand" / "eindejaarsuitkering" | 2026-10-30 | not found (primary) |
| 29 | Pay Transparency Directive, Art. 5 | Art. 5(1): applicants have the right to receive the initial pay or its range for the position, plus any relevant collective-agreement provisions. This comes before the interview, for example in the job ad. Art. 5(2): "An employer shall not ask applicants about their pay history during their current or previous employment relationships." Art. 2(3): Art. 5 applies to applicants for employment. Recital 33: employers should not enquire about or try to obtain an applicant's **current pay** or prior pay history. Expected pay is not banned. | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32023L0970 | 2026-10-30; OJ L 132, 17.5.2023 | verified |
| 30 | Transposition deadline | Art. 34(1): Member States must bring the measures into force **by 7 June 2026**. | EUR-Lex page in row 29 | 2026-10-30 | verified |
| 31 | Notified transposition measures (DE, NL, IE) | EUR-Lex lists **0** notified national measures for **Germany, Ireland and the Netherlands**, and shows no deadline entry for them. Countries such as BE, CZ, AT and SE list several. The collection is updated weekly. | https://eur-lex.europa.eu/legal-content/EN/NIM/?uri=CELEX:32023L0970 | 2026-10-30 | verified |
| 32 | Germany: transposition status | **Not transposed.** On 16 Jul 2026 the government (Drucksache 21/7026) said the BMBFSFJ had made preparations for a draft bill and was still clarifying questions; the legislative procedure would follow, with no date. On 9 Sep 2026 Die Linke filed a motion (Drs. 21/7916) asking the government to *present* a bill, so none was before the Bundestag then. The 2017 Entgelttransparenzgesetz still applies. I found no primary source for any draft between 9 Sep and 30 Oct. | https://www.bundestag.de/presse/hib/kurzmeldungen-1195086 (hib 587/2026) ; https://www.bundestag.de/presse/hib/kurzmeldungen-1211074 (hib 697/2026) ; EUR-Lex NIM (row 31) | 2026-10-30 | verified |
| 33 | Netherlands: transposition status | **Not transposed.** The bill "Wet implementatie Richtlijn loontransparantie mannen en vrouwen" (Kamerstuk 36949) was submitted on 21 May 2026 and is still pending. The nota naar aanleiding van het verslag and nota van wijziging came on 2 Sep 2026, a wetgevingsoverleg is planned for 14 Dec 2026, and the plenary is planned for week 50 of 2026 or week 2 of 2027. The target in-force date is 1 Jan 2027 "if all goes to plan". The planned rule bars employers from asking applicants what they earned before, and requires them to give the starting salary or pay scale in the ad or before the pay interview. | https://www.tweedekamer.nl/kamerstukken/wetsvoorstellen/detail?cfg=wetsvoorsteldetails&qry=wetsvoorstel%3A36949 ; https://www.rijksoverheid.nl/themas/werk/gelijke-behandeling-op-het-werk/plannen-kabinet-meer-openheid-over-loonkloof-tussen-mannen-en-vrouwen | 2026-10-30; Tweede Kamer procedure meeting 13 Oct 2026 | verified |
| 34 | Ireland: transposition status | **Not transposed.** The Government Legislation Programme for Autumn 2026 lists the "Pay Transparency Bill – to transpose the EU Pay Transparency Directive" under *All Other Legislation* with status "Heads in preparation", so it is not a priority. The "Equality (Miscellaneous Provisions) Bill" is under Priority Drafting with "Work is ongoing", and its listing does not mention pay transparency. Secondary sources say the Minister confirmed on 26 May 2026 that the deadline would be missed, and that the Jan 2025 General Scheme of the Equality (Misc. Provisions) Bill 2024 contains the pay-range and pay-history-ban measures. I could not reach oireachtas.ie because it showed a human-verification page. | https://www.gov.ie/en/department-of-the-taoiseach/organisation-information/legislation-information-bills-on-d%C3%A1il-order-paper/ → https://assets.gov.ie/static/documents/5d6bc854/Government_Legislation_Programme_Autumn_2026.pdf ; EUR-Lex NIM (row 31) | 2026-10-30; gov.ie page "Last updated 16 September 2026"; programme lists bills as of 10 Sep 2026 | verified (status); contested (PQ wording, General Scheme contents) |

Totals: 24 verified (rows 1–12, 14, 15, 18, 23, 25, 26, 29–34), 6 contested (13, 17, 20, 22, 24, 27), 4 not found (16, 19, 21, 28). Row 18 also has a "not found" part (the mother-tongue field) and row 34 a "contested" part (the PQ wording).

### Proposed data

```yaml
# Derived work-permit answers. Computed, never stored; an explicit user answer always wins.
# All rules give: authorized_now: yes, sponsorship_now: no, sponsorship_future: no.
work_permit_derivation:
  as_of: 2026-10-30
  rules:
    - id: own_country
      when_citizen_of: "<X>"
      applies_in: ["<X>"]
      basis: "citizenship of the country itself"

    - id: eu_eea_ch_free_movement
      when_citizen_of: [AT, BE, BG, HR, CY, CZ, DK, EE, FI, FR, DE, GR, HU, IE, IT,
                        LV, LT, LU, MT, NL, PL, PT, RO, SK, SI, ES, SE,   # EU 27
                        IS, LI, NO,                                       # EEA non-EU
                        CH]                                               # EU–Swiss AFMP (in force 2002-06-01)
      applies_in: [DE, NL, IE]
      transitional_limits: none   # Croatia's ended 2020-06-30 (COM(2015) 233)
      sources:
        - https://europa.eu/youreurope/citizens/work/work-abroad/work-permits/index_en.htm
        - https://www.auswaertiges-amt.de/en/visa-service/buergerservice/faq/02-arbeiten-606704
        - https://ind.nl/en/residence-permits/eu-eea-or-swiss-citizens/staying-in-the-netherlands-as-an-eu-eea-or-swiss-citizen
        - https://enterprise.gov.ie/en/what-we-do/workplace-and-skills/employment-permits/employment-permit-eligibility/who-needs-an-employment-permit-

    - id: cta_british_in_ireland
      when_citizen_of: [GB]          # "British citizen" only, the MoU's wording (see notes)
      applies_in: [IE]
      sources:
        - https://assets.publishing.service.gov.uk/media/5cd29d56ed915d50b5a206d1/CTA-MoU-UK.pdf   # para 8
        - https://www.gov.ie/en/department-of-foreign-affairs/publications/living-and-working/

    - id: cta_irish_in_uk
      when_citizen_of: [IE]
      applies_in: [GB]
      sources:
        - https://www.legislation.gov.uk/ukpga/1971/77/section/3ZA
        - https://assets.publishing.service.gov.uk/media/5cd29d56ed915d50b5a206d1/CTA-MoU-UK.pdf

  never_derive:            # leave these "unknown"; a citizenship alone does not settle them
    - when_citizen_of: [GB]
      in: [DE, NL]           # and every other EU/EEA state and CH
      reason: >
        After Brexit, British citizens need a work visa or residence permit. The Withdrawal
        Agreement exception (Art. 10(1)(b),(d)) depends on legal residence or frontier work
        that began before 2021-01-01, which is not citizenship. Ask the user.
    - when_citizen_of: [IS, LI, NO, CH, "EU-27 except IE"]
      in: [GB]
      reason: "No free movement into the UK since 2021-01-01. Only Irish citizens are exempt (s.3ZA)."

cefr:
  owner: Council of Europe
  source: https://www.coe.int/en/web/common-european-framework-reference-languages/table-1-cefr-3.3-common-reference-levels-global-scale
  levels:   # summary: own paraphrase of the global scale, not the official wording
    - {code: A1, group: Basic user,       summary: "Everyday expressions and very basic phrases; simple exchanges if the other person speaks slowly and helps."}
    - {code: A2, group: Basic user,       summary: "Frequent expressions on immediate topics; simple, routine exchanges of information."}
    - {code: B1, group: Independent user, summary: "Main points of clear standard input on familiar matters; most travel situations; simple connected text."}
    - {code: B2, group: Independent user, summary: "Main ideas of complex text, including technical discussion in own field; fluent interaction without strain; clear detailed text."}
    - {code: C1, group: Proficient user,  summary: "Demanding longer texts and implicit meaning; fluent and spontaneous; flexible use for social, academic and professional purposes."}
    - {code: C2, group: Proficient user,  summary: "Understands virtually everything with ease; summarises and reconstructs arguments; very fluent and precise."}
  native: separate_flag      # do not store "native" as C2 (rows 17, 22)
  skills_europass: [listening, reading, spoken_interaction, spoken_production, writing]
  # Verbal labels as forms show them. The mapping is APPROXIMATE and disputed (rows 20, 22).
  # Use it only to pick the nearest dropdown option and flag the pick for review; never convert back.
  verbal_labels:
    de:
      seen_options: [Grundkenntnisse, Gute Kenntnisse, Fließend, Verhandlungssicher, Muttersprache]
      stepstone_labels: {A1: Einstieg, A2: Grundlagen, B1: Mittelstufe, B2: Gute Mittelstufe, C1: Fortgeschrittene Kenntnisse, C2: Exzellente Kenntnisse}
      explicit_pairings_found: {C1: "fließend (StepStone example)"}
    nl:
      youngcapital_table: {A1: Matig, A2: Redelijk, B1: Goed, B2: Uitstekend, C1: Vloeiend, C2: Moedertaal}
      roberthalf_terms: [Moedertaal, Vloeiend, Goed, Voldoende, Basis]
      roberthalf_bands: {A1-A2: basiskennis, B1-B2: zelfstandig gebruiker, C1-C2: "gevorderd tot bijna moedertaalniveau"}

pay:
  DE:
    expected_pay:
      label: "Gehaltsvorstellung (Bruttojahresgehalt)"
      basis: gross
      period: year
      currency: EUR
      sources: [stepstone.de 08.01.2025, jobteaser.com 23.06.2025, ingenieur.de 16.03.2022]
  NL:
    expected_pay:
      label: "Gewenst bruto maandsalaris (exclusief vakantiegeld)"
      basis: gross
      period: month
      currency: EUR
      excludes: [holiday_allowance, thirteenth_month]
      sources: [nationalevacaturebank.nl, nl.indeed.com, ind.nl (regulator, gross/month excl. vacation allowance)]
    holiday_allowance:
      statutory_min_pct: 8          # of gross annual salary, paid at least yearly
      may_be_waived_above: "3 × minimum wage, by written agreement"
      source: https://www.rijksoverheid.nl/onderwerpen/vakantiedagen-en-vakantiegeld/vraag-en-antwoord/hoe-hoog-is-mijn-vakantiegeld
    thirteenth_month: not_statutory_unverified    # cao/contract only (secondary sources)
    annual_figure_rule: >
      If a form asks for an annual figure, say whether it is incl. or excl. 8% vakantiegeld and
      any 13th month. Never convert silently.

pay_history:   # EU Pay Transparency Directive (EU) 2023/970, Art. 5(2); deadline 2026-06-07
  rule: "Employers may not ask applicants about current or previous pay (Art. 5(2), recital 33). Expected pay is allowed."
  status_2026_10_30:
    DE: {transposed: false, note: "no bill before the Bundestag as of 2026-09-09; EntgTranspG 2017 still applies"}
    NL: {transposed: false, note: "bill 36949 pending; target in force 2027-01-01; bans asking previous pay"}
    IE: {transposed: false, note: "Pay Transparency Bill heads in preparation (Autumn 2026 programme)"}
  app_policy_suggestion: never_autofill_current_salary_for_eu_countries
```

### Notes

**What the design gets wrong or should tighten**

1. **"UK citizen" should be "British citizen".** The CTA MoU (para 8) and the DFA page say "British citizens". The UK has several other nationality classes, such as British Overseas Territories citizen and British National (Overseas). I found nothing showing that they share the CTA right to work in Ireland. Derive only for "British citizen" and leave the other classes unknown. The MoU is not legally binding (para 17). The Irish domestic statute behind it was not checked, and only the government statements were.
2. **UK citizens in Germany and the Netherlands must not be derived.** Rows 10–12 confirm the design's choice. The Withdrawal Agreement exception exists, but it depends on residence or frontier work that started before 1 Jan 2021. A British citizen who lived in Germany in 2019 is authorized; one who moved in 2022 is not. Citizenship alone cannot tell these apart, so the answer stays unknown.
3. **Native is not C2.** YoungCapital equates C2 with "moedertaal". Secondary sources quote the Council of Europe saying C2 is not native-speaker competence, and I could not open that primary PDF. Store "native" as a separate flag. A native speaker filling a CEFR-only dropdown will usually pick C2, but that is the user's choice, not a derivation.
4. **The verbal ↔ CEFR mapping is not a standard.** In DE and NL, job boards disagree: "fließend" is placed at C1 by StepStone, and "vloeiend" sits at C1 for YoungCapital but in the C1–C2 band for Robert Half. Treat any mapping as an approximate pick from a dropdown and flag it for review. Never derive a stored CEFR level from a verbal answer.
5. **"Current salary" in DE, NL and IE.** None of the three has transposed Art. 5(2) on 2026-10-30, so employers there may still lawfully ask until national law applies. The Netherlands plans the ban from 1 Jan 2027, and Germany and Ireland have no date. The directive bans asking about *current* pay, not only previous pay (recital 33). One option: treat "current salary" as a question to skip or leave blank in these countries, never autofill it, and keep "expected pay" as the answer.
6. **Netherlands pay needs two flags.** Store gross monthly pay excluding vakantiegeld; the IND and job boards both use monthly gross. Ask separately whether 8% vakantiegeld and a 13th month apply before showing any annual figure. Dutch annual quotes are ambiguous (row 27).
7. **Germany pay is gross annual**, but StepStone notes that a monthly figure is sometimes used. If a form says "monatlich", ask the user rather than dividing by 12, because 13th-month and holiday pay (Weihnachtsgeld, Urlaubsgeld) make the conversion lossy.

**Caveats and recent changes**

- The EU–Swiss agreement is in force. A Swiss popular initiative that could have ended it was reported rejected on 14 Jun 2026 (secondary only). Re-check this rule if Switzerland's status changes.
- The English FreizügG/EU translation on gesetze-im-internet.de reflects only the 2015 amendment. Germany's EU/EEA/Swiss rule here rests on the Federal Foreign Office page plus the current German § 12 and § 16.
- The Irish enterprise.gov.ie page carries a "2021" date but cites the Employment Permits Act 2024.
- For the pay-transparency status, EUR-Lex NIM is filled in by Member States and updated weekly. The latest primary German item is 9 Sep 2026, so a cabinet draft in the last seven weeks would not show here.
- For the Ireland Minister's 26 May 2026 written answer, oireachtas.ie showed human verification, so only law-firm reports of it were seen.
- Blocked sources:
  - make-it-in-germany.com showed browser verification, so I did not use it.
  - coe.int's 2001 CEFR PDF returned 403.
  - support.personio.de returned 403.
  - The werk.nl CV and the Jobbörse profile need a login.
- **Scope gap:** Ireland's pay and language conventions were not researched, as they were not asked.

---

## India

Sources for the job-board rows are the boards' own pages, or the JavaScript that draws their profile forms (loaded by the public registration page, read without signing in). The script URLs carry a build hash and will change. Re-check them when they 404. No employer is named, and no real person's application is quoted.

| # | Fact | Finding | Source | Checked | Status |
|---|---|---|---|---|---|
| 1a | Pay: forms ask current and expected CTC separately | Naukri's job-posting guide lists "Current CTC", "Expected CTC" and "Notice period" as the screening questions candidates answer while applying. PyjamaHR (Indian ATS) tells employers to "Enable 'Current CTC' and 'Expected CTC' fields" on the application form. Naukri also shows a candidate's expected CTC next to their current CTC on the CV page (archived RecruiterZone post). | https://www.naukri.com/recruit/learning-center/guides/job-posting ; https://helpcenter.pyjamahr.com/en/articles/11940821-how-to-configure-salary-rate-vs-ctc-fields-in-pyjamahr-step-by-step-guide-for-job-posts-and-application-forms ; http://web.archive.org/web/20260315171324/https://recruiterzone.naukri.com/displaying-ctc-expectations-on-cv-details-page/ | 2026-10-30 (Naukri guide: no date shown; PyjamaHR page dated 31 Jul 2026, text says "as of June 2024"; RecruiterZone post "Aug 23", year not shown, snapshot 15 Mar 2026) | verified |
| 1b | Pay: period | Pay is an annual figure. Naukri labels the field "Total annual salary", PyjamaHR defines CTC as "the total annual compensation package" (example "₹6,00,000 – ₹8,00,000 per annum"), foundit stores an annual `absoluteValue` and shows it as LPA, and Instahyre asks for LPA (lakhs per annum). | https://static.naukimg.com/s/9/121/_next/static/entity-components/component-desktop.781e77cc.min.js (loaded by https://www.naukri.com/registration/createAccount) ; PyjamaHR URL in 1a ; https://media.foundit.in/public/v2/seeker/_next/static/chunks/8461-d92486e552a0ecdd.js (loaded by https://www.foundit.in/seeker/registration) ; https://help.instahyre.com/en/article/your-profile-5pj32v/ | 2026-10-30 (Instahyre: updated 25/03/2022) | verified |
| 1c | Pay: entry unit (absolute rupees or LPA) | Boards differ. Naukri takes an absolute amount: digits only, grouped the Indian way, currency ₹ (INR) or $ (USD). Its older dropdowns were "Lacs" plus "Thousand". foundit stores absolute rupees and shows them as LPA (amount ÷ 1,00,000, two decimals). Instahyre wants LPA with decimals: "INR 15,50,000 would be written as 15.5 LPA". Naukri's recruiter search filters annual salary in "Lacs". | Naukri script (1b) ; Naukri Resdex guide https://www.naukri.com/recruit/learning-center/guides/resdex (filter screenshot: "Annual Salary … INR … Lacs") ; foundit script (1b) ; Instahyre (1b) | 2026-10-30 | contested |
| 1d | Pay: fixed vs variable split | Only Naukri was found splitting it. Its optional "Salary breakdown" has "Fixed salary", "Variable salary" and stock benefits, and checks that "Fixed + Variable can not be more than your total salary". If no breakdown is given, "Your total salary has been considered as fixed component". No split was found on Instahyre, foundit (registration script) or PyjamaHR. | Naukri script (1b) | 2026-10-30 | contested |
| 1e | Pay: expected pay as amount or hike % | Expected pay is an amount. Naukri: "Preferred salary", stored as `absoluteExpectedCtc` with its own currency. PyjamaHR: an "Expected CTC" field, and any other pay format goes in a custom screening question. No hike-percentage field was found in the Naukri form script, the foundit script, the Instahyre profile help or the PyjamaHR help. | Naukri script (1b) ; PyjamaHR (1a) | 2026-10-30 | verified (amount); hike % not found |
| 1f | Pay: current pay can be left out | Boards let candidates leave current pay out. foundit has a "hide salary" checkbox (`CURRENT_SALARY_HIDE_SALARY_CHECKBOX`), and Naukri's recruiter search offers "Include candidates who did not mention their current salary". | foundit https://media.foundit.in/public/v2/seeker/_next/static/chunks/102-822515d42921eefc.js ; Naukri Resdex guide (1c) | 2026-10-30 | verified |
| 1g | Law: does any Indian law define CTC? | Not found. "Cost to company" and "CTC" do not appear in the Code on Wages, 2019 text. In the Ministry of Labour FAQs, "CTC" appears only inside a question ("Is gratuity included where shown as part of CTC?"), and the reply does not define it. The Ministry's Compliance Handbook for the four Codes does not use the term. Searched: the Code on Wages text, the MoLE FAQs on the Code on Wages, the FAQs on Labour Codes, the Additional FAQs (16.03.2026) and the Compliance Handbook. The Social Security, IR and OSH Codes were not searched for the term. | https://www.labour.gov.in/static/uploads/2025/06/c328da14bbb15fc4ad571dc33e7a4ab3.pdf ; https://www.labour.gov.in/static/uploads/2026/03/a4ccf4c6d97c4f1f36a6d83f8c64213d.pdf ; https://www.labour.gov.in/static/uploads/2026/01/75252c07c1fe3a2f5571ff1464e2375e.pdf ; https://www.labour.gov.in/static/uploads/2026/01/de4758d5bfeffc456d7de97a801891b0.pdf ; https://www.labour.gov.in/static/uploads/2026/02/83978455025732b99b0165def80ab171.pdf | 2026-10-30 (Additional FAQs "As on 16.03.2026") | not found |
| 1h | Law: "wages" and the 50% rule | Code on Wages s.2(y): "wages" means all remuneration and includes (i) basic pay, (ii) dearness allowance and (iii) retaining allowance. It excludes, among others: bonus not in the terms of employment, house accommodation and amenities, employer PF and pension contributions, conveyance, HRA, award or settlement pay, overtime, commission, gratuity and retrenchment compensation. First proviso: if (a) to (i) together exceed one-half of all remuneration (or another notified %), the excess is added back into wages. The MoLE FAQ (16.03.2026) says overtime counts in the 50% calculation and that employer PF and pension contributions and statutory bonus count when arriving at the 50%. Gratuity, ESI and other retirement benefits do not. No percentage other than 50% has been notified in these sources. | Code text (1g) ; consolidated text https://www.indiacode.nic.in/indiacode/bitstream/123456789/15793/1/aA2019-29.pdf ; Additional FAQs (1g) | 2026-10-30 (India Code text "As on" 21 Nov 2025; FAQ 16.03.2026) | verified |
| 1i | Law: when the four Labour Codes came into force | 21 November 2025. Gazette S.O. 5322(E) of 21 Nov 2025 brings into force Code on Wages ss.1–41, 42(4)–(9), 43–66, most of 67, 68 and 69 (with listed exceptions). The PIB release of 21 Nov 2025 says the Code on Wages, the IR Code, the Social Security Code and the OSH Code are "being made effective from 21st November 2025". | https://www.labour.gov.in/static/uploads/2025/12/0fd090d29a4576739079a7b565c8ca9d.pdf ; https://www.pib.gov.in/PressReleasePage.aspx?PRID=2192463 | 2026-10-30 (both dated 21 Nov 2025) | verified |
| 2a | Notice: fixed choices or days | Boards use fixed choices, but the sets differ. Naukri's profile: "15 Days or less", "1 Months", "2 Months", "3 Months", "More than 3 Months", plus "Serving Notice Period". Naukri's recruiter filter: "0 - 15 days", "1 month", "2 months", "3 months", "More than 3 months", "Currently serving notice period". PyjamaHR has "Notice Period" as a standard field, with dropdown options set by the employer (its examples are "0/15/30/60/90 days" and "Immediate"). foundit stores notice as a number of days (`noticePeriod.days`). Instahyre uses a dropdown without listing the options. | Naukri script (1b) ; Naukri Resdex guide (1c, "Notice Period/ Availabilty to join") ; https://helpcenter.pyjamahr.com/en/articles/11940824-how-to-add-notice-period-and-immediate-joiner-filters-in-pyjamahr ; foundit script (1f) ; Instahyre (1b) | 2026-10-30 (PyjamaHR dated 31 Jul 2026) | contested (choices are standard; the bucket set is not) |
| 2b | Notice: "serving notice" as its own choice | Yes on Naukri (option "Serving Notice Period"; recruiter filter "Currently serving notice period") and on foundit (`noticePeriod.serving` true/false). Instahyre differs: if you are serving notice, set the notice field to "how soon you can join". | Naukri script (1b) ; Naukri Resdex guide (1c) ; foundit script (1f) ; Instahyre (1b) | 2026-10-30 | verified |
| 2c | Notice: last working day asked as a date | Yes. Naukri asks "Expected last working day" as a day/month/year date (stored YYYY-MM-DD), checks "Please select future date", and in edit-profile asks "Please specify your last working day in current company". foundit has a `lastWorkingDay` field with its own form step ("Landed_on_Last_Working_Day"). | Naukri script (1b) ; foundit script (1f) | 2026-10-30 | verified |
| 2d | Law: does any central law set an employee's notice period? | No central provision was found that fixes how much notice an employee must give when resigning. IR Code, 2020: the standing-orders chapter applies to industrial establishments with 300 or more workers (s.28). First Schedule item 8 says standing orders must cover "Termination of employment, and the notice thereof to be given by employer and workers", so the amount is set per establishment. Model Standing Orders, 2026 (S.O. 2312(E), 8 May 2026), Schedule C (service sector), para 23: the employer gives a permanent worker one month's notice or wages in lieu; temporary, probationer, badli/substitute, fixed-term and casual workers get no notice. No paragraph sets the notice a worker gives. "Worker" (s.2(zr)) excludes people employed mainly in a managerial or administrative capacity and supervisors earning over ₹18,000 a month (or a notified amount). Outside standing orders, the employment contract sets the notice period. | https://www.labour.gov.in/static/uploads/2025/07/682a44b5426bff2c1f4943ee1b2fd566.pdf ; https://egazette.gov.in/WriteReadData/2026/272341.pdf ; https://www.labour.gov.in/static/uploads/2026/02/83978455025732b99b0165def80ab171.pdf | 2026-10-30 (MSO notified 8 May 2026) | verified (central texts only) |
| 2e | Law: state Shops and Establishments Acts on notice | Not checked. The state and UT Acts and their rules were not searched in this pass. | none | 2026-10-30 | not found |
| 2f | Law: status of the Industrial Employment (Standing Orders) Act, 1946 | IR Code s.104 lets the commencement notification repeal the 1946 Act. The Model Standing Orders, 2026 supersede the Industrial Employment (Standing Orders) Central Rules, 1946 "in so far as they relate to these Model Standing Orders". The notification that actually repeals the Act was not read. | IR Code (2d) ; MSO 2026 (2d) | 2026-10-30 | contested (only part stated) |
| 3a | Experience: years only, or years and months | Years and months. Naukri: a "Years" dropdown (0 Year to 30 Years, then "30+ Years") and a "Months" dropdown (0 to 11). foundit: "Total Experience" with "Years" and "Months". Not every system does this: Zoho Recruit stores "Experience in Years" as a decimal, and Instahyre asks "years of experience". | Naukri script (1b) ; foundit script (1f) ; https://help.zoho.com/portal/en/kb/recruit/customization/field-level/standard-fields/articles/standard-fields ; https://help.instahyre.com/en/article/getting-started-nkf98s/ | 2026-10-30 (Zoho: "Updated: 2 years ago"; Instahyre: 25/03/2022) | verified |
| 3b | Experience: relevant experience as a profile field | No board profile has a stored "relevant experience" field. Naukri's job-posting guide treats relevant experience as a per-job screening question written by the employer (example: "Have you worked in a B2B client-facing role?"). Naukri does store years and months per IT skill. | Naukri job-posting guide (1a) ; Naukri script (1b, `itskills-exp-years` / `itskills-exp-months`) | 2026-10-30 | not found (as a standing field) |
| 4a | Locations: current location | Asked as one city. Naukri: "Current city" ("Mention the city you live in"), with an "Outside India" option. foundit: "Current Location". Instahyre: "current job location". Naukri's recruiter search filters on "Current location of candidate". | Naukri script (1b) ; foundit script (1f) ; Instahyre (1b) ; Naukri Resdex guide (1c) | 2026-10-30 | verified |
| 4b | Locations: preferred locations as a list of cities | Yes. Naukri: "Preferred work locations", up to 10 (placeholder "Eg. Chennai, Bangalore, Mumbai"), set under Job Preferences. foundit: "Preferred Location(s)". Instahyre: pick "desired location/locations" from a dropdown (national, international, or work from home). Naukri's recruiter search also matches candidates who "prefer to relocate" to the searched cities. | Naukri script (1b) ; https://www.naukri.com/blog/time-to-revisit-your-profile-on-naukri/ ; foundit script (1f) ; Instahyre (1b) ; Naukri Resdex guide (1c) | 2026-10-30 (Naukri blog 16 Apr 2024) | verified |

### Proposed data

```yaml
pack: india_basics
fields:
  - key: current_ctc
    label: "Current CTC (₹ per annum)"
    type: number
    unit: INR_per_year          # store absolute rupees (Naukri, foundit); convert to LPA = value / 100000 for forms that ask lakhs (Instahyre)
    optional: true              # boards let it be hidden or left blank (fact 1f)
  - key: current_ctc_fixed
    label: "Fixed salary (₹ per annum)"
    type: number
    unit: INR_per_year
    optional: true              # only Naukri asks for the split (fact 1d)
  - key: current_ctc_variable
    label: "Variable salary (₹ per annum)"
    type: number
    unit: INR_per_year
    optional: true
  - key: ctc_currency
    label: "Salary currency"
    type: select
    choices: [INR, USD]         # Naukri offers ₹ and $ (fact 1c)
    default: INR
  - key: expected_ctc
    label: "Expected CTC (₹ per annum)"
    type: number
    unit: INR_per_year          # asked as an amount; no board asks for a hike % (fact 1e)
  - key: notice_period_days
    label: "Notice period (days)"
    type: number
    unit: days                  # the source of truth; foundit stores days (fact 2a)
    form_choices:               # Naukri's own labels; map days to these by rounding UP, never down
      - {label: "15 Days or less", max_days: 15}
      - {label: "1 Months", max_days: 30}
      - {label: "2 Months", max_days: 60}
      - {label: "3 Months", max_days: 90}
      - {label: "More than 3 Months", min_days: 91}
  - key: serving_notice
    label: "Currently serving notice period?"
    type: select
    choices: ["Yes", "No"]      # Naukri "Serving Notice Period", foundit noticePeriod.serving (fact 2b)
  - key: last_working_day
    label: "Last working day"
    type: date                  # only when serving_notice = Yes; must be in the future (Naukri check) (fact 2c)
  - key: total_experience_years
    label: "Total experience — years"
    type: number
    unit: years                 # Naukri 0–30, then "30+ Years"
  - key: total_experience_months
    label: "Total experience — months"
    type: number
    unit: months                # 0–11 (Naukri, foundit) (fact 3a)
  - key: relevant_experience
    label: "Relevant experience"
    type: text
    per_job: true               # a per-job screening question, not a stored profile field (fact 3b)
  - key: current_location
    label: "Current location (city)"
    type: text                  # one city; allow "Outside India" (Naukri) (fact 4a)
  - key: preferred_locations
    label: "Preferred work locations"
    type: list
    max_items: 10               # Naukri cap; Instahyre also allows "Work from home" (fact 4b)
```

### Notes

- **The design gets experience wrong.** It says "total and relevant years of experience". Both large boards ask years and months for total experience (Naukri, foundit), so store both, or store total months. "Relevant experience" depends on the job: no board keeps it as a profile field, and employers ask it as a screening question. It cannot be one stored answer. Under "never guess a knockout answer", ask it per job.
- **"Notice period in days" is fine for storage, but forms ask fixed choices.** Naukri asks for buckets (15 days or less, 1/2/3 months, more than 3, serving). When converting days to a bucket, always round up (for example, 45 days becomes "2 Months"). Claiming a shorter notice than the real one is a knockout misstatement. Instahyre has no "serving" choice and wants "how soon you can join", so for forms like that, the fill should use the days left until the last working day.
- **The last working day goes stale.** Naukri requires a future date. Once that date passes, the stored "serving notice" answer is wrong. The pack should flag it, or recompute the days left from today's date.
- **CTC has no legal definition.** The Code on Wages defines "wages", and the 50% rule decides how much of a pay package counts as wages for PF, gratuity and bonus. That rule (in force since 21 Nov 2025) can change how employers structure CTC and payslips, but it does not define CTC. A MoLE FAQ answer had to clarify whether gratuity "shown as part of CTC" counts, which suggests employers' CTC figures do not all mean the same thing. The pack should store the figure the user gives and not derive CTC from payslips.
- **Unit:** store absolute rupees per year. Naukri and foundit take the full amount; Instahyre takes LPA with decimals; recruiter filters show Lacs. Convert at fill time. Naukri also lets pay be entered in USD.
- **Fixed/variable split:** only Naukri asks for it, and it is optional (with no split, the total is treated as fixed). Keep it optional rather than core.
- **Current CTC is optional on boards** (foundit hide checkbox; Naukri recruiters can include profiles with no salary). Employer forms may still make it required. The pack should allow "not shared" and leave it to the user per job.
- **Notice period law:** no central statute sets how much notice an employee must give when resigning. The Model Standing Orders, 2026 (8 May 2026) set the employer's one-month notice to permanent workers in establishments with 300 or more workers. Workers in managerial roles, and supervisors above ₹18,000 a month, are outside the definition of "worker" anyway. In practice the contract sets the notice. State Shops and Establishments Acts were not checked (fact 2e).
- **Recent changes:** the four Labour Codes came into force on 21 Nov 2025. The Model Standing Orders, 2026 were notified on 8 May 2026. The Ministry's Additional FAQs are dated 16 Mar 2026. The Code on Wages notification left a few s.67(2) rule-making clauses out of force.
- **Source fragility:** the Naukri and foundit rows rely partly on their form scripts, whose build-hash URLs will change. Instahyre's help dates from 2022.
