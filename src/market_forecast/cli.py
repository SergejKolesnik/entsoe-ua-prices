"""Command-line entry point for safe one-shot operations."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level CLI parser."""

    parser = argparse.ArgumentParser(
        prog="market-forecast",
        description="Ukraine energy market data foundation",
    )
    parser.add_argument("--version", action="store_true", help="Print the package version and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI without triggering network or persistence side effects."""

    args = build_parser().parse_args(argv)
    if args.version:
        from market_forecast import __version__

        print(__version__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
