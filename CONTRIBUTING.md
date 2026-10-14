# Contributing to Wanderbound

Report vulnerabilities through the [security policy](SECURITY.md).

## Translations

### Interface

Use [`en.json`](frontend/src/i18n/locales/en.json) as the reference for files in [`frontend/src/i18n/locales/`](frontend/src/i18n/locales/).

1. Create a JSON file named after its language code, such as `es.json`.
2. Import the file in [`frontend/src/i18n/index.ts`](frontend/src/i18n/index.ts).
3. Add the language to the `messages` object in that file.

Keep placeholders such as `{n}` and linked messages such as `@:common.retry` intact.
Keep the `|` separators between plural forms. Use the forms appropriate for your language.

### Demo album

You can translate the demo album separately from the interface.
Add a language-code JSON file in [`fixtures/demo/i18n/`](fixtures/demo/i18n/).
Use the English content in [`fixtures/demo/trip/`](fixtures/demo/trip/) as the reference.

## Code contributions

Discuss substantial features in an issue before starting.
Keep each PR focused. Describe its purpose and link to the related issue, if any.

Use the [development setup](README.md#development) in the README.
AI assistants must read the applicable [`AGENTS.md`](AGENTS.md).
