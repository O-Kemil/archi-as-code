"""Inventory loader, as specified in ADR-0003."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from archinv.models import Application, ITComponent

# Pydantic prefixes the message of a ValueError raised in a validator.
PYDANTIC_VALUE_ERROR_PREFIX = "Value error, "


@dataclass(frozen=True)
class RecordError:
    """One error located by file and field path (ADR-0003, decision 1).

    field is empty when the error concerns the whole file.
    """

    file: Path
    field: str
    message: str

    def __str__(self) -> str:
        if self.field:
            return f"{self.file}: {self.field}: {self.message}"
        return f"{self.file}: {self.message}"


class InventoryError(Exception):
    """Raised by the loader when the inventory has at least one error."""

    def __init__(self, errors: list[RecordError]) -> None:
        self.errors = errors
        super().__init__("\n".join(str(error) for error in errors))


def field_path(loc: tuple[int | str, ...]) -> str:
    """Render a Pydantic error location: ("depends_on", 1, "type") -> depends_on[1].type."""
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        elif path:
            path += f".{part}"
        else:
            path = str(part)
    return path


def errors_from_pydantic(file: Path, error: ValidationError) -> list[RecordError]:
    """Convert every error of a ValidationError to the loader's form."""
    return [
        RecordError(
            file,
            field_path(detail["loc"]),
            detail["msg"].removeprefix(PYDANTIC_VALUE_ERROR_PREFIX),
        )
        for detail in error.errors()
    ]


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects a key appearing twice in a mapping (ADR-0003, decision 3)."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep)


def yaml_message(error: yaml.YAMLError) -> str:
    """One-line message with the position, when PyYAML provides one."""
    if isinstance(error, yaml.MarkedYAMLError) and error.problem_mark is not None:
        mark = error.problem_mark
        return f"{error.problem} (line {mark.line + 1}, column {mark.column + 1})"
    return str(error)


def describe(data: object) -> str:
    """Name a YAML root value in plain words, for people who do not read Python."""
    if isinstance(data, list):
        return "a list"
    if isinstance(data, str):
        return "text"
    if isinstance(data, bool):
        return "a single value"
    if isinstance(data, int | float):
        return "a number"
    return "a single value"


def load_record(
    file: Path, model: type[Application] | type[ITComponent]
) -> Application | ITComponent | list[RecordError]:
    """Phase 1 for one file: read, parse, validate, check the id.

    Returns the record, or the list of its errors. The first failing step ends
    the checks for the file (ADR-0003, decision 3).
    """
    try:
        text = file.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        message = f"the file is not valid UTF-8 (byte {error.start}): save it as UTF-8"
        return [RecordError(file, "", message)]
    try:
        data = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as error:
        return [RecordError(file, "", yaml_message(error))]
    if data is None:
        return [RecordError(file, "", "the file is empty")]
    if not isinstance(data, dict):
        message = f"the file must contain a mapping of fields, not {describe(data)}"
        return [RecordError(file, "", message)]
    try:
        record = model.model_validate(data)
    except ValidationError as error:
        return errors_from_pydantic(file, error)
    if record.id != file.stem:
        message = f"'{record.id}' does not match the file name '{file.stem}'"
        return [RecordError(file, "id", message)]
    return record


APPLICATIONS_DIR = "applications"
IT_COMPONENTS_DIR = "it-components"
RECORD_SUFFIX = ".yaml"


@dataclass(frozen=True)
class Inventory:
    """The loaded inventory, records indexed by id in file name order (ADR-0003, decision 7)."""

    applications: dict[str, Application]
    it_components: dict[str, ITComponent]


def record_files(directory: Path) -> tuple[list[Path], list[RecordError]]:
    """List the record files of a directory, sorted by name (ADR-0003, decision 5)."""
    if not directory.is_dir():
        return [], [RecordError(directory, "", "directory not found")]
    files: list[Path] = []
    errors: list[RecordError] = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_file() and path.suffix == RECORD_SUFFIX:
            files.append(path)
        elif path.suffix == ".yml":
            errors.append(RecordError(path, "", "use the .yaml extension"))
        else:
            errors.append(
                RecordError(
                    path, "", "not a record file: only .yaml files are read here"
                )
            )
    return files, errors


def load_records(
    directory: Path, model: type[Application] | type[ITComponent]
) -> tuple[dict, list[RecordError]]:
    """Phase 1 over a directory: every file is read, every error is kept."""
    files, errors = record_files(directory)
    records = {}
    for file in files:
        result = load_record(file, model)
        if isinstance(result, list):
            errors.extend(result)
        else:
            records[result.id] = result
    return records, errors


def record_file(root: Path, directory: str, record_id: str) -> Path:
    """The file of a loaded record: id equals the file name (ADR-0001)."""
    return root / directory / f"{record_id}{RECORD_SUFFIX}"


def check_references(
    root: Path,
    applications: dict[str, Application],
    it_components: dict[str, ITComponent],
) -> list[RecordError]:
    """Phase 2: ids unique across kinds, every target exists (ADR-0003, decision 4)."""
    errors = []
    for shared in sorted(applications.keys() & it_components.keys()):
        file = record_file(root, IT_COMPONENTS_DIR, shared)
        errors.append(
            RecordError(file, "id", f"'{shared}' is also the id of an application")
        )
    for application in applications.values():
        file = record_file(root, APPLICATIONS_DIR, application.id)
        for index, dependency in enumerate(application.depends_on):
            target = dependency.application
            if target not in applications:
                message = (
                    f"unknown application '{target}': "
                    f"there is no {APPLICATIONS_DIR}/{target}{RECORD_SUFFIX}"
                )
                errors.append(
                    RecordError(file, f"depends_on[{index}].application", message)
                )
        for index, component in enumerate(application.it_components):
            if component not in it_components:
                message = (
                    f"unknown IT component '{component}': "
                    f"there is no {IT_COMPONENTS_DIR}/{component}{RECORD_SUFFIX}"
                )
                errors.append(RecordError(file, f"it_components[{index}]", message))
    return errors


def load_inventory(root: Path) -> Inventory:
    """Load inventory/ or raise InventoryError with every error found (ADR-0003)."""
    applications, errors = load_records(root / APPLICATIONS_DIR, Application)
    it_components, more_errors = load_records(root / IT_COMPONENTS_DIR, ITComponent)
    errors.extend(more_errors)
    if not errors:
        errors = check_references(root, applications, it_components)
    if errors:
        raise InventoryError(errors)
    return Inventory(applications, it_components)
