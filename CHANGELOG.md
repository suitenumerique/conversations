# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- 🧱(files) allow to use S3 storage without external access #849

### Changed

- 🏗️(back) migrate to uv

## [0.0.12] - 2026-01-27

### Fixed

- ⚡️(front) performance improvements on chat input
- 💄(front) i18n and standardize pdf parsing display

### Removed

- 🔥(chat) consider PDF documents as other kind of documents #234

## [0.0.11] - 2026-01-16

### Changed

- 📦️(front) update react
- ✨(chat) Generate and edit conversation title


### Fixed

- 🐛(e2e) fix test-e2e-chromium
- 🐛(back) fix system prompt compatibility with self-hosted models #200
- ⚰️(back) remove dead code and unused files
- 🐛(back) prevent tool call timeouts

### Removed

- 🔥(chat) remove thinking part from frontend #227

## [0.0.10] - 2025-12-15

### Added

- ✨(front) add retry button

### Fixed

- 🐛(front) fix long user messages
- 🐛(front) fix "Maximum update depth exceeded" error in Chat component
- 🐛(front) fix parsing documents display
- 🐛(front) fix opacity input in error
- 🐛(front) resolve React hydration errors
- 🚑️(user) allow longer short names #182

## [0.0.9] - 2025-11-17

### Added

- ✨(front) add code copy button
- ✨(RAG) add generic collection RAG tools #159

### Fixed

- 🔊(langfuse) enable tracing with redacted content #162

## [0.0.8] - 2025-11-10

### Fixed

- 🦺(front) Fix send prohibited file types
- 🐛(front) fix target blank links in chat #103
- 🚑️(posthog) pass str instead of UUID for user PK #134
- ⚡️(web-search) keep running when tool call fails #137
- ✨(summarize): new summarize tool integration #78

### Removed

- 🔥(posthog) remove posthog middleware for async mode fix #146

## [0.0.7] - 2025-10-28

### Fixed

- 🚑️(posthog) fix the posthog middleware for async mode #133

## [0.0.6] - 2025-10-28

### Fixed

- 🚑️(stats) fix tracking id in upload event #130

## [0.0.5] - 2025-10-27

### Fixed

- 🚑️(drag-drop) fix the rejection display on Safari #127

## [0.0.4] - 2025-10-27

### Added

- ♿️(a11y) improve accessibility #135
- 🌐(i18n) add dutch language #117

### Changed

- ⚡️(asgi) use `uvicorn` to serve backend #121

### Fixed

- 🐛(front) fix mobile source
- 🐛(attachments) reject the whole drag&drop if unsupported formats #123

## [0.0.3] - 2025-10-21

### Fixed

- 🚑️(web-search) fix missing argument in RAG backend #116

## [0.0.2] - 2025-10-21

### Added

- ✨(front) add drag'n drop file
- ✨(activation-codes) register users also on Brevo #98
- 📈(posthog) add `sub` field to tracking #95

### Changed

- 🔧(front) change links feedback tchap + settings popup
- 🐛(front) code activation fix session end #93
- 💬(wording) error page wording #102
- ⚡️(web-search) allow to override returned chunks #107
- 🐛(activation-codes) create contact in brevo before add to list #108
- ⚗️(summarization) add system prompt to handle tool #112

## [0.0.1] - 2025-10-19

### Changed

- 🎨(front) activation page footer
- 👷(front) change size small modal
- 🎨(front) retour ui global
- 👷(front) fix button scrollDown
- 💥(front) disable input when error occurred
- 👷(front) fix scroll
- 🐛(front) fix left panel status + fix scroll
- 🐛(llm) add is_active field and persist chat preference
- ✨(frontend) add LLM selection in chat input #53
- 🎨(front) fix width chat container
- 🎨(front) fix width chat container #55
- 🐛(front) fix button search web on new conversation
- 🎨(front) improvement search input scroll
- ✨(404) fix front 404 page
- ✅(chat) add frontend feature flags #29
- 🎨(front) change list attachment in chat
- 🎨(front) move emplacement for attachment
- 🎨(ui) retour ui sources files
- ✨(ui) fix retour global ui
- 🐛(fix) broken staging css
- 🎨(alpha) adjustment for alpha version
- ✨(ui) delete flex message
- ✅(front) add enabled/disabled conversation analysis
- 🎨(front) amelioration chat ux
- 🎨(front) global layout modification
- ✨(front) global layout UI
- ♻️(chat) rewrite backend using Pydantic AI SDK #4
- 🗃️(chat) enforce messages stored JSON format #6
- 🐛(chat) UI messages must have a unique identifier #6
- ✨(llm) allow configuration from JSON file #22
- 💥(agent) replace routing w/ tool calls #40
- 🧱(storage) upload the user documents into S3 #86

### Added

- 🎉(conversations) bootstrap backend & frontend #1
- ✨(web-search) add RAG capability to do web search #7
- ✨(chat) add document RAG on document uploaded by user #8
- ✨(backend) allow use to stop conversation streaming #14
- 🐛(agent) add the current date in the system prompt #18
- ✨(backend) add feature flags from posthog #13
- ✨(user) allow to use conversation data for analytics #23
- ✨(chat) enforce response in user language #24
- 📈(langfuse) add light instrumentation #26
- 🚑️(agent) allow Mistral w/ vLLM & tools #36
- ✨(web-search) add Brave search tool #47
- ✨(models) add mistral support & customization #51
- 🐛(web-search) add summarization to Brave results #58
- ✨(langfuse) allow user to score messages from LLM #6
- ✨(onboarding) add activation code logic for launch #62
- 💄(chat) add code highlighting for LLM responses #67


[unreleased]: https://github.com/suitenumerique/conversations/compare/v0.0.12...main
[0.0.12]: https://github.com/suitenumerique/conversations/releases/v0.0.12
[0.0.11]: https://github.com/suitenumerique/conversations/releases/v0.0.11
[0.0.10]: https://github.com/suitenumerique/conversations/releases/v0.0.10
[0.0.9]: https://github.com/suitenumerique/conversations/releases/v0.0.9
[0.0.8]: https://github.com/suitenumerique/conversations/releases/v0.0.8
[0.0.7]: https://github.com/suitenumerique/conversations/releases/v0.0.7
[0.0.6]: https://github.com/suitenumerique/conversations/releases/v0.0.6
[0.0.5]: https://github.com/suitenumerique/conversations/releases/v0.0.5
[0.0.4]: https://github.com/suitenumerique/conversations/releases/v0.0.4
[0.0.3]: https://github.com/suitenumerique/conversations/releases/v0.0.3
[0.0.2]: https://github.com/suitenumerique/conversations/releases/v0.0.2
[0.0.1]: https://github.com/suitenumerique/conversations/releases/v0.0.1
