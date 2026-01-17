# Repository Guidelines

## Project Structure & Module Organization
- Current repository is a project specification, not an implementation. Key files:
  - `pyproject.toml`: Python project metadata (requires Python >= 3.13).
  - `project-idea.md`: Architecture and API design notes.
- Tests live in `tests/` and should continue to follow `test_*.py` naming.

## Build, Test, and Development Commands
- Dependency management is configured for Poetry via `pyproject.toml`.
  - Example: `poetry install` to create the environment once dependencies are defined.
- Run the test suite with: `poetry run pytest`

## Coding Style & Naming Conventions
- No formatter or linter is configured yet.
- Until tooling is added, use 4-space indentation, type hints where reasonable, and snake_case for Python identifiers. Keep module names short and descriptive (e.g., `inventory_service.py`, `locations_api.py`).

## Testing Guidelines
- Tests use pytest and live under `tests/` with `test_*.py` naming.
- Default database for tests comes from `THINGDEX_TEST_DATABASE_URL` or `DATABASE_URL`.

## Commit & Pull Request Guidelines
- Git history is not available in this workspace, so commit conventions cannot be inferred.
- Use clear, imperative commit subjects (e.g., "Add locations API schema") and include context in the body for non-trivial changes.
- For pull requests, include a short summary, mention any related issue IDs, and note manual testing steps.

## Architecture Notes
- The intended stack and data model are described in `project-idea.md`.
- If implementation diverges from the design, update `project-idea.md` or add a concise `ARCHITECTURE.md` to keep expectations aligned.
