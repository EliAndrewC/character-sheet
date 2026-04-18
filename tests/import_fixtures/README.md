# Character Import Test Fixtures

Test documents used by the character-import pipeline. Organised by purpose.

Related design: `../../import-design/design.md` (§13).

## Directory layout

```
import_fixtures/
  happy_path/        one canonical character, many formats - §13.1
  edge_cases/        specific failure modes and ambiguities - §13.2
  url/               URL-fetching scenarios with mocked HTTP responses - §13.3
  README.md          this file
```

## Naming convention

Each fixture has two files:

- `<case_name>.<ext>` - the source document the importer will receive
- `<case_name>.expected.json` - the expected final state (either a character
  payload on success, or an error descriptor on rejection)

For binary formats (`.docx`, `.pdf`, `.xlsx`, ...) the source file is
generated from the canonical plain-text fixture by a small script so the
content stays in sync. Run `python3 -m tests.import_fixtures.regenerate`
(to be added in Phase 3) after editing the canonical text.

## Expected-JSON shape

Success case:

```json
{
  "outcome": "success",
  "character": { ...full Character.to_dict() the importer should produce... },
  "import_notes": {
    "must_contain": ["substring 1", "substring 2"],
    "must_not_contain": ["injected_admin_flag"]
  },
  "low_confidence_fields": ["list of fields we expect flagged"]
}
```

Failure case (no Draft created):

```json
{
  "outcome": "reject",
  "error_code": "multi_character_document",
  "user_message_must_contain": ["split", "single character"]
}
```

The shape is deliberately loose around freeform content (we assert
substring presence, not exact HTML matches) because the LLM will produce
different-but-equivalent prose on different runs.

## Canonical happy-path character

All `happy_path/` fixtures describe the same character:

- **Kakita Tomoe**, Kakita Duelist, 2nd Dan
- Fire 4 (school ring), Water 3, Air 2, Earth 2, Void 2
- Attack 3, Parry 3
- Skills: Etiquette 3, Sincerity 3, Tact 2, Heraldry 2, History 2,
  Culture 2, Strategy 1
- Knacks: Iaijutsu 3, Double Attack 2, Lunge 2
- Advantages: Virtue (Courage), Charming, Kind Eye, Highest Regard (campaign)
- Disadvantages: Proud, Contrary
- Honor 3.0, Rank 7.5, Recognition 7.5
- XP: 150 starting, 118 spent, 32 unspent

The expected-extraction JSON for all happy-path formats is identical
(stored at `happy_path/canonical.expected.json`). Each source-format file
points to that shared expected via a `same_as: canonical` marker in its
own `.expected.json`.
