"""Tests for the Lifecycle model (ADR-0001, section "Lifecycle object")."""

from datetime import date

import pytest
from pydantic import ValidationError

from archinv.models import Lifecycle, LifecyclePhase

FULL = {
    "plan": date(2014, 1, 1),
    "phase_in": date(2014, 9, 1),
    "active": date(2015, 3, 1),
    "phase_out": date(2027, 6, 30),
    "end_of_life": date(2027, 12, 31),
}


def test_phase_names_match_field_names():
    assert [phase.value for phase in LifecyclePhase] == list(Lifecycle.model_fields)


def test_accepts_all_phases_in_order():
    lifecycle = Lifecycle(**FULL)
    assert lifecycle.active == date(2015, 3, 1)


def test_accepts_a_single_phase():
    lifecycle = Lifecycle(active=date(2015, 3, 1))
    assert lifecycle.plan is None


def test_accepts_no_phase_at_all():
    assert Lifecycle().dated_phases() == []


def test_converts_iso_text_to_date():
    lifecycle = Lifecycle(active="2015-03-01")
    assert lifecycle.active == date(2015, 3, 1)


def test_accepts_two_phases_on_the_same_day():
    Lifecycle(phase_out=date(2027, 6, 30), end_of_life=date(2027, 6, 30))


@pytest.mark.parametrize("value", ["2015-13-01", "01/03/2015", "soon", 20150301, True])
def test_rejects_malformed_date(value):
    with pytest.raises(ValidationError) as error:
        Lifecycle(active=value)
    assert error.value.errors()[0]["loc"] == ("active",)


def test_rejects_unknown_field():
    with pytest.raises(ValidationError) as error:
        Lifecycle(retired=date(2030, 1, 1))
    first = error.value.errors()[0]
    assert first["type"] == "extra_forbidden"
    assert first["loc"] == ("retired",)


@pytest.mark.parametrize(
    "dates",
    [
        {"active": date(2020, 1, 1), "phase_out": date(2019, 1, 1)},
        {"plan": date(2020, 1, 1), "end_of_life": date(2019, 1, 1)},
        {**FULL, "phase_in": date(2030, 1, 1)},
    ],
)
def test_rejects_dates_out_of_order(dates):
    with pytest.raises(ValidationError, match="is before"):
        Lifecycle(**dates)


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        (date(2013, 12, 31), None),
        (date(2014, 1, 1), LifecyclePhase.PLAN),
        (date(2014, 12, 1), LifecyclePhase.PHASE_IN),
        (date(2026, 10, 5), LifecyclePhase.ACTIVE),
        (date(2027, 6, 30), LifecyclePhase.PHASE_OUT),
        (date(2040, 1, 1), LifecyclePhase.END_OF_LIFE),
    ],
)
def test_current_phase_on_a_full_lifecycle(reference, expected):
    assert Lifecycle(**FULL).current_phase(reference) == expected


def test_current_phase_skips_missing_phases():
    lifecycle = Lifecycle(active=date(2015, 3, 1), end_of_life=date(2027, 12, 31))
    assert lifecycle.current_phase(date(2020, 1, 1)) == LifecyclePhase.ACTIVE
    assert lifecycle.current_phase(date(2028, 1, 1)) == LifecyclePhase.END_OF_LIFE


def test_current_phase_of_an_empty_lifecycle_is_none():
    assert Lifecycle().current_phase(date(2026, 10, 5)) is None
