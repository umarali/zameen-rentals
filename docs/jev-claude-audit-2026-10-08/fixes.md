The Jev and English/Urdu search fixes from PRs #14 and #22 are combined with the UI branches in the [tested integration](../integration-validation-2026-10-08.md). The notes below record validation of the individual fixes before integration.

Jev now invalidates tags whenever the classifier's source fields change. An atomic SQL comparison prevents an old in-flight response from restoring stale tags. Insert, replace and delete paths are covered. Existing databases gain nullable version/hash columns without dropping their tag table; legacy tags are hidden until rescored. Reads and filters require the current model and pipeline version. Even the default browse cache refreshes tags before responding.

The provider client validates finite probability ranges, types, choice values, rubric bounds, response completeness, usage and the requested model. Malformed JSON becomes a typed provider failure. Fractional scores remain supported, as required by the [official Score contract](https://docs.typesafe.ai/primitives/score). Provider failures no longer log response bodies.

Amenity objects retain their values, including `None`, so a missing backup-power value no longer becomes an affirmative-looking amenity. Production and evaluation use the same normalization. Revised questions treat advertisement text as data. A conservative English/Urdu instruction detector withholds tags from suspect ads; incomplete descriptions or omitted amenities also produce unknown tags. These checks reduce the tested failure modes; they are not a universal prompt-injection defense or verification that an advertiser's claim is true.

The evaluation tool now excludes blank labels independently for each field, rejects invalid labels, recalculates weights on each field's evaluated subset, and reuses predictions only when their source, model, formatted input and pipeline match. Old prediction files are treated as stale. The same publication guard runs in production and model evaluation.

Claude Opus 5.5 at high effort reviewed the proposed fixes, and its recommendations were incorporated. A second patch-only review did not return after more than twelve minutes and was stopped; it is not counted as a completed review. Its advice strengthened source-column comparisons, trigger coverage, migration behavior and evaluation consistency. I verified provider-specific suggestions against the documentation; I did not adopt its incorrect integer-only Score suggestion.

The search branch preserves main's Haiku 5.5 default, `ZR_PARSE_MODEL` configuration, candidate-area prompts, persistent cache and daily spend controls. Native async requests now support deadline cancellation, and provider failures record only the exception type. The prompt version was bumped so earlier cached parses refresh.

Search remains focused on English and Urdu. The fallback parser now recognizes common Urdu neighborhoods in Lahore and Islamabad, Urdu sector names with Urdu digits, Urdu bedroom ranges, and marla/kanal/gaz size units. All aliases are city-specific and are tested against the actual area dictionaries. Existing language handling was preserved rather than removed.

Validation:

- Search branch after integrating current main: 694 tests passed, 2 optional model-transcription tests skipped.
- Headless browsers: 36 passed across desktop and mobile, including English/Urdu searches in all three cities.
- Jev branch after integrating current main: 760 tests passed, 2 skipped. The targeted Jev suite also passes all 89 tests, including numeric-overflow cases.
- Live Jev: 15/15 synthetic English/Urdu cases passed with the actual revised questions and publication guard, without lowering thresholds. [Responses and raw probabilities](jev-fixed-live.json) are saved for inspection. This is a development smoke test, not proof of representative accuracy.
- The previous 12 failing Jev regression checks all pass.

Use the [manual and automated test guide](testing.md) to reproduce the search behavior or verify Jev without touching production data. This audit could not run live Claude search benchmarking because its API-key attempt returned insufficient credits; the successful Opus collaboration used the existing Claude Code subscription.
