# ADR-0001: Inventory schema for applications and IT components

- Status: Accepted
- Date: 2026-10-03
- Deciders: Kemil

## Context

The inventory is a set of YAML files, one per record, validated by a Pydantic schema (scoping note, scope of v1). The schema is the contract between the people who write records, the tool that reads them, and the deliverables built from them (dependency graph, anomaly report, Archi export). It has to be decided before any code is written.

Terms used in this ADR. A *record* is one YAML file describing one application or one IT component. An *IT component* is a technology an application runs on: a database, a runtime, a middleware, a piece of hardware. A *lifecycle* is the set of dates at which a record enters each phase of its life. *Business criticality* says how much the business suffers if the application stops. A *dependency* says that an application needs another one to work.

The record model is inspired by the public SAP LeanIX meta model. Verified in the SAP LeanIX documentation on 2026-10-03 (see Sources):

- A lifecycle has five dated phases, stored as `plan`, `phaseIn`, `active`, `phaseOut`, `endOfLife`, and LeanIX itself exposes a derived `currentPhase` computed from those dates.
- Business criticality has four levels: mission critical, business critical, business operational, administrative. The enumeration values used below are these labels in `snake_case`; `administrative_service` is this project's own name for the fourth level. The LeanIX API spelling of these values was not consulted and the project does not depend on it.
- Applications are not linked directly. An Interface fact sheet connects a provider application and a consumer application and carries the data objects exchanged.
- IT Component fact sheets have three subtypes in meta model v3: Software, Hardware, Service. Meta model v4 adds SaaS, PaaS, IaaS and AI Model.
- LeanIX recommends modeling IT components as classes (for example "Oracle DB 11.2"), not as instances, and models application hosting at entry level with a tag group whose values are On-Prem, SaaS, PaaS, IaaS.

## Decision drivers

From the scoping note:

- D1. A reliable dependency map, usable to split the migration into waves.
- D2. An anomaly report listing end-of-life technologies, applications without an owner, and circular dependencies.
- D3. An invalid record fails the CI with an error naming the file and the field.
- D4. Records stay easy to write by hand by an application owner, and easy to generate by a script.
- D5. The export opens in Archi without errors.
- D6. Stay within the v1 scope: no fine-grained data flows, no detailed infrastructure, no costs.

## Options considered

### Option A: flat record, status by enumeration

One flat application record: id, name, owner as free text, lifecycle status as an enumeration, business criticality, untyped list of dependencies, list of IT components. The component record has an id, a name, a category and an optional end-of-life date.

Brings: the fastest to write and to generate. Costs: a status without dates cannot answer "which applications reach end of life before the hosting contract ends" (D1, D2); untyped dependencies make every edge equal, which does not help split waves (D1); a hand-written status and a separate end-of-life date drift apart, which is the kind of contradiction the scoping note describes.

### Option B: LeanIX-lite, dated lifecycle and typed dependencies

Two record types, application and IT component, carrying the four LeanIX concepts named in the scoping note: a dated lifecycle with a derived status, business criticality, owners, and typed dependencies declared as direct links between applications. Hosting is an enumeration on the application.

Brings: meets D1 to D6 with nothing that does not serve one of them, and one source of truth for the lifecycle. Costs: dates take more thought than a status, and the generator must produce coherent dates.

### Option C: LeanIX-faithful, with Interface records

Option B plus a third record type, Interface (provider, consumer, data objects, frequency), plus business capabilities, functional and technical fit scores, and tags.

Brings: the closest to the real tool, so the best learning value on how such tools are built. Costs: fine-grained data flows and business capabilities are out of scope (D6), and a third record type doubles the work on loader, graph, generator and Archi export. It becomes the right choice when the migration plan has to treat data migration interface by interface, or when several teams must agree on an exchange contract. Not the case in v1.

## Decision

Option B.

### Files and identifiers

- One YAML file per record: `inventory/applications/<id>.yaml` and `inventory/it-components/<id>.yaml`.
- `id` is a kebab-case slug matching `^[a-z0-9]+(-[a-z0-9]+)*$` and must equal the file name without its extension. Brings: readable in pull requests and in diagrams, stable without a database to allocate numbers; the equality check produces the "file and field" error required by D3. Rejected: UUIDs, unreadable in review.
- One IT component record per version, for example `oracle-database-19c`. An end-of-life date belongs to a version, not to a product. This follows the LeanIX recommendation to model classes, not instances.
- Unknown fields are rejected. A typo in a field name must fail the CI rather than silently lose data (D3). Rejected: ignoring unknown fields, which hides mistakes.
- Dates use ISO 8601 (`YYYY-MM-DD`). YAML parses them natively and Pydantic types them as dates without conversion.
- Enumeration values are lowercase `snake_case`.

### Application record

