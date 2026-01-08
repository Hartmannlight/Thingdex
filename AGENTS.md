# Repository Guidelines

## Project Structure & Module Organization
- Current repository is a project specification, not an implementation. Key files:
  - `pyproject.toml`: Python project metadata (requires Python >= 3.13).
  - `project-idea.md`: Architecture and API design notes.
- No `src/`, `tests/`, or `assets/` directories exist yet. When implementation starts, keep application code in `src/` and tests in `tests/` to stay standard with Python tooling.

## Build, Test, and Development Commands
- Dependency management is configured for Poetry via `pyproject.toml`.
  - Example: `poetry install` to create the environment once dependencies are defined.
- No build, run, or test scripts are committed yet. Add explicit commands to this file once the first runnable service or tests land.

## Coding Style & Naming Conventions
- No formatter or linter is configured yet.
- Until tooling is added, use 4-space indentation, type hints where reasonable, and snake_case for Python identifiers. Keep module names short and descriptive (e.g., `inventory_service.py`, `locations_api.py`).

## Testing Guidelines
- No test framework is set up yet.
- When tests are added, place them under `tests/` and name files `test_*.py`. Provide a single entry-point command (e.g., `poetry run pytest`) and document it here.

## Commit & Pull Request Guidelines
- Git history is not available in this workspace, so commit conventions cannot be inferred.
- Use clear, imperative commit subjects (e.g., "Add locations API schema") and include context in the body for non-trivial changes.
- For pull requests, include a short summary, mention any related issue IDs, and note manual testing steps.

## Architecture Notes
- The intended stack and data model are described in `project-idea.md`.
- If implementation diverges from the design, update `project-idea.md` or add a concise `ARCHITECTURE.md` to keep expectations aligned.
