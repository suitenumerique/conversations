# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- ✨(ui) delete flex message

### Changed

- ✅(front) add enabled/disabled conversation analysis
- 🎨(front) amelioration chat ux
- 🎨(front) global layout modification
- ✨(front) global layout UI
- ♻️(chat) rewrite backend using Pydantic AI SDK #4
- 🗃️(chat) enforce messages stored JSON format #6
- 🐛(chat) UI messages must have a unique identifier #6
- ✨(llm) allow configuration from JSON file #22

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
- 💩(chat) add frontend feature flags #29


[unreleased]: https://github.com/numerique-gouv/conversations/compare/HEAD...main
