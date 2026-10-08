"""Tests for the ITComponent model (ADR-0001, section "IT component record")."""

from datetime import date

import pytest
from pydantic import ValidationError

from archinv.models import ITComponent, ITComponentCategory, Lifecycle

MINIMAL = {
    "id": "oracle-database-11g",
    "name": "Oracle Database 11g",
    "category": "software",
}


def test_categories_match_the_adr():
    assert [c.value for c in ITComponentCategory] == ["software", "hardware", "service"]


def test_accepts_a_minimal_record():
    component = ITComponent(**MINIMAL)
    assert component.vendor is None
    assert component.version is None
    assert component.lifecycle is None


def test_accepts_the_adr_example():
    component = ITComponent(
        **MINIMAL,
        vendor="Oracle",
        version="11.2",
        lifecycle={"active": "2009-09-01", "end_of_life": "2020-12-31"},
    )
    assert isinstance(component.lifecycle, Lifecycle)
    assert component.lifecycle.end_of_life == date(2020, 12, 31)


def test_converts_text_to_category():
    assert ITComponent(**MINIMAL).category is ITComponentCategory.SOFTWARE


def test_accepts_an_empty_lifecycle_block():
    # "lifecycle: {}" in YAML: present, but no date is known.
    assert ITComponent(**MINIMAL, lifecycle={}).lifecycle == Lifecycle()


def test_accepts_a_lifecycle_left_blank():
    # "lifecycle:" with no value is read by YAML as None.
    assert ITComponent(**MINIMAL, lifecycle=None).lifecycle is None


def test_strips_whitespace_around_name():
    assert ITComponent(**{**MINIMAL, "name": "  Oracle  "}).name == "Oracle"


def test_rejects_malformed_id():
    with pytest.raises(ValidationError) as error:
        ITComponent(**{**MINIMAL, "id": "Oracle_DB"})
    first = error.value.errors()[0]
    assert first["type"] == "string_pattern_mismatch"
    assert first["loc"] == ("id",)


@pytest.mark.parametrize("name", ["", "   "])
def test_rejects_empty_name(name):
    with pytest.raises(ValidationError) as error:
        ITComponent(**{**MINIMAL, "name": name})
    first = error.value.errors()[0]
    assert first["type"] == "string_too_short"
    assert first["loc"] == ("name",)


@pytest.mark.parametrize("value", ["Software", "middleware", None])
def test_rejects_unknown_category(value):
    with pytest.raises(ValidationError) as error:
        ITComponent(**{**MINIMAL, "category": value})
    first = error.value.errors()[0]
    assert first["type"] == "enum"
    assert first["loc"] == ("category",)


@pytest.mark.parametrize("value", [1.0, 19])
def test_rejects_version_that_is_not_text(value):
    # In YAML, version: 1.0 without quotes is a number, not text.
    with pytest.raises(ValidationError) as error:
        ITComponent(**{**MINIMAL, "version": value})
    first = error.value.errors()[0]
    assert first["type"] == "string_type"
    assert first["loc"] == ("version",)


def test_rejects_lifecycle_dates_out_of_order():
    with pytest.raises(ValidationError, match="is before") as error:
        ITComponent(
            **MINIMAL, lifecycle={"active": "2020-01-01", "end_of_life": "2019-01-01"}
        )
    assert error.value.errors()[0]["loc"] == ("lifecycle",)


def test_reports_the_path_of_a_malformed_date_inside_lifecycle():
    with pytest.raises(ValidationError) as error:
        ITComponent(**MINIMAL, lifecycle={"active": "soon"})
    assert error.value.errors()[0]["loc"] == ("lifecycle", "active")


def test_reports_the_path_of_an_unknown_field_inside_lifecycle():
    with pytest.raises(ValidationError) as error:
        ITComponent(**MINIMAL, lifecycle={"retired": "2020-01-01"})
    first = error.value.errors()[0]
    assert first["type"] == "extra_forbidden"
    assert first["loc"] == ("lifecycle", "retired")


def test_rejects_lifecycle_that_is_not_a_mapping():
    with pytest.raises(ValidationError) as error:
        ITComponent(**MINIMAL, lifecycle="2020-01-01")
    first = error.value.errors()[0]
    assert first["type"] == "model_type"
    assert first["loc"] == ("lifecycle",)


@pytest.mark.parametrize("field", ["id", "name", "category"])
def test_rejects_missing_required_field(field):
    data = {key: value for key, value in MINIMAL.items() if key != field}
    with pytest.raises(ValidationError) as error:
        ITComponent(**data)
    first = error.value.errors()[0]
    assert first["type"] == "missing"
    assert first["loc"] == (field,)


def test_rejects_end_of_life_outside_the_lifecycle_block():
    # A likely mistake: the date belongs under lifecycle.
    with pytest.raises(ValidationError) as error:
        ITComponent(**MINIMAL, end_of_life="2020-12-31")
    first = error.value.errors()[0]
    assert first["type"] == "extra_forbidden"
    assert first["loc"] == ("end_of_life",)
