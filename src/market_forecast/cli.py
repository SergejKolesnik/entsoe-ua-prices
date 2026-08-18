"""Command-line entry point for safe one-shot operations."""

from __future__ import annotations

import argparse
from datetime import date


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level CLI parser."""

    parser = argparse.ArgumentParser(
        prog="market-forecast",
        description="Ukraine energy market data foundation",
    )
    parser.add_argument("--version", action="store_true", help="Print the package version and exit.")
    subparsers = parser.add_subparsers(dest="command")
    initialize = subparsers.add_parser("init-db", help="Create the local SQLite schema.")
    initialize.add_argument("--database", help="Override DATABASE_PATH.")

    collect = subparsers.add_parser("collect", help="Collect one explicit delivery day.")
    collect.add_argument("--date", required=True, type=date.fromisoformat, dest="delivery_date")
    collect.add_argument("--source", required=True, choices=("entsoe", "operator"))
    collect.add_argument("--bidding-zone", help="Required EIC bidding zone for ENTSO-E.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI without triggering network or persistence side effects."""

    args = build_parser().parse_args(argv)
    if args.version:
        from market_forecast import __version__

        print(__version__)
        return 0
    if args.command == "init-db":
        from pathlib import Path

        from market_forecast.config import Settings
        from market_forecast.persistence import SQLiteMarketRepository

        settings = Settings.from_environment()
        path = Path(args.database) if args.database else settings.database_path
        SQLiteMarketRepository(path).initialize()
        print(f"Initialized SQLite database: {path}")
        return 0
    if args.command == "collect":
        from market_forecast.config import Settings
        from market_forecast.persistence import RawArtifactStore, SQLiteMarketRepository
        from market_forecast.services import MarketCollectionService
        from market_forecast.sources import EntsoeSource, OperatorMarketSource

        settings = Settings.from_environment()
        service = MarketCollectionService(
            SQLiteMarketRepository(settings.database_path),
            RawArtifactStore(settings.raw_data_directory),
        )
        if args.source == "entsoe":
            if not args.bidding_zone:
                raise SystemExit("--bidding-zone is required for ENTSO-E")
            result = service.collect_entsoe(
                args.delivery_date,
                EntsoeSource(
                    settings.require_entsoe_token(),
                    timeout_seconds=settings.request_timeout_seconds,
                ),
                args.bidding_zone,
            )
        else:
            result = service.collect_operator_artifact(
                args.delivery_date,
                OperatorMarketSource(timeout_seconds=settings.request_timeout_seconds),
            )
            if result is None:
                print("Market Operator result is not published.")
                return 2
        print(
            f"Collected {result.source} {result.delivery_date}: "
            f"parsed={result.parsed_records}, inserted={result.inserted_records}, "
            f"sha256={result.artifact_sha256}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
