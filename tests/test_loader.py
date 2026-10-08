"""Tests for the inventory loader (ADR-0003)."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from pydantic import ValidationError

from archinv.loader import (
    Inventory,
    InventoryError,
    RecordError,
    errors_from_pydantic,
    field_path,
    load_inventory,
    load_record,
)
from archinv.models import Application, ITComponent

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


# Step 2: phase 1, one file at a time (ADR-0003, decision 3).

VALID_APPLICATION = """\
id: pos-stores
name: Point of sale
description: Caisse des magasins à Évry.
business_criticality: mission_critical
hosting: store
lifecycle:
  active: 2015-03-01
"""


def write(directory: Path, name: str, text: str) -> Path:
    file = directory / name
    file.write_text(text, encoding="utf-8")
    return file


def test_loads_a_valid_application(tmp_path):
    record = load_record(
        write(tmp_path, "pos-stores.yaml", VALID_APPLICATION), Application
    )
    assert isinstance(record, Application)
    assert record.description == "Caisse des magasins à Évry."


def test_loads_a_valid_it_component(tmp_path):
    text = "id: oracle-database-11g\nname: Oracle Database 11g\ncategory: software\n"
    record = load_record(write(tmp_path, "oracle-database-11g.yaml", text), ITComponent)
    assert isinstance(record, ITComponent)


def test_reports_a_file_that_is_not_utf8(tmp_path):
    file = tmp_path / "pos-stores.yaml"
    file.write_bytes(VALID_APPLICATION.encode("latin-1"))
    # Everything before the first accented letter is ASCII, so its index is its byte offset.
    byte = VALID_APPLICATION.index("à")
    assert load_record(file, Application) == [
        RecordError(
            file, "", f"the file is not valid UTF-8 (byte {byte}): save it as UTF-8"
        )
    ]


def test_reports_a_syntax_error_with_its_position(tmp_path):
    file = write(tmp_path, "pos-stores.yaml", "name: A\n  bad: [\n")
    [error] = load_record(file, Application)
    assert error.field == ""
    assert error.message == "mapping values are not allowed here (line 2, column 6)"


def test_reports_a_duplicate_key_at_the_root(tmp_path):
    file = write(tmp_path, "pos-stores.yaml", "id: pos-stores\nname: A\nname: B\n")
    assert load_record(file, Application) == [
        RecordError(file, "", "duplicate key 'name' (line 3, column 1)")
    ]


def test_reports_a_duplicate_key_inside_a_nested_mapping(tmp_path):
    text = "id: pos-stores\nlifecycle:\n  active: 2020-01-01\n  active: 2021-01-01\n"
    file = write(tmp_path, "pos-stores.yaml", text)
    assert load_record(file, Application) == [
        RecordError(file, "", "duplicate key 'active' (line 4, column 3)")
    ]


@pytest.mark.parametrize("text", ["", "# nothing yet\n"])
def test_reports_an_empty_file(tmp_path, text):
    file = write(tmp_path, "pos-stores.yaml", text)
    assert load_record(file, Application) == [
        RecordError(file, "", "the file is empty")
    ]


@pytest.mark.parametrize(
    ("text", "kind"),
    [("- a\n- b\n", "a list"), ("hello\n", "text"), ("42\n", "a number")],
)
def test_reports_a_root_that_is_not_a_mapping(tmp_path, text, kind):
    file = write(tmp_path, "pos-stores.yaml", text)
    assert load_record(file, Application) == [
        RecordError(file, "", f"the file must contain a mapping of fields, not {kind}")
    ]


def test_reports_pydantic_errors_with_the_file(tmp_path):
    file = write(tmp_path, "pos-stores.yaml", VALID_APPLICATION + "tags: [retail]\n")
    assert load_record(file, Application) == [
        RecordError(file, "tags", "Extra inputs are not permitted")
    ]


def test_reports_an_id_that_does_not_match_the_file_name(tmp_path):
    file = write(tmp_path, "other.yaml", VALID_APPLICATION)
    assert load_record(file, Application) == [
        RecordError(file, "id", "'pos-stores' does not match the file name 'other'")
    ]


def test_checks_the_file_name_only_on_a_valid_record(tmp_path):
    file = write(tmp_path, "other.yaml", VALID_APPLICATION + "tags: [retail]\n")
    [error] = load_record(file, Application)
    assert error.field == "tags"


# Step 3: directories, phase 2 and the entry point (ADR-0003, decisions 2, 4, 5, 6, 7).

INVENTORY = Path(__file__).parent.parent / "inventory"


def application_text(record_id, depends_on=(), it_components=()):
    text = (
        f"id: {record_id}\nname: {record_id}\ndescription: d\n"
        "business_criticality: administrative_service\nhosting: cloud\n"
        "lifecycle:\n  active: 2020-01-01\n"
    )
    if depends_on:
        text += "depends_on:\n"
        for target in depends_on:
            text += f"  - application: {target}\n    type: api\n"
    if it_components:
        text += "it_components:\n" + "".join(f"  - {c}\n" for c in it_components)
    return text


def component_text(record_id):
    return f"id: {record_id}\nname: {record_id}\ncategory: software\n"


@pytest.fixture
def root(tmp_path):
    (tmp_path / "applications").mkdir()
    (tmp_path / "it-components").mkdir()
    return tmp_path


def errors_of(root):
    with pytest.raises(InventoryError) as error:
        load_inventory(root)
    return [str(e).replace(f"{root}/", "") for e in error.value.errors]


def test_empty_directories_give_an_empty_inventory(root):
    assert load_inventory(root) == Inventory({}, {})


def test_reports_each_missing_directory(tmp_path):
    assert errors_of(tmp_path) == [
        "applications: directory not found",
        "it-components: directory not found",
    ]


def test_records_are_indexed_by_id_in_file_name_order(root):
    write(root / "applications", "zeta.yaml", application_text("zeta"))
    write(root / "applications", "alpha.yaml", application_text("alpha"))
    assert list(load_inventory(root).applications) == ["alpha", "zeta"]


def test_reports_a_yml_file_and_says_what_to_do(root):
    write(root / "applications", "pos-stores.yml", application_text("pos-stores"))
    assert errors_of(root) == ["applications/pos-stores.yml: use the .yaml extension"]


@pytest.mark.parametrize("name", ["notes.txt", "pos-stores.yaml.bak"])
def test_reports_a_file_that_is_not_a_record(root, name):
    write(root / "applications", name, "")
    assert errors_of(root) == [
        f"applications/{name}: not a record file: only .yaml files are read here"
    ]


def test_reports_a_subdirectory(root):
    (root / "applications" / "archive").mkdir()
    assert errors_of(root) == [
        "applications/archive: not a record file: only .yaml files are read here"
    ]


def test_ignores_hidden_files(root):
    write(root / "applications", ".gitkeep", "")
    write(root / "it-components", ".DS_Store", "")
    assert load_inventory(root) == Inventory({}, {})


def test_collects_record_errors_from_both_directories(root):
    write(root / "applications", "a.yaml", "")
    write(root / "it-components", "c.yaml", component_text("wrong"))
    assert errors_of(root) == [
        "applications/a.yaml: the file is empty",
        "it-components/c.yaml: id: 'wrong' does not match the file name 'c'",
    ]


def test_skips_reference_checks_when_a_record_is_invalid(root):
    write(root / "applications", "a.yaml", application_text("a", depends_on=["ghost"]))
    write(root / "it-components", "c.yaml", "")
    assert errors_of(root) == ["it-components/c.yaml: the file is empty"]


def test_reports_an_unknown_dependency_target(root):
    write(
        root / "applications",
        "a.yaml",
        application_text("a", depends_on=["b", "ghost"]),
    )
    write(root / "applications", "b.yaml", application_text("b"))
    assert errors_of(root) == [
        (
            "applications/a.yaml: depends_on[1].application: "
            "unknown application 'ghost': there is no applications/ghost.yaml"
        )
    ]


def test_reports_an_unknown_it_component(root):
    write(
        root / "applications", "a.yaml", application_text("a", it_components=["nope"])
    )
    assert errors_of(root) == [
        (
            "applications/a.yaml: it_components[0]: "
            "unknown IT component 'nope': there is no it-components/nope.yaml"
        )
    ]


def test_reports_an_id_shared_by_an_application_and_a_component(root):
    write(root / "applications", "erp.yaml", application_text("erp"))
    write(root / "it-components", "erp.yaml", component_text("erp"))
    assert errors_of(root) == [
        "it-components/erp.yaml: id: 'erp' is also the id of an application"
    ]


def test_loads_a_valid_inventory_with_references(root):
    write(root / "applications", "a.yaml", application_text("a", ["b"], ["db"]))
    write(root / "applications", "b.yaml", application_text("b"))
    write(root / "it-components", "db.yaml", component_text("db"))
    inventory = load_inventory(root)
    assert inventory.applications["a"].depends_on[0].application == "b"
    assert list(inventory.it_components) == ["db"]


def test_the_real_inventory_loads_without_the_templates():
    inventory = load_inventory(INVENTORY)
    assert "application" not in inventory.applications
    assert "it-component" not in inventory.it_components
