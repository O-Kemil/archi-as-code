"""Command line interface, as specified in ADR-0004 and ADR-0006."""

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from archinv.graph import build_graph
from archinv.loader import InventoryError, load_inventory
from archinv.report import render

DEFAULT_INVENTORY = Path("inventory")


def plural(count: int, word: str) -> str:
    """'1 error', '2 errors'. Words that do not take an s are not needed yet."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def iso_date(text: str) -> date:
    """argparse type for YYYY-MM-DD; the function name appears in the usage error."""
    return date.fromisoformat(text)


def add_inventory_option(parser: argparse.ArgumentParser) -> None:
    """The option every sub-command shares (ADR-0004, decision 2)."""
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
        help="inventory directory (default: %(default)s)",
    )


def run_validate(args: argparse.Namespace) -> int:
    inventory = load_inventory(args.inventory)
    applications = plural(len(inventory.applications), "application")
    it_components = plural(len(inventory.it_components), "IT component")
    print(f"Inventory valid: {applications}, {it_components}")
    return 0


def today() -> date:
    """Today in UTC, the same date on a laptop and in the CI at any hour."""
    return datetime.now(tz=UTC).date()


def run_report(args: argparse.Namespace) -> int:
    inventory = load_inventory(args.inventory)
    reference = args.reference_date or today()
    text = render(inventory, build_graph(inventory), reference, args.deadline)
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
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

    report = subparsers.add_parser(
        "report", help="write the anomaly report in Markdown"
    )
    add_inventory_option(report)
    report.add_argument(
        "--reference-date",
        type=iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="date for lifecycle phases and end of life (default: today)",
    )
    report.add_argument(
        "--deadline",
        type=iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="also list the components reaching end of life on or before this date",
    )
    report.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="write the report to this file, creating its directory (default: standard output)",
    )
    report.set_defaults(run=run_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: returns the exit status (ADR-0004, decision 3)."""
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except InventoryError as error:
        print(error, file=sys.stderr)
        print(plural(len(error.errors), "error"), file=sys.stderr)
        return 1
