/* Maestro CS Companion — voluntary EEO and demographics solver. */

// ============================================================
// WHAT THIS FILE PUBLISHES
// ============================================================
(() => {
  const ns = (window.careerStudioCompanion ??= {});

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
    };
    const yesNo = (value) =>
      (value === true ? "yes" : value === false ? "no" : value);
    const isEeoLabel = (label) =>
      /veteran|disab|hispanic|latino|gender|\bsex\b|race|ethnic/i.test(label);

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
      { id: "gender", re: /gender|^sex\b/i, value: e.gender, kind: "gender" },
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
      if (kind === "gender") return optionWords[value] ?? optionWords.decline;
      return null;
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

    return { rules, isEeoLabel, optionWordsFor, optionFor, canonicalOptionText };
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
      for (const radio of group) {
        const radioLabel = labelFor(radio);
        if (!matches(radioLabel)) continue;
        clickControl(radio);
        // The verdict, not the attempt — see `stillChecked` (autofill.js). A
        // disclosure the page threw away must not be recorded as one the user
        // made, which matters more here than anywhere else in the engine.
        const stuck = stillChecked(radio);
        record({ label, value: radioLabel.slice(0, 40) }, stuck);
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
      const option = context.optionFor(labelText, rule.optionList)
        ?? (rule.kind && optionWordsFor(rule.kind, String(res.value))
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
      const outcome = await commitValue(input, String(res.value));
      const stuck = commitOk.has(outcome);
      observe(input, kind, labelText, rule, outcome);
      record({
        label,
        value: String(res.value),
        note: stuck ? undefined : "may not have registered, check the field",
      }, stuck);
    }
  }

  ns.createEeoContext = createEeoContext;
  ns.shouldSkipEeoControl = shouldSkipEeoControl;
  ns.handleEeoControl = handleEeoControl;
})();
