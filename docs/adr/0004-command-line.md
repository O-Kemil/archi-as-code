# ADR-0004: Command line interface

- Status: Accepted
- Date: 2026-10-09
- Deciders: Kemil

## Context

The loader (ADR-0003) returns a valid inventory or raises `InventoryError` with one line per error. The CI must run that validation on every push (scoping note). The first command, `archinv validate`, is the contract between the tool, the CI and anyone who scripts it; later commands (graph, report, exports) will follow the same shape.

`pyproject.toml` already declares the entry point `archinv = "archinv:main"`, and the script that uv generates calls `sys.exit(main())`, so the value returned by `main()` is the exit status of the process (verified by reading `.venv/bin/archinv` on 2026-10-09). An *exit status* is the number a program returns to the system when it ends: 0 means success, anything else means failure, and GitHub Actions fails a step on any non-zero status.

## Decision drivers

- D1. The CI fails on an invalid inventory with the errors of ADR-0003 in its log.
- D2. The command stays scriptable: normal output and errors on separate streams, stable exit codes.
- D3. No dependency that the real need does not justify (ADR-0002).
- D4. The same shape for every later command.

## Options considered

### Command line library

- A: `argparse`, standard library. No dependency, sub-commands, generated `--help`, usage errors exit with status 2 (documented, and verified by execution on Python 3.13.7). More verbose code and plain help text.
- B: Typer or Click. A function with type annotations becomes a command, coloured help, shell completion. One production dependency plus its own dependencies, and one more notion to defend, for four or five commands with one or two options each. Justified when options multiply or completion becomes a real need; the switch would be confined to `cli.py`.

### Inventory path

- A: `--inventory PATH` option on each sub-command, default `inventory` relative to the current directory, which is where the CI and a developer in a clone run the command.
- B: optional positional path. Shorter, but ambiguous once a command has both an input and an output path.
- C: find the repository root by walking up to `.git` or `pyproject.toml`. Works from any sub-directory, at the price of hidden behaviour. Rejected for v1.

## Decision

1. `argparse` (option A), with sub-commands. `main(argv=None) -> int` lives in `src/archinv/cli.py` and the entry point becomes `archinv.cli:main`; the example `main()` of `archinv/__init__.py` is removed. Taking the arguments as a parameter and returning the status makes the function testable without a sub-process.
2. `archinv validate --inventory PATH`, default `inventory` relative to the current directory. A missing directory is an inventory error (ADR-0003), so a mistyped path fails loudly. No other option until a need appears; `--reference-date` arrives with the report.
3. Output and exit status:

| Situation | Output | Status |
|---|---|---|
| Valid inventory | one line on stdout: `Inventory valid: 15 applications, 12 IT components` | 0 |
| Invalid inventory (`InventoryError`, including a missing directory) | one line per error on stderr, then `3 errors` | 1 |
| Usage error (unknown sub-command or option, no sub-command) | argparse message on stderr | 2 |
| Unexpected exception | Python traceback | 1 (Python default) |

The success line exists so that a CI log shows what was validated: an empty inventory validated in silence would look like a step that did nothing. Errors go to stderr so that stdout stays usable by scripts. No distinct status for "not found" versus "invalid": the CI does not distinguish them and the error line already says which it is.

## Consequences

- Positive: no new dependency; the CI step is `uv run archinv validate`; every later command reuses the parser, the `--inventory` option and the status convention.
- Negative: plain help text; about twenty lines of argparse code per command; no shell completion.
- Follow-up: the GitHub Actions workflow (next step); `--reference-date` and `--output` with the report and the exports; Typer if the options multiply.

## Sources

Consulted on 2026-10-09.

- Python documentation, `argparse` (sub-commands; usage errors exit with status 2): https://docs.python.org/3/library/argparse.html
- Exit status 2 on usage errors and `sys.exit(main())` in the generated script: verified by execution on Python 3.13.7 with uv on 2026-10-09.
