# Contributing to Wanderbound

## Translations

Start with interface translations so people can upload Polarsteps trips and edit
albums in their language. You do not need to develop app features to translate.

### Interface

Use [`en.json`](frontend/src/i18n/locales/en.json) as the reference for files in
[`frontend/src/i18n/locales/`](frontend/src/i18n/locales/).
For a new language:

1. Create a JSON file named after its language code, such as `es.json`.
2. Import the file in [`frontend/src/i18n/index.ts`](frontend/src/i18n/index.ts).
3. Add the language to the `messages` object in that file.

Preserve the JSON structure and message names.
Keep placeholders such as `{n}` and linked messages such as `@:common.retry` intact.
Keep the `|` separators between plural forms. Use the forms appropriate for your language.

Use concise, natural labels.
Check translated text in the interface for clipping and text direction.

### Demo album

You can translate the demo album separately from the interface.
Add a language-code JSON file in [`fixtures/demo/i18n/`](fixtures/demo/i18n/).
Use its existing translation structure.

Use the English content in [`fixtures/demo/trip/`](fixtures/demo/trip/) as the reference.
Translate the album title and subtitle, step descriptions, and place names.
Keep step IDs unchanged so translations match the original steps.

## Code contributions

Discuss substantial features in an issue before starting.
Keep each PR focused. Describe its purpose and link to the related issue, if any.

Use the [development setup](README.md#development) in the README.
AI assistants must read the applicable [`AGENTS.md`](AGENTS.md),
[`frontend/AGENTS.md`](frontend/AGENTS.md), and [`backend/AGENTS.md`](backend/AGENTS.md) files.
For UI changes, read the [design guidance](frontend/DESIGN.md).
Before changing tests, read the [test policy](.claude/rules/testing.md).
Run the checks relevant to your change with the repository's `mise` tasks.

Report vulnerabilities through the [security policy](SECURITY.md).
