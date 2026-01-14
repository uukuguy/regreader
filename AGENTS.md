# Repository Guidelines

## Project Structure & Module Organization
- `src/regreader/`: library code; `agents/` hosts Claude/Pydantic/LangGraph flows, `mcp/` serves MCP tools, `parser/` handles Docling ingestion, `index/` controls retrieval backends, `storage/` manages page persistence, `cli.py` is the Typer entrypoint.
- `scripts/`: utilities like `reindex_document.py`, `verify_chapters.py`, and `stats_headings.py` for maintenance and debugging.
- `data/` and `outputs/`: ingested regulation data, backups, and generated artifacts (git-ignored); keep large files local and reference paths in PRs if relevant.
- `tests/`: pytest suites (e.g., heading detection in `tests/test_heading_detection.py`, scenarios in `tests/main/`).
- `docs/` and `README*.md`: architecture and usage notes for contributors and operators.

## Build, Test, and Development Commands
- `make install-dev` (or `make install-all` for optional backends) uses `uv sync`; requires Python 3.12.
- `make lint` / `make lint-fix`, `make format` / `make format-check` run Ruff linting/formatting.
- `make test`, `make test-cov`, `make test-fast` run pytest variants through `uv run`.
- `make serve` (SSE) or `make serve-stdio` start the MCP server; `make chat REG_ID=... AGENT=...` launches the CLI agent.
- `make ingest FILE=... REG_ID=...` loads a document; `make inspect PAGE_NUM=...` or `make search QUERY=...` validates parsing and retrieval.
- `make build` builds the package; `make clean`/`clean-data` purge artifacts (data deletion is destructive).

## Coding Style & Naming Conventions
- Python only; prefer 4-space indents and type hints. Functions/modules stay `snake_case`; classes use `CamelCase`.
- Ruff enforces style (`line-length = 100`, `py312` target, `select = ["E","F","I","N","W","UP"]`); run `make format` before PRs.
- Favor small, composable functions and explicit logging via `loguru`; keep CLI entrypoints thin and delegate to services.
- Config via environment variables (e.g., `REGREADER_KEYWORD_INDEX_BACKEND`, `REGREADER_VECTOR_INDEX_BACKEND`, provider API keys); never commit `.env` or data assets.

## Testing Guidelines
- Add/extend pytest cases under `tests/`; name files `test_*.py` and keep deterministic inputs.
- For new parser/index logic, add focused unit tests plus a CLI smoke (e.g., `make inspect` or `make search`) noted in the PR.
- Aim to keep or raise coverage (`make test-cov`); mark slow cases with `-m "not slow"` if needed for CI speed.

## Commit & Pull Request Guidelines
- Use concise, imperative subjects; conventional prefixes seen (`feat:`, `fix:`, `refactor:`). Group related changes per commit.
- PRs should describe scope, data used (paths/REG_IDs), and commands executed (`make test`, `make lint`); attach screenshots/logs for CLI outputs when relevant.
- Highlight breaking changes, migration steps, or data cleanups; avoid committing large PDFs or generated storage.
