"""Command line interface, as specified in ADR-0004, ADR-0006, ADR-0007 and ADR-0008."""

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from archinv.archi import DEFAULT_MODEL_NAME, build_model, to_xml
from archinv.graph import build_graph
from archinv.loader import InventoryError, load_inventory
from archinv.maps import (
    end_of_life_view,
    focus_view,
    global_view,
    hosting_view,
    to_dot,
    to_mermaid,
)
from archinv.report import render

DEFAULT_INVENTORY = Path("inventory")
RENDERERS = {"mermaid": to_mermaid, "dot": to_dot}
VIEWS = ["global", "hosting", "focus", "end-of-life"]


def plural(count: int, word: str) -> str:
    """'1 error', '2 errors'. Words that do not take an s are not needed yet."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def iso_date(text: str) -> date:
    """argparse type for YYYY-MM-DD; the function name appears in the usage error."""
    return date.fromisoformat(text)


def today() -> date:
    """Today in UTC, the same date on a laptop and in the CI at any hour."""
    return datetime.now(tz=UTC).date()


def add_inventory_option(parser: argparse.ArgumentParser) -> None:
    """The option every sub-command shares (ADR-0004, decision 2)."""
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
        help="inventory directory (default: %(default)s)",
    )


def add_date_options(parser: argparse.ArgumentParser) -> None:
    """Reference date and deadline, shared by report and map (ADR-0006, ADR-0007)."""
    parser.add_argument(
        "--reference-date",
        type=iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="date for lifecycle phases and end of life (default: today)",
    )
    parser.add_argument(
        "--deadline",
        type=iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="also consider the components reaching end of life on or before this date",
    )


def add_output_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="write to this file, creating its directory (default: standard output)",
    )


def write_output(text: str, output: Path | None) -> None:
    """To stdout, or to the file, creating its directory."""
    if output is None:
        sys.stdout.write(text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")


def run_validate(args: argparse.Namespace) -> int:
    inventory = load_inventory(args.inventory)
    applications = plural(len(inventory.applications), "application")
    it_components = plural(len(inventory.it_components), "IT component")
    print(f"Inventory valid: {applications}, {it_components}")
    return 0


def run_report(args: argparse.Namespace) -> int:
    inventory = load_inventory(args.inventory)
    reference = args.reference_date or today()
    text = render(inventory, build_graph(inventory), reference, args.deadline)
    write_output(text, args.output)
    return 0


def run_map(args: argparse.Namespace) -> int:
    if (args.view == "focus") != (args.focus is not None):
        args.parser.error("--focus ID is required with --view focus, and only with it")
    inventory = load_inventory(args.inventory)
    graph = build_graph(inventory)
    reference = args.reference_date or today()
    if args.view == "global":
        view = global_view(inventory, graph, reference, args.deadline)
    elif args.view == "hosting":
        view = hosting_view(inventory, graph, reference, args.deadline)
    elif args.view == "end-of-life":
        view = end_of_life_view(inventory, graph, reference, args.deadline)
    else:
        try:
            view = focus_view(inventory, graph, args.focus, reference, args.deadline)
        except ValueError as error:
            args.parser.error(str(error))
    write_output(RENDERERS[args.format](view), args.output)
    return 0


def run_archi(args: argparse.Namespace) -> int:
    if not args.name.strip():
        args.parser.error("--name must not be empty")
    inventory = load_inventory(args.inventory)
    reference = args.reference_date or today()
    model = build_model(inventory, build_graph(inventory), reference, args.name.strip())
    write_output(to_xml(model), args.output)
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
    add_date_options(report)
    add_output_option(report)
    report.set_defaults(run=run_report)

    map_ = subparsers.add_parser("map", help="write a dependency map in Mermaid or DOT")
    add_inventory_option(map_)
    map_.add_argument("--format", choices=sorted(RENDERERS), required=True)
    map_.add_argument(
        "--view",
        choices=VIEWS,
        required=True,
        help="global: every application; hosting: grouped by hosting; focus: one application"
        " and its neighbours; end-of-life: components past end of life and their applications",
    )
    map_.add_argument("--focus", metavar="ID", help="the application of the focus view")
    add_date_options(map_)
    add_output_option(map_)
    map_.set_defaults(run=run_map, parser=map_)

    archi = subparsers.add_parser(
        "archi", help="write the inventory as an ArchiMate exchange file"
    )
    add_inventory_option(archi)
    # No --deadline here: the export writes dates, it compares nothing to a deadline.
    archi.add_argument(
        "--reference-date",
        type=iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="date of the lifecycle_phase property (default: today)",
    )
    archi.add_argument(
        "--name",
        default=DEFAULT_MODEL_NAME,
        help="name of the model (default: %(default)s)",
    )
    add_output_option(archi)
    archi.set_defaults(run=run_archi, parser=archi)
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
