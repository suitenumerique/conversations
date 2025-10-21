# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- ✨(front) add drag'n drop file
- ✨(activation-codes) register users also on Brevo #98

### Changed

- 💬(text) error page wording
- 🐛(front) code activation fix session end #93


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


[unreleased]: https://github.com/suitenumerique/conversations/compare/v0.0.1...main
[0.0.1]: https://github.com/suitenumerique/conversations/releases/v0.0.1
