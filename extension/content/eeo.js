/* Maestro CS Companion — voluntary EEO and demographics solver. */

// ============================================================
// WHAT THIS FILE PUBLISHES
// ============================================================
(() => {
  const ns = (window.careerStudioCompanion ??= {});

  // "Self-describe", "I prefer to self-describe", `gender_self_describe`.
  const SELF_DESCRIBE = /self[-_\s]?describ/i;
  // A text box that follows a question for the user's own words rather than
  // asking one: a self-description goes there, and only that.
  const SPECIFY_BOX = /self[-_\s]?describ|\bspecify\b|\bif other\b/i;

  /** Build the protected-class rules and exact option matcher for one profile.
   * This module owns what counts as an EEO field, which answers exist, and how
   * each protected-class control is handled without replacing a user answer. */
  function createEeoContext(profile, norm) {
    const e = profile.eeo ?? {};
    const optionWords = {
      decline: [/decline/i, /don'?t wish/i, /prefer not/i, /not to (self.)?identify/i, /no answer/i],
      // ANCHORED, and that is the whole point of this entry.
      //
      // `/not a protected veteran/` used to be here unanchored, and Workday
      // offers "I identify as a veteran, just not a protected veteran" ABOVE
      // "I am not a veteran" (read off deluxe.wd5, 2026-08-08). The unanchored
      // pattern matched the first one, and `bestOption` takes the first option
      // matching ANY pattern — so a user who answered "I am not a veteran" had
      // the extension declare them a veteran. A false statement about a
      // protected characteristic, made on their behalf, on a form an employer
      // keeps.
      //
      // Anchoring is what makes the two disjoint: the negative answers all
      // BEGIN with the negation, and every option that opens with "I identify
      // as" is a claim of veteran status whatever it says afterwards.
      not_veteran: [
        /^\s*i\s+am\s+not\s+a\s+(?:protected\s+)?veteran\b/i,
        /^\s*i\s+(?:do\s+not|don'?t)\s+identify\s+as\b/i,
        /^\s*no\b/i,
      ],
      // Left unanchored on purpose — every wording of an affirmative starts
      // with the claim — but see `veteranClaimIsAmbiguous` below for the case
      // this cannot decide.
      veteran: [/identify as .*veteran/i, /^yes/i],
      disability_no: [/no,? i do,?n'?t have a disability/i, /don'?t have a disability/i, /^no\b/i],
      disability_yes: [/yes,? i have a disability/i, /^yes\b/i],
      male: [/^male$/i, /^man$/i],
      female: [/^female$/i, /^woman$/i],
      // Only an option that says non-binary. "Gender non-conforming" alone is
      // a different identity for some people, so a form offering only that is
      // left for the user (the owner's call, 2026-09-24): never a wrong answer.
      // Unanchored, because the wordings vary ("Nonbinary", "I identify as
      // non-binary", "Non-Binary/Gender Non-Conforming"), so a gender radio or
      // box is matched on its OWN words (`ownWords`), never on the question's.
      non_binary: [/\bnon[-\s]?binary\b/i],
      // The OPTION that says "I will describe it myself". Nothing here may
      // match a decline ("Decline to self-identify"), and nothing does.
      self_describe: [SELF_DESCRIBE],
    };
    // The values Profile › Autofill stores. Anything else (a hand-edited
    // "Woman") has no words: it is matched exactly or not at all, where it
    // used to fall back to the DECLINE words and answer for the user.
    const GENDER_VALUES = new Set(["male", "female", "non_binary", "self_describe", "decline"]);
    // What a free-text gender box is given. The rest keep the stored value,
    // which is already a word.
    const GENDER_TEXT = { non_binary: "Non-binary" };
    const selfDescription = String(e.gender_self_describe ?? "").trim();
    const yesNo = (value) =>
      (value === true ? "yes" : value === false ? "no" : value);
    const isEeoLabel = (label) =>
      /veteran|disab|hispanic|latino|gender|\bsex\b|race|ethnic/i.test(label)
      || SELF_DESCRIBE.test(label);

    // Race/ethnicity may contain several independently supplied categories.
    // Empty categories are discarded once, before rule construction.
    const raceList = [].concat(e.race_ethnicity ?? []).map(String)
      .filter((option) => norm(option) !== "");
    const hispanic = yesNo(e.hispanic_latino);
    const rules = [
      { id: "veteran", re: /veteran/i, value: e.veteran_status, kind: "veteran" },
      { id: "disability", re: /disab/i, value: e.disability_status, kind: "disability" },
      { id: "hispanic-latino", re: /hispanic|latino/i, value: hispanic, kind: "yesno",
        optionList: hispanic === "yes" ? ["Hispanic or Latino"] : [] },
      // `not`: "gender" is inside "transgender", and neither that question nor
      // sexual orientation is this one.
      { id: "gender", re: /gender|^sex\b/i, not: /\btransgender\b|\bsexual orientation\b/i,
        value: e.gender, kind: "gender" },
      { id: "race-ethnicity", re: /race|ethnic/i, optionList: raceList,
        value: raceList.join(", ") },
    ];

    const optionWordsFor = (kind, value) => {
      if (kind === "disability") {
        return value === "yes" ? optionWords.disability_yes
          : value === "no" ? optionWords.disability_no : optionWords.decline;
      }
      if (kind === "veteran") {
        return value === "veteran" ? optionWords.veteran
          : value === "not_veteran" ? optionWords.not_veteran : optionWords.decline;
      }
      if (kind === "gender") return GENDER_VALUES.has(value) ? optionWords[value] : [];
      return null;
    };

    /** A radio's or a box's own text: labelFor puts the control's own label
     * first and the question (legend, container) after it, so a legend that
     * lists the options ("man, woman or non-binary") cannot put the
     * non-binary words on every button. */
    const ownWords = (labelText) => String(labelText ?? "").split("|")[0].trim();

    /** Which of `items` answers a gender question: the one whose own words meet
     * the EARLIEST pattern of the value's ordered list, first in the DOM on a
     * tie. Null when none does. */
    const bestGenderItem = (items, textOf, value) => {
      const words = optionWordsFor("gender", value);
      let best = null;
      let bestRank = Infinity;
      for (const item of items) {
        const rank = words.findIndex((pattern) => pattern.test(ownWords(textOf(item))));
        if (rank >= 0 && rank < bestRank) { best = item; bestRank = rank; }
      }
      return best;
    };

    /** What a TEXT control is given for `rule`: `{text}`, or `{outcome}` when
     * it is given nothing. A box that follows the gender question for the
     * user's own words ("If you prefer to self-describe, please specify")
     * takes a self-description and nothing else: its label says gender, and
     * the gender rule typed "female" into it. */
    const textAnswer = (rule, value, labelText) => {
      if (rule.kind !== "gender") return { text: String(value) };
      if (SPECIFY_BOX.test(labelText) && value !== "self_describe") {
        return { outcome: "skip_rule" };
      }
      if (value === "self_describe") {
        return selfDescription ? { text: selfDescription } : { outcome: "missing_source" };
      }
      return { text: GENDER_TEXT[value] ?? String(value) };
    };

    /** The known value the retry lane may type into a search box after a miss:
     * what a form would show, never a stored key. A self-description is not
     * retried, since its option's wording varies from form to form. */
    const retryValue = (rule, value) => {
      if (rule.kind !== "gender") return value;
      if (value === "self_describe") return "";
      return GENDER_TEXT[value] ?? value;
    };

    /** An option text with the vendor's DECORATION removed, and nothing else.
     *
     * Workday's race list reads "3-Asian (Not Hispanic or Latino) (United
     * States of America)" (deluxe.wd5, 2026-08-08). The EEO bar is exact
     * normalized equality — deliberately, because "Asian" and "Asian Indian"
     * are different statements — so every one of those options was refused and
     * the field went unfilled with the opt-in ON.
     *
     * What is stripped is only ever ADDED by the form: a leading enumeration
     * code, and parentheticals. What is left is the category itself, and the
     * comparison on it stays EXACT — which is what preserves the property this
     * bar exists for. "Asian" canonicalizes to "asian" and "Asian Indian" to
     * "asian indian", so the near miss this refuses today it still refuses.
     */
    const canonicalOptionText = (text) => norm(
      String(text ?? "")
        .replace(/^\s*\d+\s*[-–—.)]\s*/, "")
        .replace(/\([^)]*\)/g, " ")
        .replace(/[.\s]+$/, ""),
    );

    // labelFor joins sources with " | ". Equality by segment is deliberate:
    // "Asian" must never match "Asian Indian" on a protected-class question.
    const optionFor = (labelText, optionList) => {
      const segments = new Set(labelText.split("|").map(norm));
      return (optionList ?? []).find((option) => segments.has(norm(option))) ?? null;
    };

    return {
      rules, isEeoLabel, optionWordsFor, optionFor, canonicalOptionText,
      ownWords, bestGenderItem, textAnswer, retryValue,
    };
  }

  /** The other boxes of ONE single-choice checkbox question.
   *
   * Workday gives every box of a question the same id SUFFIX — three
   * `…-disabilityStatus` boxes with different prefixes (live telemetry,
   * waystar.wd1) — and no shared name. So the suffix is the grouping signal
   * where there is one, the name where there is not, and the control itself as
   * the floor: a group of one is still a correct answer to "is anything here
   * already ticked".
   *
   * Bounded on purpose. A too-SHORT suffix would sweep in unrelated boxes, and
   * ticking one of those is a disclosure nobody asked for. */
  function eeoCheckboxGroup(input) {
    const suffix = String(input.id ?? "").split("-").pop();
    if (suffix && suffix.length >= 8) {
      const found = [...document.querySelectorAll(
        `input[type="checkbox"][id$="-${CSS.escape(suffix)}"]`)];
      if (found.length) return found;
    }
    if (input.name) {
      return [...document.querySelectorAll(
        `input[type="checkbox"][name="${CSS.escape(input.name)}"]`)];
    }
    return [input];
  }

  /** Apply the opt-in and strict-visibility bars for a protected-class field. */
  function shouldSkipEeoControl({
    input, kind, labelText, enabled, rule, isStrictlyVisible, observe,
  }) {
    if (!enabled) {
      observe(input, kind, labelText, null, "eeo_disabled");
      return true;
    }
    if (!isStrictlyVisible(input)) {
      if (rule && !rule.skip && !rule.missingSource) {
        observe(input, kind, labelText, rule, "hidden");
      }
      return true;
    }
    return false;
  }

  /** Own every protected-class DOM decision once a valued EEO rule matched.
   * General DOM primitives are injected by the autofill engine so its commit
   * ladder remains untouched and deliberately duplicated only where required. */
  async function handleEeoControl({
    context,
    input,
    kind,
    isSelect,
    isCombobox,
    isListboxButton,
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
    // The visit around a write that is not a text commit — autofill.js's
    // `visitControl` carries the whole reasoning, and it is handed in here for
    // the reason every other writer on this object is: one engine, one set of
    // gestures, so a voluntary-disclosure control is committed exactly the way
    // an ordinary one is.
    visitControl,
    leaveControl,
    clickControl,
    stillChecked,
    optionWordsFor,
    labelFor,
    doneRadioGroups,
    fillCombobox,
    commitValue,
    commitOk,
  }) {
    const record = (item, stuck = true) => {
      filled.push(item);
      if (stuck) {
        eeoFilled.push({ field: rule.id, label: item.label, value: item.value });
      }
    };

    // Several race categories have no honest one-value representation. Only
    // per-option checkboxes may carry them.
    if (rule.optionList?.length > 1 && input.type !== "checkbox") {
      observe(input, kind, labelText, rule, "skip_rule");
      return;
    }

    if (isSelect) {
      const options = [...input.options]
        .filter((option) => option.value !== "")
        .map((option) => ({ el: option, text: option.textContent ?? "" }));
      const best = bestOption(options, res);
      // Any existing answer, including decline-to-identify, belongs to the user.
      if (best && !input.value) {
        visitControl(input);
        setNativeValue(input, best.el.value);
        leaveControl(input);
        record({ label, value: best.text.trim().slice(0, 60) });
        observe(input, kind, labelText, rule, "filled");
      }
      return;
    }

    if (input.type === "radio") {
      const groupKey = `${input.name}::${res.value}`;
      if (doneRadioGroups.has(groupKey)) return;
      const group = [...(input.name
        ? document.querySelectorAll(
          `input[type="radio"][name="${CSS.escape(input.name)}"]`)
        : [input])];
      if (group.some((radio) => radio.checked)) return;
      const words = optionWordsFor(res.kind, String(res.value));
      const matches = !res.kind
        ? (radioLabel) => context.optionFor(
          radioLabel, [String(res.value)]) !== null
        : (radioLabel) => words.some((pattern) => pattern.test(radioLabel));
      // Gender picks ONE button by its own words and the value's ordered list.
      const genderPick = res.kind === "gender"
        ? context.bestGenderItem(group, labelFor, String(res.value)) : null;
      for (const radio of group) {
        const radioLabel = labelFor(radio);
        if (res.kind === "gender" ? radio !== genderPick : !matches(radioLabel)) continue;
        clickControl(radio);
        // The verdict, not the attempt — see `stillChecked` (autofill.js). A
        // disclosure the page threw away must not be recorded as one the user
        // made, which matters more here than anywhere else in the engine.
        const stuck = stillChecked(radio);
        // A gender button reports its own words; the joined label carried the
        // legend ("nonbinary | wd_gender | gender (such as…").
        const shown = res.kind === "gender" ? context.ownWords(radioLabel) : radioLabel;
        record({ label, value: shown.slice(0, 40) }, stuck);
        observe(input, kind, labelText, rule, stuck ? "filled" : "not_stuck");
        doneRadioGroups.add(groupKey);
        break;
      }
      return;
    }

    if (input.type === "checkbox") {
      // TWO shapes wear the same control, and only one of them was handled.
      //
      // A multi-category question (race) renders one box per category and is
      // matched from `optionList`. A SINGLE-CHOICE question renders as a group
      // of boxes behaving like radios — Workday's disability self-ID is three
      // of them ("Yes, I have a disability…", "No, I do not…", "I do not want
      // to answer"), each labelled with the whole answer and sharing an id
      // suffix. That rule carries a `kind` and no `optionList`, so the lookup
      // below returned nothing and every one of those boxes reported
      // `skipped_checkbox` — the field was never filled with the opt-in ON.
      //
      // The kind-based match is the same one the RADIO branch already makes,
      // which is what these boxes are impersonating.
      //
      // Except the two gender answers whose words are UNANCHORED (a non-binary
      // option is worded a dozen ways): a box's label carries the question as
      // well as its option, so those boxes are left for the user.
      const unanchored = rule.kind === "gender"
        && ["non_binary", "self_describe"].includes(String(res.value));
      const option = context.optionFor(labelText, rule.optionList)
        ?? (rule.kind && !unanchored && optionWordsFor(rule.kind, String(res.value))
          ?.some((pattern) => pattern.test(labelText))
          ? String(res.value) : null);
      if (!option) {
        observe(input, kind, labelText, rule, "skipped_checkbox");
        return;
      }
      // One answer per question, and never over the top of an existing one.
      // A radio group gets this from the browser; a checkbox group does not,
      // so ticking ours beside an answer already on the page would submit two
      // contradictory disclosures. `singleChoice` is the rule's own vocabulary
      // — a multi-category question is allowed several ticks and must not be
      // caught by this.
      const singleChoice = !rule.optionList?.length;
      if (singleChoice) {
        const groupKey = `eeo:${rule.id}`;
        if (doneRadioGroups.has(groupKey)) return;
        const siblings = eeoCheckboxGroup(input);
        if (siblings.some((box) => box.checked)) return;
        doneRadioGroups.add(groupKey);
      }
      // click() toggles, so an existing answer must never be cleared.
      if (!input.checked) {
        clickControl(input);
        const ticked = stillChecked(input);
        observe(input, kind, labelText, rule,
          ticked ? "filled" : "not_stuck");
        record({
          label,
          value: option.slice(0, 40),
          note: ticked ? undefined : "may not have registered, check the box",
        }, ticked);
      }
      return;
    }

    // Workday renders every voluntary-disclosure dropdown as a listbox button
    // whose visible text is the answer. Answer-preserving like the rest: a
    // button already showing something — including a decline — is the user's
    // own disclosure and is never re-driven.
    if (isListboxButton) {
      if (!listboxButtonEmpty(input)) return;
      const popup = await fillListboxButton(input, res);
      observe(input, kind, labelText, rule,
        popup.ok ? "filled" : "combobox_snap_failed");
      record({
        label,
        value: popup.text,
        note: popup.ok ? undefined : "no matching option, choose it manually",
      }, popup.ok);
      return;
    }

    if (isCombobox) {
      // Search widgets are also answer-preserving: do not even drive one that
      // already carries the user's disclosure.
      if (input.value) return;
      const combo = await fillCombobox(input, res);
      observe(input, kind, labelText, rule,
        combo.ok ? "filled" : "combobox_snap_failed");
      record({
        label,
        value: combo.text,
        note: combo.ok ? undefined : "no matching option, enter it manually",
      }, combo.ok);
      return;
    }

    if (!input.value) {
      const answer = context.textAnswer(rule, res.value, labelText);
      if (answer.outcome) {
        observe(input, kind, labelText, rule, answer.outcome);
        return;
      }
      const outcome = await commitValue(input, answer.text);
      const stuck = commitOk.has(outcome);
      observe(input, kind, labelText, rule, outcome);
      record({
        label,
        value: answer.text,
        note: stuck ? undefined : "may not have registered, check the field",
      }, stuck);
    }
  }

  ns.createEeoContext = createEeoContext;
  ns.shouldSkipEeoControl = shouldSkipEeoControl;
  ns.handleEeoControl = handleEeoControl;
})();