| Field | Required | Type | Notes |
|---|---|---|---|
| `id` | yes | slug | equals the file name |
| `name` | yes | string | display name |
| `description` | yes | string | one sentence, for the onboarding use case |
| `business_owner` | no | string | team or person who decides for the application; missing is an anomaly, not an error |
| `technical_owner` | no | string | team or person who operates it |
| `business_criticality` | yes | enum | `mission_critical`, `business_critical`, `business_operational`, `administrative_service` |
| `hosting` | yes | enum | `data_center`, `cloud`, `saas`, `store` |
| `lifecycle` | yes | object | see Lifecycle object; at least one date |
| `depends_on` | no | list of dependency objects | default empty |
| `it_components` | no | list of IT component ids | default empty |

### IT component record

| Field | Required | Type | Notes |
|---|---|---|---|
| `id` | yes | slug | equals the file name |
| `name` | yes | string | product and version, for example "Oracle Database 19c" |
| `category` | yes | enum | `software`, `hardware`, `service` |
| `vendor` | no | string | |
| `version` | no | string | |
| `lifecycle` | no | object | same object as the application; `end_of_life` is the date the report uses |

### Lifecycle object

| Field | Required | Type |
|---|---|---|
| `plan` | no | date |
| `phase_in` | no | date |
| `active` | no | date |
| `phase_out` | no | date |
| `end_of_life` | no | date |

Rules: the dates present must be in the order above, and an application lifecycle has at least one date. The current status is derived at load time: it is the latest phase whose date is on or before the reference date (today by default), or empty when no phase has started. Brings: one source of truth, and the report can compute "end of life before a given date". Costs: more thought when writing a record. Rejected: a hand-written status enumeration plus an end-of-life date, which can contradict each other.

The component lifecycle is optional because an unknown end-of-life date is a realistic situation during an audit. The application lifecycle is required because a record with no lifecycle information is useless for migration planning.

### Dependency object

