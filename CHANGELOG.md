# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- 🐛(fix) source links should open a new tab
- 💄(ui) codeblock light mode
- ✨(front) allow typing while LLM is generating a response
- ⬆️(dependencies) update back and front dependencies
- 💄(ui) new header
- ✨(back) add debug mode setup for local development
- ⬆️(dependencies) switch base docker image to upgrade markitdown

### Fixed

- 💄(ui) little fix margin top

## [0.0.15] - 2026-03-31

### Added

- ✨(back) add projects with custom LLM instructions
- ✨(front) projects management UI
- 🥚(front) add April Fools day prank

### Changed

- ⬆️(dependencies) upgrade Next.js 15 to 16, upgrade python dependencies
- ✨(front) rich text copy for Word/Docs paste

### Fixed

- 🐛(back) add missing color option for project colors
- 💄(project) ui fix project
- 💄(ui) ui fix button css
- 💄(ui) ui fix model selector css

## [0.0.14] - 2026-03-11

### Added

- ✨(user) allow disabling automatic internet search
- ✨(search) add searchModal and modify leftPanel
- ✨(waffle) hide the waffle if not fr theme
- ✨(front) allow pasting an attachment from clipboard
- ✨(array) temporarily adjust array

### Changed

- ⚡️(front) optimize streaming markdown rendering performance
- ⬆️(back) update pydantic-ai
- ♻️(chat) refactor AIAgentService for readability and maintainability
- 🚸(oidc) ignore case when fallback on email #281
- ⬆️(back) update pillow, django-pydantic-field, pypdf
- ♻️(front) migrate from ESLint 8 to ESLint 9 flat config
- ⬆️(back) update django and pypdf

### Fixed

- 💚(docker) vendor mime.types file instead of fetching from Apache SVN
- 🚑️(back) fix mime type for pptx
- 🐛(front) fix math formulas and carousel translations
- 🐛(helm) reverse liveness and readiness for backend deployment
- 🐛(front) fix dark mode styling on chat messages
- 🐛(front) fixed inverted toast for setting changes

## [0.0.13] - 2026-02-09

### Added

- 💄(front) ui fix : update ui-kit
- ✨(front) add persistent darkmode
- ✨(front) add ui kit #240
- 🧱(files) allow to use S3 storage without external access #849
- ✨(backend) add FindRagBackend #209
- ⬆️(back) update dependencies
- ✨(back) use adaptive parsing for pdf documents

### Changed

- 💄(darkmode) change color feedback button
- 🏗️(back) migrate to uv
- ♻️(front) optimize syntax highlighting bundle size

### Fixed

- 🐛(back) cast collection Ids to API expected types

## [0.0.12] - 2026-01-27

### Fixed

- ⚡️(front) performance improvements on chat input
- 💄(front) i18n and standardize pdf parsing display

### Removed

- 🔥(chat) consider PDF documents as other kind of documents #234

## [0.0.11] - 2026-01-16

### Changed

- 📦️(front) update react
- ✨(chat) generate and edit conversation title

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

[unreleased]: https://github.com/suitenumerique/conversations/compare/v0.0.15...main
[0.0.15]: https://github.com/suitenumerique/conversations/releases/v0.0.15
[0.0.14]: https://github.com/suitenumerique/conversations/releases/v0.0.14
[0.0.13]: https://github.com/suitenumerique/conversations/releases/v0.0.13
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
