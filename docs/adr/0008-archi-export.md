# ADR-0008: Archi export, ArchiMate mapping and exchange format

- Status: Accepted
- Date: 2026-10-16
- Deciders: Kemil

## Context

The scoping note asks for an export that the team's modelling tool, Archi, opens without errors. ADR-0001 deferred to this ADR the mapping of records and dependency types to ArchiMate elements and relationships. The inventory is loaded by ADR-0003 and the graph of ADR-0005 holds one edge per pair of applications with the list of dependency types.

Facts verified on 2026-10-16:

- Archi 5.10.0 is the current release; its relationship rules file (`relationships.xml`) is versioned 3.2, so Archi applies the ArchiMate 3.2 relationship matrix. Archi imports, without plugin, an Open Exchange XML file ("File > Import > Open Exchange XML Model...", which creates a new model) and CSV files into an existing model; its own Open Exchange export offers "Validate after export" against the XSD schemas. Archi also runs headless from the command line (`--xmlexchange.import`, `--saveModel`, with `xvfb-run` on Linux).
- The Open Group publishes the ArchiMate Model Exchange File Format 3.1 (for ArchiMate 3.1 and 3.2) as three XSD files, reachable without an account, with the namespace `http://www.opengroup.org/xsd/archimate/3.0/`. A model holds `elements`, `relationships`, optional `organizations`, `propertyDefinitions` and `views`; every concept takes a `documentation` and `properties`. The `identifier` attribute is an `xs:ID`, an XML name: unique in the file, not starting with a digit, letters, digits, `-`, `_` and `.` allowed, no space or colon (pattern `[\i-[:]][\c-[:]]*`, checked with xmlschema). The XSD files carry no licence notice.
- The ArchiMate 3.2 specification on the Open Group site now requires an account; the relationship rules below are taken from Archi's own matrix, which is what decides whether an import succeeds. With Archi's key letters (`a` Access, `f` Flow, `i` Assignment, `o` Association, `r` Realization, `t` Triggering, `v` Serving): ApplicationComponent to ApplicationComponent allows `c f g o r s t v` and not Access; SystemSoftware, Device and Node to ApplicationComponent allow `f o r t v`; TechnologyService to ApplicationComponent allows `f o t v`; ApplicationComponent to SystemSoftware allows `f o t v`.
- The schema of ADR-0001 records which application triggers an exchange, not which way the data flows.
- `xmlschema` 4.3.2 validates XML against XSD in pure Python, MIT licence.

## Decision drivers

- D1. The file opens in Archi 5.x without error and without plugin.
- D2. No information of the inventory is lost in the export.
- D3. No relationship asserts something the schema does not know.
- D4. The export is verified on every push without Archi (ADR-0006 path: generated, not committed).

## Options considered

### Relationship for `depends_on`

- A: Serving from the target to the declaring application for every type, the types in a property of the relationship, one relationship per pair. Always valid, says exactly what `depends_on` means, keeps the types.
- B: one relationship per type: Serving for `api`, Triggering for `event`, Flow for `file`, Access for `database`. Flow needs the direction of the data, which the schema does not hold (on the curated data set, four file links are exports and three are imports), and Access is not allowed between two application components: it would need a data object invented by the export. What remains of B is Triggering for `event` alone. Rejected (D3).
- C: Association with the type in a property. Always valid, says nothing. Rejected.

### File format

- Open Exchange Format 3.1: native import, elements, relationships, properties, documentation, views if wanted, one file, validated offline against the XSD, readable by other ArchiMate tools.
- Archi CSV import: three files with fixed headers, imported into an existing model only, no validation possible outside Archi beyond the headers, specific to Archi. Rejected.
- Archi's own `.archimate` format: internal format, not documented as an exchange format. Rejected.

### Views in the export

- (a) Model only; views are built in Archi.
- (b) Views with a grid layout computed by the export. Opens, ugly, to be rearranged by hand.
- (c) Views with coordinates computed by Graphviz (`dot -Tplain`). Couples the export to Graphviz and to a parser of its output. Both deferred.

### Where the XSD files live

