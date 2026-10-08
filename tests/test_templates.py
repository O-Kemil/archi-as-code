"""The record templates in inventory/templates/ must stay valid against the schema."""

from pathlib import Path

import yaml

from archinv.models import ITComponent

TEMPLATES = Path(__file__).parent.parent / "inventory" / "templates"


def test_it_component_template_is_valid():
    data = yaml.safe_load((TEMPLATES / "it-component.yaml").read_text())
    component = ITComponent.model_validate(data)
    assert component.id == "it-component"
