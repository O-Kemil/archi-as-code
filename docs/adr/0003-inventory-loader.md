# ADR-0003: Inventory loader and validation errors

- Status: Accepted
- Date: 2026-10-08
- Deciders: Kemil

## Context

The four record models of ADR-0001 validate one record at a time. A *loader* is the code that reads every record file under `inventory/`, builds the models, checks what a single record cannot see (its file name, the other records it refers to) and hands a loaded inventory to the graph, the report and the exports. The scoping note requires that an invalid record makes the CI fail with an error message naming the file and the field.

Facts verified by execution on 2026-10-08 with PyYAML 6.0.3 and Pydantic 2.13:

- Pydantic reports every error of one record, each with the path of the field, for example `("depends_on", 1, "type")`. Its default text output takes four lines per error and includes the input value and a documentation URL.
- `yaml.safe_load` returns `None` for an empty file, a `list` for a file whose root is a list, and raises `yaml.YAMLError` with line and column on a syntax error.
- `yaml.safe_load` keeps the last value when a key appears twice in a mapping, silently. The PyYAML documentation does not describe this case. A `SafeLoader` subclass that overrides `construct_mapping` detects the duplicate and reports its line and column.

Git does not track empty directories (verified: `inventory/applications/` does not exist in the repository before its first file). A fresh clone has no record directory until the first record or a `.gitkeep` file is committed.

## Decision drivers

- D1. An error names the file and the field (scoping note), in one form for every kind of error.
- D2. One CI run shows every error, so that a contributor fixes everything in one push.
- D3. Nothing is lost silently: a record skipped, a value overwritten, a path mistyped must produce an error.
- D4. The loaded inventory is deterministic, so that `generated/` does not change between two runs on the same data.
- D5. Templates in `inventory/templates/` are never loaded as records (ADR-0001).

## Options considered

### Error form

- A: let the Pydantic exception propagate, prefixed with the file name. Nothing to write, but four lines per error, and loader errors (file name, unknown target) would have another form. Fails D1.
- B: one line per error, `file: field.path: message`, from a small error object with three fields (file, field path, message). Pydantic errors are converted, loader errors are created in the same form. About fifteen lines of code and their tests.
- C: GitHub Actions annotations (`::error file={name},line={line}::{message}`), shown in the pull request. Needs the line of the field, which means walking the YAML node tree. Justified when reviewers read errors in the pull request rather than in the log; built on top of B when the time comes.

### Several errors

- A: stop at the first invalid record. Simplest, but a contributor with three bad records pushes three times. Fails D2.
- B1: read everything, report everything, fail at the end. Cross-record checks run only when every record is valid, because a record that failed is absent from the index and every reference to it would be a false "unknown target".
- B2: like B1, but a failed record still registers its file name as a known id so that both phases run in one go. One less CI round in the worst case, one more subtlety to defend. Can replace B1 later without changing the error form.

### Duplicate keys in a YAML file

- Detect: a `SafeLoader` subclass, about ten lines, reports the key with its line and column.
- Known limitation: document that the last value wins. Fails D3 for a plain copy-paste mistake.

### Excluding the templates

- A: the loader reads only `inventory/applications/` and `inventory/it-components/`. Nothing to maintain.
- B: walk `inventory/` recursively with an exclusion list. The walk cannot tell the kind of a record found elsewhere. Rejected.
- C: mark templates with a field. Unknown fields are rejected by ADR-0001 and templates must stay valid. Rejected.

## Decision

1. Error form B. Each error is an object with `file`, `field` and `message`, printed as `file: field: message`. The field path uses brackets for list indexes: `depends_on[1].type`, the notation the Pydantic documentation itself uses in its formatting example. When the error concerns the whole file (syntax error, empty file, root that is not a mapping, duplicate key, file name), `field` is empty and the line is `file: message`.
2. Several errors, B1. The loader raises one `InventoryError` carrying the list of all errors. The command line prints one line per error and exits with status 1. An inventory is either fully valid or not returned at all, so the graph and the report never see a partial one.
3. Phase 1, record by record, files sorted by name: read the file as UTF-8 explicitly, parse it with a YAML loader that rejects duplicate keys, check that the root is a mapping, build the model, check that `id` equals the file name without extension. The first failing step ends the checks for that file.
4. Phase 2, across records, only when phase 1 produced no error: ids unique over applications and IT components together (the graph identifies nodes by id, a collision would merge two nodes); every `depends_on` target exists among the applications; every `it_components` target exists among the IT components.
5. Files and directories. Only `*.yaml` files are records. Any other non-hidden file in a record directory is an error; for a `.yml` file the message says to use the `.yaml` extension. A missing record directory is an error, because a mistyped path would otherwise produce an empty report with no anomaly. A present but empty directory gives an empty inventory for that kind. Consequence: a clone with no record at all fails, since git does not keep empty directories; the two directories are created with a `.gitkeep` file.
6. Templates, option A: `inventory/templates/` is never read. A test loads the real `inventory/` and checks that no record carries a template id.
7. The loader returns an `Inventory` dataclass with two dictionaries indexed by id, `applications` and `it_components`, in file name order. A dataclass rather than a Pydantic model because the content is already validated.

## Consequences

- Positive: one error form for Pydantic, YAML and loader errors; one CI run lists every error of every record; a duplicate key, a `.yml` file or a wrong path cannot pass silently; the inventory order is stable.
- Negative: in the worst case two CI rounds, one for record errors and one for reference errors (B1); the duplicate key check depends on a PyYAML extension point that few projects use; the loader has more code than a plain loop over `safe_load`.
- Follow-up: GitHub annotations (option C) if errors need to appear in pull requests; B2 if the two rounds prove annoying; the command line (arguments, default `inventory/` path, exit codes) is specified with the CLI; whether `generated/` is committed remains open.

## Sources

Consulted on 2026-10-08.

- Pydantic, Error Handling (`ValidationError.errors()`, the `loc` tuple, and the `items[1].value` formatting example): https://pydantic.dev/docs/validation/latest/errors/errors/
- PyYAML documentation (`safe_load`, `SafeLoader`, `construct_mapping`, `problem_mark`): https://pyyaml.org/wiki/PyYAMLDocumentation
- GitHub Docs, Workflow commands for GitHub Actions (`::error file={name},line={line},endLine={endLine},title={title}::{message}`): https://docs.github.com/en/actions/reference/workflow-commands-for-github-actions
- Behaviour of PyYAML 6.0.3 on duplicate keys, empty files and syntax errors, and of Pydantic 2.13 on error paths: verified by execution on 2026-10-08.
