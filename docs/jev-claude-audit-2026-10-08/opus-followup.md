Requested and confirmed model: claude-opus-5-5. Effort: high. Follow-up supplied the synthetic Jev outcomes and prior review, with no additional project source.

# ZameenRentals AI review: revised

**What changed.** My earlier Jev section treated Jev as a typed, deterministic authority. That was wrong. Jev is a stochastic classifier that returns probabilities, and a probability can't be the final word on a fact. This revision uses only the facts you supplied about jev-1.13.0. I haven't seen any Jev source or integration code.

## What the live test shows

- **The pass rate is too uncertain to rely on.** 7/10 has a Wilson 95% interval of roughly 40–89%.
- **No single threshold separates true from false.** The injected "bachelor" (.85) scored higher than both true explicit claims: separate gate (.79) and solar panels (.45).
  - A threshold that rejects the injection also drops both true claims.
  - A threshold that keeps the true claims also admits the injection.
- **Text-presence checks don't stop injection.** The word "bachelor" literally appears in the advertisement. So "the quote is a substring of the description" passes the injected fact.
  - Evidence checking must test that the span is a *claim about the property*, not just that the text exists.

## Position on the Codex proposal

I agree that deterministic validation plus evidence spans should be the authority. I'd tighten the roles:

- **Rules (free baseline, built first).** Per-language lexicons and patterns (English, Roman Urdu, Urdu) for each fact.
  - Examples: "solar", "سولر", "separate gate/alag gate", "family only", "bachelors allowed".
  - This sets the bar that the models must beat.
- **Jev.** Cheap offline tagging, used for **routing** rather than deciding: which listings need extraction or review.
  - Its scores should be calibrated per fact before being used as routing thresholds.
- **Claude.** Structured multilingual extraction, run only on listings that rules and Jev leave ambiguous or conflicting.
  - Listing text is passed as quoted data.
  - Output must include a verbatim span.
  - Claude never sets a final value.
- **Validator (the authority).** It accepts a fact only if:
  - the span is in the description;
  - the span matches a claim pattern for that fact;
  - the span isn't inside instruction-like text ("ignore instructions", "output …", schema field names like `tenant_fit`);
  - rules and models don't contradict each other.
  - Otherwise the fact is stored as **unknown** or **conflicting**, never guessed.

## Priorities, reordered

**0. Prerequisite reliability fixes** (from the approved review):

- D1: an off-list AI area survives the `pop`.
- D2: the thread isn't cancelled on timeout, so budgets need to be set explicitly.
- D4: `furnished=false` is ignored.
- D5: an inverted price range causes a 400.

These cause wrong or failed searches today. Each is small and can be tested deterministically.

**1. Evidence-backed listing facts.** I'd move this first because the other two depend on it.

- Store a three-state value (`yes`/`no`/`unknown`, plus `conflicting`) with span, source (rule/jev/claude), model version and `detail_hash`.
- **Gate, per fact × city × language:**
  - Precision at the shipping operating point is at least a target you set (e.g. ≥95%), with the CI lower bound reported.
  - It must beat the rules baseline, or ship rules alone.
  - **Injection success is 0** on a dedicated adversarial set (instruction text, field names, contradictory claims).
  - Coverage is reported. Rarely present facts get no filter.
  - Every Jev version change (it's pinned at 1.13.0) reruns the gate.

**2. Compositional multilingual search.** For example, "Gulberg mein solar wala 2 bed, family".

- It can start in parallel on existing structured fields: area, beds, price, size. Fact-based terms ("solar", "family") wait for #1.
- Claude proposes the query parse. Area must come from a deterministic candidate list (earlier opportunity 2), and gaz/sq yd units and N+ ranges must be handled (D4).
- Unknown facts appear as a "may match" group, not silently included or excluded.
- **Gate:** a golden set across city × script × compositional feature, including D6's Urdu-script Lahore and Islamabad queries.
  - Zero off-list areas.
  - Field accuracy ≥ regex in every cell.
  - Measured p95 latency and fallback rate.

**3. Personalized comparison with explicit unknowns.**

- The renter's stated priorities weight the verdict. Unknowns are shown as "not stated in listing" and are never scored as `no`.
- Refuse cross-type value verdicts. Today `buildVerdict` compares Rs/marla across a room and a house.
- Claude may explain the verdict only from fields and reason codes the deterministic comparator returns.
- **Gate:**
  - Replaying logged inputs reproduces the same verdict.
  - Explanations cite no field outside the comparator's output.
  - A user study or click-through measure shows unknowns aren't hidden.

**Challenge.** If the fact gate fails for most facts, #3 reduces to price/size/beds plus a column of unknowns. It still has honest value, but you should decide that before investing in it.

## Uncertainty handling

- **Abstain band:** scores between calibrated low and high cutoffs go to Claude or human review, not to a default.
- **Small samples:** report CIs. Don't call a fact shippable from fewer than about 100 labelled examples per cell.
- **Shadow mode first:** log rule/Jev/Claude disagreement with phone-like digit runs redacted, and only then enable filters.

## Code-review items still standing

Unchanged from the approved review:

- D1–D5 as above.
- D6: Urdu matching is gated to Karachi.
- D7: prompt hygiene (temperature, `city_hint` examples, hard-coded model ID).
- D8: a curated landmark loses to the model's guess.
- D9: observability (usage, parser source, `exc_info`).

The "typed arbiter" seam I noted, `_reconcile_ai_area` plus the post-validations, is still where the **deterministic validator** belongs. I no longer suggest it as a home for Jev.