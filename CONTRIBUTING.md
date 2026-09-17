# Contributing to News Trader AI

This document establishes the baseline engineering protocols, onboarding constraints, and repository branching strategies required for contributing to the News Trader AI codebase.

## Local Environment Onboarding

Contributors must configure their environments to match the absolute baseline specifications.

### Dependencies
1. **Python**: Version 3.12.0 or higher.
2. **PostgreSQL**: Version 15.0 or higher (or Docker Desktop for containerized deployment).
3. **.NET SDK**: Version 6.0 (for compiling the C# execution bot).

### Setup Execution
Execute the environment initialization sequence strictly:

```bash
git clone https://github.com/bumhira27/news-trader-ai.git
cd news-trader-ai
python -m venv venv
source venv/bin/activate
pip install -r economic_data_server/requirements.txt
pip install -r requirements.txt
```

### Testing Baseline
All pull requests must pass the comprehensive pytest suite locally prior to submission.
```bash
python -m pytest -v
```

## Linting and Formatting Policies

Code submissions must adhere to the following static analysis and formatting baselines. 

- **Python Formatting**: `black` (Line length: 120).
- **Type Checking**: `mypy` (Strict mode).
- **C# Formatting**: Standard `dotnet format` complying with Microsoft C# conventions.

Files failing lint or type checks in the CI pipeline will trigger automatic PR rejection.

## Branching Strategy

This repository follows a strict Trunk-Based Development model.

- **`main`**: The canonical, deployable artifact state. Commits direct to main are blocked.
- **Feature Branches**: Cut from `main` using the format `feature/<issue-id>-<short-desc>` or `fix/<issue-id>-<short-desc>`.
- **Merge Protocol**: Rebase feature branches against `main` prior to PR submission. Merge commits are disabled; squash and merge is enforced.

## Pull Request Policy

1. **Test Coverage**: PRs must maintain or increase total codebase line-coverage metrics. Regression tests must be included for bug fixes.
2. **Architectural Review**: Modifications to the `economic_data_server` schema or API contracts require explicitly updated Markdown documentation in the PR.
3. **Approval**: One approving review from a core maintainer is required for integration.

## Semantic Commit Guidelines

Commit messages must conform to the Conventional Commits specification. This ensures automated CHANGELOG generation and semantic versioning stability.

### Format
```
<type>(<scope>): <subject>

<body>
```

### Allowed Types
- **`feat:`** A new feature or architectural component (e.g., new API endpoint).
- **`fix:`** A bug fix or logical correction.
- **`docs:`** Modifications restricted entirely to markdown files or inline documentation.
- **`style:`** Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons).
- **`refactor:`** A code change that neither fixes a bug nor adds a feature.
- **`perf:`** A code change that improves operational performance or runtime efficiency.
- **`test:`** Addition of missing tests or correcting existing test suites.
- **`ci:`** Changes to CI configuration files and automation scripts.
- **`chore:`** Maintenance tasks, dependency bumps, or build process updates.

### Example
```
feat(api): add high-impact news event filter endpoint

Implemented the /api/v1/news-events route allowing clients to filter calendar items natively by USD currency and High impact classification.
```