- Committed in the repository: offline and reproducible, but the files carry no licence. Rejected.
- Downloaded into a git-ignored cache when the test runs: in the CI the test fails if the download fails; on a laptop without network the test is skipped with a message saying how to fetch the files.

## Decision

1. Elements. An application becomes an `ApplicationComponent`. An IT component becomes a `SystemSoftware` (`software`), a `Device` (`hardware`) or a `TechnologyService` (`service`). The record name is the element name; the application description is its documentation. The other fields are properties: `id`, `business_owner`, `technical_owner`, `business_criticality`, `hosting`, each lifecycle date present (`lifecycle.plan` ... `lifecycle.end_of_life`), `lifecycle_phase` at the reference date, `vendor`, `version`. Property names are declared once in `propertyDefinitions`.
2. Relationships. `runs_on` is a Serving relationship from the technology element to the application component. `depends_on` is option A: one Serving relationship per pair, from the target application to the declaring one, with the property `dependency_types` (the types in enumeration order, comma separated) and, as documentation, one line per declared dependency (type and description).
3. Format: Open Exchange Format 3.1. Element identifiers are `id-<record id>`. Relationship identifiers are `rel-<source id>_<target id>`: the separator is an underscore because slugs contain hyphens and never underscores, so `rel-pos-stores-erp` would be ambiguous (`pos-stores` to `erp`, or `pos` to `stores-erp`) while `rel-pos-stores_erp` is not, and the underscore is allowed in an `xs:ID`. Both prefixes start with a letter, as an `xs:ID` requires, since a slug may start with a digit. The model carries a name, "Application inventory" by default and `--name` to change it (the tool does not know the data set; the workflow passes the data set's name like it passes the deadline), and a documentation line: produced by archinv, reference date, number of applications and IT components.
4. Scope: the whole inventory, no organization folders (Archi files by layer), no views (option a).
5. Command: `archinv archi --reference-date --name --output`, same conventions as `report` and `map`; `.xml` extension. The CI produces `generated/inventory.archimate.xml` with the other deliverables, in the artifact.
6. Verification, three levels. (1) The export of the curated data set is validated against the three XSD files with `xmlschema`, a test dependency; the files are downloaded into a git-ignored cache, with the download policy above. (2) A test checks that every (source type, target type, relationship type) produced is in the allowed list copied from Archi's matrix, with its source, because the XSD does not enforce the matrix. (3) A headless Archi import in a `workflow_dispatch` workflow is deferred until levels 1 and 2 let an error through. The first export is opened in Archi on a laptop: the acceptance test of the scoping note.

## Consequences

- Positive: a valid ArchiMate 3.2 model with every record, every link and every field, opened by Archi and by any tool that reads the exchange format; verified on every push without Archi.
- Negative: every application link is a Serving relationship, the ArchiMate nuances (Flow, Triggering, Access) are not used; no ready-made view; the XSD download makes one test depend on the network in the CI; the headless Archi check is not automated.
- Follow-up: a `direction` field on `Dependency` (amendment of ADR-0001) would allow Flow for `file` and `event`; generated views (b or c) if Archi users ask for them; the headless Archi workflow; owners and hosting as ArchiMate elements if someone needs to relate them.

## Sources

Consulted on 2026-10-16.

- Archi, download page (version 5.10.0): https://www.archimatetool.com/download/
- Archi, help "The Open Group Exchange File Format", "Importing from an Open Exchange file", "Exporting and Settings", "Exporting and Importing the Model in CSV Format": https://github.com/archimatetool/archi/tree/master/com.archimatetool.help/help/Text
- Archi, Command Line Interface: https://github.com/archimatetool/archi/wiki/Archi-Command-Line-Interface
- Archi, relationship matrix and key letters: https://github.com/archimatetool/archi/blob/master/com.archimatetool.model/model/relationships.xml and https://github.com/archimatetool/archi/blob/master/com.archimatetool.model/model/relationships-keys.xml
- The Open Group, ArchiMate Model Exchange File Format schemas: https://www.opengroup.org/xsd/archimate/ (files under https://www.opengroup.org/xsd/archimate/3.1/)
- xmlschema (MIT): https://github.com/sissaschool/xmlschema
