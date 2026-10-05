"""Record models for the inventory, as specified in ADR-0001."""

from datetime import date
from enum import StrEnum
from itertools import pairwise
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class StrictModel(BaseModel):
    """Base class for every record model: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class LifecyclePhase(StrEnum):
    """The five lifecycle phases, in order. Values match the Lifecycle field names."""

    PLAN = "plan"
    PHASE_IN = "phase_in"
    ACTIVE = "active"
    PHASE_OUT = "phase_out"
    END_OF_LIFE = "end_of_life"


class Lifecycle(StrictModel):
    """Dates at which a record enters each phase. All optional, in chronological order."""

    plan: date | None = None
    phase_in: date | None = None
    active: date | None = None
    phase_out: date | None = None
    end_of_life: date | None = None

    def dated_phases(self) -> list[tuple[LifecyclePhase, date]]:
        """Return the phases that have a date, in lifecycle order."""
        dated = []
        for phase in LifecyclePhase:
            value = getattr(self, phase.value)
            if value is not None:
                dated.append((phase, value))
        return dated

    @model_validator(mode="after")
    def check_chronological_order(self) -> Self:
        for (earlier, earlier_date), (later, later_date) in pairwise(
            self.dated_phases()
        ):
            if later_date < earlier_date:
                raise ValueError(
                    f"{later.value} ({later_date}) is before {earlier.value} ({earlier_date})"
                )
        return self

    def current_phase(self, reference: date) -> LifecyclePhase | None:
        """Return the latest phase started on or before the reference date."""
        current = None
        for phase, value in self.dated_phases():
            if value <= reference:
                current = phase
        return current
