# ADR-0002: Tooling for environment, dependencies, tests and lint

- Status: Accepted
- Date: 2026-10-05
- Deciders: Kemil

## Context

The code lives in `src/archinv/` and runs on a laptop and in GitHub Actions. The project starts from scratch, with no team and no existing standard. In an organization that already has its standards (dependency manager, Python version, test and lint tools), following them would be the right choice.

## Decision drivers

- D1. The CI installs exactly the versions used locally, so a CI failure means an invalid inventory or a real bug, not a version drift.
- D2. Open source tools only, few of them, each easy to explain.

## Options considered

- A. `venv` and `pip` from the standard library. Nothing to install, but no real lock file (a file listing the exact version of every installed library) and no control of the Python version. Fails D1 without manual work. Right for a throwaway script.
- B. uv. One tool for the Python version, the virtual environment, the dependencies in `pyproject.toml` and the lock file. Costs one install, and the tool is young and backed by a single company.
- C. Poetry. Mature, with a lock file, but slower and heavier, with nothing here that uv lacks. Right when a team already uses it.

## Decision

Option B, uv, with:

- Python 3.13 pinned in `.python-version`, the version already on the development machine.
- `uv.lock` committed. This is an application, not a library, and D1 depends on it.
- pytest for tests. Tests are plain functions with `assert` and can be parametrized. Rejected: `unittest`, more verbose.
- ruff for lint and formatting, from the first line of code. Rejected: adding it later, which forces one noisy reformatting commit.

## Consequences

- Positive: the same commands (`uv sync`, `uv run`) locally and in CI.
- Negative: contributors must install uv. `pyproject.toml` stays standard, so going back to pip is cheap.
- Follow-up: the GitHub Actions workflow uses uv and runs ruff and pytest.

## Sources

Consulted on 2026-10-05.

- uv documentation: https://docs.astral.sh/uv/
- uv license (Apache 2.0 or MIT): https://docs.astral.sh/uv/reference/policies/license/
