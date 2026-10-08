"""Tests for the Application model (ADR-0001, section "Application record")."""

import pytest
from pydantic import ValidationError

from archinv.models import Application, BusinessCriticality, Dependency, Hosting

MINIMAL = {
    "id": "pos-stores",
    "name": "Point of sale",
    "description": "Cash register software used in every store.",
    "business_criticality": "mission_critical",
    "hosting": "store",
    "lifecycle": {"active": "2015-03-01"},
}

ADR_EXAMPLE = {
    **MINIMAL,
    "business_owner": "Retail operations",
    "technical_owner": "Store IT team",
    "lifecycle": {"active": "2015-03-01", "phase_out": "2027-06-30"},
    "depends_on": [
        {
            "application": "inventory-management",
            "type": "api",
            "description": "Stock lookup.",
        },
        {
            "application": "erp-finance",
            "type": "file",
            "description": "Nightly sales export.",
        },
    ],
    "it_components": ["oracle-database-11g", "windows-server-2012"],
}


def test_criticality_levels_match_the_adr():
    assert [level.value for level in BusinessCriticality] == [
        "mission_critical",
        "business_critical",
        "business_operational",
        "administrative_service",
    ]


def test_hosting_values_match_the_adr():
    assert [value.value for value in Hosting] == [
        "data_center",
        "cloud",
        "saas",
        "store",
    ]


def test_accepts_the_adr_example():
    application = Application(**ADR_EXAMPLE)
    assert isinstance(application.depends_on[0], Dependency)
    assert application.depends_on[1].application == "erp-finance"
    assert application.it_components == ["oracle-database-11g", "windows-server-2012"]


def test_accepts_a_minimal_record():
    application = Application(**MINIMAL)
    assert application.business_owner is None
    assert application.technical_owner is None
    assert application.depends_on == []
    assert application.it_components == []


def test_default_lists_are_not_shared_between_records():
    first = Application(**MINIMAL)
    second = Application(**MINIMAL)
    first.it_components.append("oracle-database-11g")
    assert second.it_components == []


def test_converts_text_to_enumerations():
    application = Application(**MINIMAL)
    assert application.business_criticality is BusinessCriticality.MISSION_CRITICAL
    assert application.hosting is Hosting.STORE


def test_missing_business_owner_is_not_an_error():
    # ADR-0001: an application without owner is a report anomaly, not a validation error.
    assert "business_owner" not in MINIMAL
    Application(**MINIMAL)


def test_accepts_two_dependencies_on_different_targets():
    application = Application(**ADR_EXAMPLE)
    assert len(application.depends_on) == 2


def test_accepts_the_same_target_with_different_types():
    # ADR-0001, amendment of 2026-10-08: an API call and a file transfer to the same
    # application are two real links.
    application = Application(
        **MINIMAL,
        depends_on=[
            {"application": "erp-finance", "type": "api"},
            {"application": "erp-finance", "type": "file"},
        ],
    )
    assert len(application.depends_on) == 2


@pytest.mark.parametrize("field", ["name", "description"])
def test_rejects_empty_required_text(field):
    with pytest.raises(ValidationError) as error:
        Application(**{**MINIMAL, field: "   "})
    first = error.value.errors()[0]
    assert first["type"] == "string_too_short"
    assert first["loc"] == (field,)


def test_rejects_unknown_criticality():
    with pytest.raises(ValidationError) as error:
        Application(**{**MINIMAL, "business_criticality": "high"})
    first = error.value.errors()[0]
    assert first["type"] == "enum"
    assert first["loc"] == ("business_criticality",)


def test_rejects_unknown_hosting():
    with pytest.raises(ValidationError) as error:
        Application(**{**MINIMAL, "hosting": "on_prem"})
    first = error.value.errors()[0]
    assert first["type"] == "enum"
    assert first["loc"] == ("hosting",)


def test_rejects_lifecycle_without_any_date():
    with pytest.raises(ValidationError, match="at least one date") as error:
        Application(**{**MINIMAL, "lifecycle": {}})
    assert error.value.errors()[0]["loc"] == ("lifecycle",)


def test_rejects_lifecycle_left_blank():
    # "lifecycle:" with no value is read by YAML as None.
    with pytest.raises(ValidationError) as error:
        Application(**{**MINIMAL, "lifecycle": None})
    first = error.value.errors()[0]
    assert first["type"] == "model_type"
    assert first["loc"] == ("lifecycle",)


def test_rejects_self_dependency():
    with pytest.raises(ValidationError, match="depends on itself") as error:
        Application(
            **MINIMAL, depends_on=[{"application": "pos-stores", "type": "api"}]
        )
    assert error.value.errors()[0]["loc"] == ("depends_on",)


def test_rejects_the_same_target_and_type_twice():
    with pytest.raises(
        ValidationError, match="erp-finance \\(api\\) is listed twice"
    ) as error:
        Application(
            **MINIMAL,
            depends_on=[
                {
                    "application": "erp-finance",
                    "type": "api",
                    "description": "Stock lookup.",
                },
                {
                    "application": "erp-finance",
                    "type": "api",
                    "description": "Price lookup.",
                },
            ],
        )
    assert error.value.errors()[0]["loc"] == ("depends_on",)


def test_reports_the_path_of_an_error_inside_a_dependency():
    with pytest.raises(ValidationError) as error:
        Application(
            **MINIMAL,
            depends_on=[
                {"application": "erp-finance", "type": "api"},
                {"application": "crm", "type": "rest"},
            ],
        )
    first = error.value.errors()[0]
    assert first["type"] == "enum"
    assert first["loc"] == ("depends_on", 1, "type")


@pytest.mark.parametrize("field", ["depends_on", "it_components"])
@pytest.mark.parametrize("value", [None, "erp-finance"])
def test_rejects_list_field_that_is_not_a_list(field, value):
    # "depends_on:" left blank is read by YAML as None: delete the block or write [].
    with pytest.raises(ValidationError) as error:
        Application(**{**MINIMAL, field: value})
    first = error.value.errors()[0]
    assert first["type"] == "list_type"
    assert first["loc"] == (field,)


def test_reports_the_path_of_a_malformed_component_id():
    with pytest.raises(ValidationError) as error:
        Application(**MINIMAL, it_components=["oracle-database-11g", "Windows"])
    first = error.value.errors()[0]
    assert first["type"] == "string_pattern_mismatch"
    assert first["loc"] == ("it_components", 1)


def test_rejects_the_same_component_twice():
    with pytest.raises(ValidationError, match="listed twice") as error:
        Application(
            **MINIMAL, it_components=["oracle-database-11g", "oracle-database-11g"]
        )
    assert error.value.errors()[0]["loc"] == ("it_components",)


@pytest.mark.parametrize(
    "field",
    ["id", "name", "description", "business_criticality", "hosting", "lifecycle"],
)
def test_rejects_missing_required_field(field):
    data = {key: value for key, value in MINIMAL.items() if key != field}
    with pytest.raises(ValidationError) as error:
        Application(**data)
    first = error.value.errors()[0]
    assert first["type"] == "missing"
    assert first["loc"] == (field,)


def test_rejects_unknown_field():
    with pytest.raises(ValidationError) as error:
        Application(**MINIMAL, tags=["retail"])
    first = error.value.errors()[0]
    assert first["type"] == "extra_forbidden"
    assert first["loc"] == ("tags",)
