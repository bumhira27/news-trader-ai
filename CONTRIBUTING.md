# Contributing to News Trader AI

We treat documentation, test coverage, and deterministic builds as core engineering features. Contributions must strictly adhere to the following standards.

## Local Developer Environment

To contribute, your local environment must mirror the CI pipeline.

1. **Python Runtime:** Strict targeting of Python 3.12.x.
2. **Virtual Environment:** Code must execute inside an isolated virtual environment (`.venv`).
3. **Database:** Testing requires a functioning SQLite implementation. Production patches must be validated against PostgreSQL 16.
4. **Timezones:** The OS must have valid IANA timezone databases accessible, or `tzdata` must be explicitly installed via `pip`.

## Linting & Formatting Baseline

Code cleanliness is mechanically enforced. We do not argue about style.

- **Formatter:** `black` (Line length: 120)
- **Linter:** `ruff` (Catching unused imports, undefined variables, and basic security flaws)
- **Type Checking:** `mypy` (Strict mode enabled. All functions must have explicit type hints for arguments and return values).

*C# Code:* Must conform to standard `.editorconfig` rules bundled with Visual Studio/cTrader (.NET 6 baseline).

## Branching Strategy

This repository utilizes **Trunk-Based Development**.
- The `main` branch is the absolute source of truth and must always be in a deployable state.
- Short-lived feature branches (`feat/`, `fix/`, `chore/`) are branched from `main`.
- We do not use long-running `develop` or `release` branches.

## Pull Request Approval Policies

Before a Pull Request is merged into `main`, it must satisfy the following constraints:
1. **Zero Failing Tests:** `python -m pytest -v` must execute with 100% pass rate.
2. **Type Safety:** `mypy .` must report zero errors.
3. **No Unaudited Artifacts:** Commits must not contain compiled binaries, SQLite databases (`.db`), or temporary parquet/csv outputs. 
4. **Clean Git History:** Commits must follow the Semantic Commit Guidelines.

## Semantic Commit Guidelines

We strictly adhere to [Conventional Commits](https://www.conventionalcommits.org/).

**Allowed Prefixes:**
- `feat:` A new feature (e.g., adding a new API endpoint)
- `fix:` A bug fix (e.g., correcting timezone parsing)
- `docs:` Documentation only changes
- `chore:` Maintenance tasks, dependency updates, or artifact removal
- `refactor:` Code changes that neither fix a bug nor add a feature
- `test:` Adding or modifying tests
- `ci:` Changes to CI configuration files and scripts

*Example:* `fix: resolve IANA timezone parsing failure during DST shifts`
