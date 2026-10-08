"""Inventory loader, as specified in ADR-0003."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

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
