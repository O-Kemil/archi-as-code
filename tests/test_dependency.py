"""Tests for the Dependency model (ADR-0001, section "Dependency object")."""

import pytest
from pydantic import ValidationError

from archinv.models import Dependency, DependencyType


def test_dependency_types_match_the_adr():
    assert [kind.value for kind in DependencyType] == [
        "api",
        "file",
        "database",
        "event",
    ]


def test_accepts_a_minimal_dependency():
    dependency = Dependency(application="erp-finance", type="file")
    assert dependency.application == "erp-finance"
    assert dependency.description is None


def test_converts_text_to_dependency_type():
    dependency = Dependency(application="erp-finance", type="file")
    assert dependency.type is DependencyType.FILE


def test_accepts_a_description():
    dependency = Dependency(
        application="erp-finance", type="file", description="Nightly sales export."
    )
    assert dependency.description == "Nightly sales export."


def test_accepts_a_description_left_blank():
    # YAML reads "description:" with no value as None.
    Dependency(application="erp-finance", type="file", description=None)


@pytest.mark.parametrize("slug", ["a", "erp-finance", "crm2", "2024", "a-1-b"])
def test_accepts_valid_slug(slug):
    assert Dependency(application=slug, type="api").application == slug


@pytest.mark.parametrize(
    "slug",
    [
        "",
        "ERP",
        "erp_finance",
        "-erp",
        "erp-",
        "erp--finance",
        "erp finance",
        "erp\n",
        "été",
    ],
)
def test_rejects_malformed_slug(slug):
    with pytest.raises(ValidationError) as error:
        Dependency(application=slug, type="api")
    first = error.value.errors()[0]
    assert first["type"] == "string_pattern_mismatch"
    assert first["loc"] == ("application",)


@pytest.mark.parametrize("value", [2024, None])
def test_rejects_application_that_is_not_text(value):
    with pytest.raises(ValidationError) as error:
        Dependency(application=value, type="api")
    first = error.value.errors()[0]
    assert first["type"] == "string_type"
    assert first["loc"] == ("application",)


@pytest.mark.parametrize("value", ["API", "rest", None])
def test_rejects_unknown_type(value):
    with pytest.raises(ValidationError) as error:
        Dependency(application="erp-finance", type=value)
    first = error.value.errors()[0]
    assert first["type"] == "enum"
    assert first["loc"] == ("type",)


@pytest.mark.parametrize("field", ["application", "type"])
def test_rejects_missing_required_field(field):
    data = {"application": "erp-finance", "type": "api"}
    del data[field]
    with pytest.raises(ValidationError) as error:
        Dependency(**data)
    first = error.value.errors()[0]
    assert first["type"] == "missing"
    assert first["loc"] == (field,)


def test_rejects_unknown_field():
    with pytest.raises(ValidationError) as error:
        Dependency(application="erp-finance", type="api", kind="sync")
    first = error.value.errors()[0]
    assert first["type"] == "extra_forbidden"
    assert first["loc"] == ("kind",)