| Field | Required | Type | Notes |
|---|---|---|---|
| `application` | yes | application id | the application this one depends on |
| `type` | yes | enum | `api` (synchronous call), `file` (file transfer or batch), `database` (direct access to the other application's database), `event` (message or queue) |
| `description` | no | string | |

Dependencies are declared by the consumer, in the direction "A depends on B". The owner of A knows what A needs, while the owner of B does not know all of B's consumers. For the migration, B must move before or together with A. The graph builds the reverse index. The type distinguishes synchronous from asynchronous coupling and feeds the choice of ArchiMate relationship at export (later ADR). Rejected: untyped dependencies (option A) and Interface records (option C).

IT components are listed on the application side for the same reason: a shared component such as a database version would otherwise force every consumer to edit the same file.

### Secondary choices

- `hosting` is required. It is not detailed infrastructure (D6); it is the one field that makes the trigger of the scoping note actionable: which applications must leave the data center. `store` covers software running locally in shops, such as point of sale. This mirrors the LeanIX entry-level "Application Hosting" tag group. Rejected: deriving hosting from IT components, which would require modeling hosting services as components.
- Two owner fields rather than a list of roles. The need is "who decides" and "who operates". A role list is more general but heavier to validate and to write for two values. Both are optional, see the boundary below.
- Three component categories (`software`, `hardware`, `service`), the LeanIX meta model v3 set. The v4 cloud subtypes are not needed because `hosting` on the application already carries that information; AI Model is out of scope.
- `description` is required on applications. The onboarding use case needs one sentence per application, and the generator can produce one.
- No `tags` and no `schema_version` in v1. Tags become the place for everything one did not want to model. A schema version only matters at the first breaking change, which will have its own ADR.

### Deviation from LeanIX: direct dependencies instead of Interface records

In LeanIX, an application-to-application link is an Interface fact sheet with its own lifecycle, provider, consumer and data objects. This ADR collapses it into a typed edge declared on the consumer. This is a deliberate simplification: fine-grained data flows are out of scope (D6), and v1 needs the direction and the kind of coupling, not the content of the exchange. If interfaces become first-class later, each `depends_on` entry can be migrated to an Interface record without losing information.

### Validation errors versus report anomalies

The schema and the loader validate the form of the inventory. The report judges its content. A record that reveals a problem in the IT landscape must be valid, otherwise the CI would reject it and the problem would never reach the report.

| Validation error (CI fails) | Report anomaly (CI passes) |
|---|---|
| Unknown, missing or mistyped field; value outside an enumeration; malformed date | Application without `business_owner` |
| `id` that does not match the file name; two records with the same `id` | IT component whose `end_of_life` is on or before the reference date |
| Dependency on an application id that does not exist; reference to an IT component id that does not exist | Circular dependency between applications |
| Application that depends on itself; the same (target, type) pair listed twice (amended 2026-10-08, see Amendments) | Later, without schema change: end of life before the migration deadline, application with no IT component |
| Lifecycle dates out of order; application lifecycle with no date | |

### Example records

```yaml
# inventory/applications/pos-stores.yaml
id: pos-stores
name: Point of sale
description: Cash register software used in every store.
business_owner: Retail operations
technical_owner: Store IT team
business_criticality: mission_critical
hosting: store
lifecycle:
  active: 2015-03-01
  phase_out: 2027-06-30
depends_on:
  - application: inventory-management
    type: api
    description: Stock lookup at checkout.
  - application: erp-finance
    type: file
    description: Nightly sales export.
it_components:
  - oracle-database-11g
  - windows-server-2012
```

```yaml
# inventory/it-components/oracle-database-11g.yaml
id: oracle-database-11g
name: Oracle Database 11g
category: software
vendor: Oracle
version: "11.2"
lifecycle:
  active: 2009-09-01
  end_of_life: 2015-01-31
```

## Consequences

Positive:

- The three anomalies of the scoping note are detectable from the data, and more can be added without changing the schema.
- The lifecycle has one source of truth; the derived status cannot contradict the dates.
- The graph carries the direction and the type of each dependency, which the migration waves need.
- The model stays close enough to LeanIX to be explained with its vocabulary.

Negative:

- Writing a record by hand takes more thought than filling in a status, mainly for lifecycle dates.
- `scripts/generate_sample_inventory.py` must produce coherent lifecycle dates, valid references, and at least one anomaly of each type.
- Direct dependencies cannot describe what is exchanged. Accepted for v1.
- `business_owner` and `technical_owner` are free text, so a spelling variation creates two distinct owners in the report. Accepted limit for v1.

Follow-up:

- `business_owner` may become required once the inventory has been cleaned up and every application has one. That change will be a new ADR, because it changes what the CI rejects.
- The mapping of records and dependency types to ArchiMate elements and relationships is decided in a later ADR on the Archi export.
- The reference date used for the derived status and the end-of-life check is today by default. A configurable date (the end of the hosting contract) is a report option, not a schema concern.
- Whether `generated/` is committed is a separate ADR (open question in the scoping note).
- Commented record templates live in `inventory/templates/`. The loader must not load them as records, and a test must check that they stay valid against the schema as soon as the Pydantic code exists.

## Clarifications

Decided while coding the models, 2026-10-08. None of them changes what the tables above say; they settle what the tables left open.

- Required text fields (`name`, `description`) reject an empty string and a string made of spaces only. Surrounding whitespace is removed at validation. Optional text fields are accepted as written.
- Numbers are not converted to text. `version: 1.0` without quotes is read by YAML as a number and rejected; it must be written `version: "1.0"`. Converting silently would turn `1.10` into `1.1`.
- Dates are validated in Pydantic lax mode: a native YAML date and the ISO text `"2015-03-01"` are both accepted.
- Two lifecycle phases on the same day are accepted; only a later phase dated before an earlier one is rejected.
- The derived status takes a mandatory reference date in the model. "Today by default" is supplied by the command line, so the model stays deterministic and testable.
- The same IT component id listed twice in `it_components` is rejected, like a dependency link listed twice. Both are copy-paste mistakes rather than information.
- A list field left without value (`depends_on:` or `it_components:` followed by nothing) is rejected, because YAML reads it as null, not as an empty list. Delete the line or write `depends_on: []`.

Decided while writing the sample records, 2026-10-09:

- A dependency is declared by the application that triggers the exchange: the one that calls the API, sends or fetches the file, or subscribes to the events. The example below follows this rule: the point of sale sends its sales export, so it declares the link to the ERP.
- For an IT component, `end_of_life` is the date after which the vendor delivers no security fixes without a separately purchased extension. Microsoft Extended Security Updates, Red Hat Extended Life Cycle Support and Oracle Extended Support are excluded. `active` is the general availability date. The source and the date it was consulted go in a comment at the top of the record.

## Amendments

### 2026-10-08: several dependencies on the same application, with different types

Replaces, in the table of the section "Validation errors versus report anomalies", the row "Application that depends on itself; the same dependency target listed twice" with: "Application that depends on itself; the same (target, type) pair listed twice".

An application can call another one through an API and also send it a file. Rejecting the second link would force the inventory to hide a real coupling. Only the same pair of target and type is a duplicate. Consequence for the graph: one edge per pair of applications, carrying the list of dependency types as an attribute.

## Sources

Consulted on 2026-10-03.

- SAP LeanIX, Fact Sheets (types and subtypes): https://help.sap.com/docs/leanix/ea/fact-sheets
- SAP LeanIX, Modeling: IT Components / Hosting (Meta Model v3): https://help.sap.com/docs/leanix/ea/it-components-hosting-modeling-v3
- SAP LeanIX, Meta Model: https://help.sap.com/docs/leanix/ea/meta-model
- LeanIX, Application Criticality Assessment and Matrix: https://www.leanix.net/en/wiki/apm/application-criticality-assessment-and-matrix
- SAP LeanIX, Updating a Lifecycle Phase and Approving the Quality Seal (lifecycle phases and `currentPhase` in the fact sheet data model): https://help.sap.com/docs/leanix/ea/updating-lifecycle-phase-and-approving-quality-seal
