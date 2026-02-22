# AGENTS.md

## Project Basics
- Stack: Android, Kotlin, Jetpack Compose
- Dependency Injection: Koin
- Navigation: Jetpack Navigation (Navigation3)
- Networking: Retrofit + OkHttp
- AI Router: routerai.ru (OpenAI-compatible API)
- Architecture: Clean Architecture (domain/data/presentation layers)

## Conventions
- For Compose functions, add `@Preview`.
- One file, one class.
- Prefer DI (Koin) for reusable dependencies instead of constructing them in-place.

## Project Summary
- Android app in Compose to send prompts and receive responses from RouterAI (OpenAI-compatible).
- Main screen: prompt input, send button, response display (simple Markdown: headings + bold).
- Supports streaming responses (SSE) and an option to disable streaming in settings.
- Bottom sheet settings: `max_tokens`, `temperature`, `stop`, `stream`.
- API key from `BuildConfig` via env `ROUTERAI_API_KEY`, with UI warning when missing.
- Clean Architecture (domain/data/presentation) and DI via Koin.
