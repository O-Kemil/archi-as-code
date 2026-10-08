"""Tests for the inventory loader (ADR-0003)."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from pydantic import ValidationError

from archinv.loader import InventoryError, RecordError, errors_from_pydantic, field_path
from archinv.models import Application

FILE = Path("inventory/applications/pos-stores.yaml")


# Step 1: the error object and its display (ADR-0003, decision 1).


def test_error_with_a_field_prints_file_field_and_message():
    error = RecordError(FILE, "depends_on[1].type", "Input should be 'api'")
    assert (
        str(error)
        == "inventory/applications/pos-stores.yaml: depends_on[1].type: Input should be 'api'"
    )


def test_error_on_the_whole_file_prints_file_and_message():
    error = RecordError(FILE, "", "duplicate key 'name'")
    assert str(error) == "inventory/applications/pos-stores.yaml: duplicate key 'name'"


def test_errors_are_immutable():
    error = RecordError(FILE, "name", "message")
    with pytest.raises(FrozenInstanceError):
        error.message = "other"


def test_errors_with_the_same_content_are_equal():
    assert RecordError(FILE, "name", "m") == RecordError(Path(str(FILE)), "name", "m")


@pytest.mark.parametrize(
    ("loc", "expected"),
    [
        ((), ""),
        (("name",), "name"),
        (("lifecycle", "active"), "lifecycle.active"),
        (("depends_on", 1, "type"), "depends_on[1].type"),
        (("it_components", 0), "it_components[0]"),
    ],
)
def test_field_path_renders_a_pydantic_location(loc, expected):
    assert field_path(loc) == expected


def test_converts_every_pydantic_error_of_a_record():
    with pytest.raises(ValidationError) as error:
        Application(
            id="pos-stores",
            name="",
            description="Cash register software.",
            business_criticality="mission_critical",
            hosting="store",
            lifecycle={},
            depends_on=[{"application": "pos-stores", "type": "api"}],
        )
    errors = errors_from_pydantic(FILE, error.value)
    assert [e.field for e in errors] == ["name", "lifecycle", "depends_on"]
    assert errors[0] == RecordError(
        FILE, "name", "String should have at least 1 character"
    )


def test_strips_the_pydantic_value_error_prefix():
    with pytest.raises(ValidationError) as error:
        Application(
            id="pos-stores",
            name="Point of sale",
            description="Cash register software.",
            business_criticality="mission_critical",
            hosting="store",
            lifecycle={},
        )
    [converted] = errors_from_pydantic(FILE, error.value)
    assert converted.message == "an application lifecycle needs at least one date"


def test_inventory_error_prints_one_line_per_error_and_keeps_the_list():
    errors = [RecordError(FILE, "name", "first"), RecordError(FILE, "", "second")]
    error = InventoryError(errors)
    assert error.errors is errors
    assert str(error) == (
        "inventory/applications/pos-stores.yaml: name: first\n"
        "inventory/applications/pos-stores.yaml: second"
    )
