# Contributing to News Trader AI

As an algorithmic execution engine routing highly leveraged institutional capital, code quality and strict integration standards are treated as engineering features, not afterthoughts. All contributions must adhere to the following control protocols.

## Local Developer Onboarding Parameters

1. **Environment Initialization:**
   - Clone the repository and initialize the isolated virtual environment explicitly via `.venv`.
   - Install Python dependencies precisely locked to `requirements.txt`.
   - Ensure cTrader Automate is installed and .NET 6.0 SDK is resolved locally.
2. **Local Environment Variables:**
   - The system utilizes local flat-file IPC instead of environment variables to maintain execution latency constraints. Developers must ensure write access to `C:\` or map the IPC file path accordingly in the EA configuration.

## Linting & Formatting Baseline

Any pull request failing automated formatting checks will be immediately rejected.

- **Python Ecosystem:**
  - Formatter: `Black` (Line length: 88).
  - Linter: `Flake8` for cyclomatic complexity and unused imports.
  - Type Checker: `MyPy` (Strict mode enabled).
- **C# / .NET Ecosystem:**
  - Formatter: `dotnet format` using standard MSBuild ruleset.
  - Style: K&R brace styling, explicit access modifiers required.

## Branching Strategy

This repository enforces **Trunk-Based Development**.
- `main` is the only long-lived branch and is always deploy-ready.
- All feature branches must be short-lived (max 48 hours) and branch directly from `main`.
- Naming convention: `feature/<ticket>-<short-desc>`, `bugfix/<ticket>-<short-desc>`.

## Pull Request Approval Check Policies

To merge into `main`, a PR must satisfy the following pipeline requirements:
1. **Automated Tests:** 100% pass rate on Python unit tests (`pytest`).
2. **Zero Latency Regression:** Order execution profiling must prove no added microsecond latency in the C# execution loop.
3. **Peer Review:** Mandatory approval from at least 1 Senior Quant Engineer.
4. **Squash & Merge:** All PRs must be squashed into a single Semantic Commit upon merging.

## Semantic Commit Guidelines

We strictly follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification. Commit messages must be structured as follows:

`<type>[optional scope]: <description>`

### Allowed Commit Types:
- **feat:** A new feature (e.g., integrating a new HuggingFace dataset).
- **fix:** A bug fix (e.g., fixing slippage calculation rounding).
- **docs:** Documentation changes only.
- **chore:** Routine tasks, dependency updates, or pipeline adjustments.
- **refactor:** A code change that neither fixes a bug nor adds a feature.
- **ci:** Changes to our CI configuration files and scripts.
