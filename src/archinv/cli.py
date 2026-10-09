"""Command line interface, as specified in ADR-0004."""

import argparse
import sys
from pathlib import Path

from archinv.loader import InventoryError, load_inventory

DEFAULT_INVENTORY = Path("inventory")


def plural(count: int, word: str) -> str:
    """'1 error', '2 errors'. Words that do not take an s are not needed yet."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def add_inventory_option(parser: argparse.ArgumentParser) -> None:
    """The option every sub-command shares (ADR-0004, decision 2)."""
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
        help="inventory directory (default: %(default)s)",
    )


def run_validate(args: argparse.Namespace) -> int:
    try:
        inventory = load_inventory(args.inventory)
    except InventoryError as error:
        print(error, file=sys.stderr)
        print(plural(len(error.errors), "error"), file=sys.stderr)
        return 1
    applications = plural(len(inventory.applications), "application")
    it_components = plural(len(inventory.it_components), "IT component")
    print(f"Inventory valid: {applications}, {it_components}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="archinv", description="Application inventory as code."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser(
        "validate", help="check every record and every reference"
    )
    add_inventory_option(validate)
    validate.set_defaults(run=run_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: returns the exit status (ADR-0004, decision 3)."""
    args = build_parser().parse_args(argv)
    return args.run(args)
