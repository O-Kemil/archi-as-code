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
