"""Tests for the command line (ADR-0004)."""

from importlib.metadata import entry_points

import pytest

from archinv.cli import main

VALID_APPLICATION = """\
id: a
name: A
description: d
business_criticality: administrative_service
hosting: cloud
lifecycle:
  active: 2020-01-01
"""


@pytest.fixture
def root(tmp_path):
    (tmp_path / "applications").mkdir()
    (tmp_path / "it-components").mkdir()
    return tmp_path


def test_valid_inventory_prints_a_summary_and_returns_0(root, capsys):
    (root / "applications" / "a.yaml").write_text(VALID_APPLICATION, encoding="utf-8")
    assert main(["validate", "--inventory", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "Inventory valid: 1 application, 0 IT components\n"
    assert captured.err == ""


def test_empty_inventory_is_valid(root, capsys):
    assert main(["validate", "--inventory", str(root)]) == 0
    assert (
        capsys.readouterr().out == "Inventory valid: 0 applications, 0 IT components\n"
    )


def test_invalid_inventory_prints_errors_on_stderr_and_returns_1(root, capsys):
    (root / "applications" / "a.yaml").write_text("", encoding="utf-8")
    assert main(["validate", "--inventory", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"{root}/applications/a.yaml: the file is empty\n1 error\n"


def test_counts_several_errors(root, capsys):
    (root / "applications" / "a.yaml").write_text("", encoding="utf-8")
    (root / "applications" / "b.yaml").write_text("", encoding="utf-8")
    assert main(["validate", "--inventory", str(root)]) == 1
    assert capsys.readouterr().err.endswith("\n2 errors\n")


def test_missing_directory_is_an_inventory_error(tmp_path, capsys):
    assert main(["validate", "--inventory", str(tmp_path / "nope")]) == 1
    assert "nope/applications: directory not found" in capsys.readouterr().err


def test_default_inventory_is_relative_to_the_current_directory(
    root, monkeypatch, capsys
):
    monkeypatch.chdir(root.parent)
    root.rename(root.parent / "inventory")
    assert main(["validate"]) == 0
    assert capsys.readouterr().out.startswith("Inventory valid")


@pytest.mark.parametrize("argv", [[], ["bogus"], ["validate", "--nope"]])
def test_usage_error_exits_with_status_2(argv, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert exit_info.value.code == 2
    assert "usage: archinv" in capsys.readouterr().err


def test_help_mentions_the_default_inventory(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["validate", "--help"])
    assert exit_info.value.code == 0
    assert "(default: inventory)" in capsys.readouterr().out


def test_the_installed_command_points_to_the_cli_module():
    [entry_point] = entry_points(group="console_scripts", name="archinv")
    assert entry_point.value == "archinv.cli:main"
