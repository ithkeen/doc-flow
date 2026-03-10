# Config Module Design

## Goal

Create a centralized configuration management module at `src/config/` that loads settings from `.env` files and environment variables with type-safe validation and fail-fast behavior.

## Approach

Use `pydantic-settings` (`BaseSettings`) for declarative config with automatic `.env` loading, type validation, and nested model support.

## File Structure

```
src/config/
├── __init__.py      # Export `settings` singleton
└── settings.py      # Pydantic Settings definitions
```

## Configuration Groups

| Group | Env Prefix | Required Fields | Optional Fields |
|-------|-----------|-----------------|-----------------|
| LLM | `LLM_` | `api_key` | `base_url` (default: openai), `model` (default: gpt-4) |
| LangSmith | `LANGSMITH_` | none | `tracing`, `api_key`, `project`, `endpoint` |
| Root | — | none | `docs_output_dir` (default: ./docs) |

## Validation

- `LLM_API_KEY` is required — missing triggers `ValidationError` at startup (fail-fast).
- All LangSmith fields are optional with sensible defaults.
- `DOCS_OUTPUT_DIR` defaults to `./docs`.

## Usage

```python
from src.config import settings

settings.llm.api_key
settings.llm.model
settings.docs_output_dir
settings.langsmith.tracing
```

## Dependencies

- Add `pydantic-settings` to `pyproject.toml`.

## Design Decisions

- **Singleton pattern**: One `settings` instance created at module load, reused via import.
- **Nested models via `env_nested_delimiter="_"`**: Maps `LLM_API_KEY` → `settings.llm.api_key`.
- **No runtime mutation**: Config is read-only after initialization.
