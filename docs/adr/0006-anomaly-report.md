# ADR-0006: Anomaly report and generated deliverables

- Status: Accepted
- Date: 2026-10-13
- Deciders: Kemil

## Context

The scoping note asks for an anomaly report listing end-of-life technologies, applications without an owner and circular dependencies, and for maps and report "regenerated with no manual action" by GitHub Actions. ADR-0001 decided that a record revealing a problem in the landscape must be valid, so that the problem reaches the report instead of failing the CI. ADR-0005 provides the graph queries the report needs. The question "commit `generated/` or let the CI produce it" has been open since the scoping note.

Facts verified on 2026-10-13 in the GitHub documentation: a step can write GitHub Flavored Markdown to the `$GITHUB_STEP_SUMMARY` file, shown on the page of the workflow run, up to 1 MiB per step; `actions/upload-artifact` attaches files to the run, with a configurable retention; a `schedule` trigger runs on the latest commit of the default branch, may be delayed under load, and is disabled automatically after 60 days without activity in a public repository; `workflow_dispatch` allows a manual run. The current workflow has `permissions: contents: read`.

## Decision drivers

- D1. The three anomalies of the scoping note, plus what the graph gives at no cost and within scope.
- D2. The report says the truth of its date: a technology that reached end of life yesterday appears today.
- D3. No manual action to regenerate, including for an owner who edits a record from the GitHub web interface.
- D4. The CI keeps a read-only token.
- D5. An anomaly is content, not a failure (ADR-0001).

## Options considered

### Where `generated/` lives

- A: the CI commits `generated/` back to the repository. Literal "no manual action", the report is readable in the repository. Costs: a write token (fails D4), a CI push that triggers the CI again, commits nobody wrote in a pull request, and noise commits on the days a component crosses its date.
- B: the developer commits `generated/`, the CI regenerates and fails if it differs. Read-only token, the report is reviewed in the pull request. Costs: an owner editing a record on GitHub cannot regenerate (fails D3), and the reference date must be frozen for the check to be stable, which makes an obsolescence report false (fails D2).
- C: nothing is committed; the CI produces the report on every push and every night, shows it on the run page and attaches it as an artifact. Read-only token, no manual action, the date is always today. Costs: the deliverable is not in the repository, artifacts expire, and the nightly schedule stops after 60 days of inactivity.

### Exit status with anomalies

- 0: the report is the deliverable, anomalies are its normal content (D5); the CI stays green on a data set built to contain anomalies.
- 1: a quality gate for a landscape that is already clean. Not the situation of a migration inventory; a permanently red CI is ignored. Rejected. A `--fail-on` option can come when a team decides that one kind of anomaly must never enter.

## Decision

1. Content, in this order: a header with the reference date, the deadline when given, and the counts of records; a summary table with the count of every section, zeros included; applications without business owner; circular dependencies (from `cycles()`, first id repeated at the end); IT components past end of life on the reference date, each with the applications using it; IT components reaching end of life after the reference date and on or before the deadline, present only when `--deadline` is given; applications without IT component, excluding `saas` hosting, which has none by construction; the ten most depended-upon applications by direct dependents, zeros omitted. Every list is sorted by id; the report contains no generation time, so the same inventory and dates give the same text.
2. Command: `archinv report --inventory PATH --reference-date YYYY-MM-DD --deadline YYYY-MM-DD --output PATH`. The reference date defaults to today, supplied by the command line, not by the models; the deadline is optional; the output defaults to stdout, and `--output` creates the parent directory. An invalid inventory is reported exactly as by `validate`, with status 1.
3. Exit status 0 when the report contains anomalies. Status 1 stays reserved to an invalid inventory (ADR-0004).
4. `generated/`, option C. `generated/` is listed in `.gitignore` and never committed. The workflow, after the validation step, runs `archinv report --deadline 2028-03-31 --output generated/report.md`, appends the file to `$GITHUB_STEP_SUMMARY`, and uploads `generated/` with `actions/upload-artifact`, pinned by commit SHA like the other actions. The workflow gains two triggers: `schedule` every night, for a report at the date of the day, and `workflow_dispatch`, for a run on demand. The deadline is an assumption of the data set (hosting contract end), written in the workflow until a second data set needs its own.
5. A dated example of the report is committed under `docs/`, with its reference date and the commit it was produced from in its header, so that a reader of the repository sees the deliverable. It is a snapshot, regenerated by hand when the data set changes.

## Consequences

- Positive: the report is produced on every push and every night with a read-only token and no manual action; an owner who edits a record on GitHub sees the new report on the run page; the acceptance list of expected anomalies can be checked by tests on the report text.
- Negative: the deliverable lives in workflow runs, not in the repository; artifacts expire; the nightly run stops after 60 days without activity and resumes at the next commit; the example in `docs/` ages between two regenerations; the deadline is hard-coded in the workflow.
- Follow-up: the exports (Mermaid, Graphviz, Archi) take the same path, artifact and run page; a published site (GitHub Pages) that keeps the latest report and maps readable at a stable address is the v1.1 evolution, with its own ADR because it changes the token permissions; `--fail-on` if a quality gate is ever wanted; a data-set configuration file if the deadline must leave the workflow.

## Sources

Consulted on 2026-10-13.

- GitHub Docs, Workflow commands for GitHub Actions, "Adding a job summary" (`$GITHUB_STEP_SUMMARY`, 1 MiB per step): https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions
- GitHub Docs, Events that trigger workflows (`schedule`, `workflow_dispatch`): https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows
- GitHub Docs, Storing and sharing data from a workflow (artifacts, `retention-days`): https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow
- actions/upload-artifact, README and release v7.0.2 (2026-10-07), tag commit `cf430e030ddbb5b0abf93d22962f4752f3646cd9` read from the GitHub API: https://github.com/actions/upload-artifact
