"""Command-line entry point for safe one-shot operations."""

from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal

from market_forecast.neighbor_markets import MARKET_BY_CODE


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

    refresh = subparsers.add_parser(
        "refresh-operator", help="Collect tomorrow's Operator result and record its status."
    )
    refresh.add_argument(
        "--date",
        type=date.fromisoformat,
        dest="delivery_date",
        help="Optional explicit delivery date; defaults to tomorrow in Kyiv.",
    )

    subparsers.add_parser(
        "snapshot-baseline",
        help="Freeze the next operational baseline forecast for later scoring.",
    )

    neighbor_backfill = subparsers.add_parser(
        "backfill-neighbors",
        help="Collect ENTSO-E DAM prices for configured neighboring EU markets.",
    )
    neighbor_backfill.add_argument(
        "--market", choices=("all", *MARKET_BY_CODE), default="all"
    )
    neighbor_backfill.add_argument("--from", required=True, type=date.fromisoformat, dest="date_from")
    neighbor_backfill.add_argument("--to", required=True, type=date.fromisoformat, dest="date_to")
    neighbor_backfill.add_argument("--delay-seconds", type=float, default=0.5)
    neighbor_backfill.add_argument("--max-days", type=int, default=366)

    backfill = subparsers.add_parser("backfill", help="Collect an inclusive date range.")
    backfill.add_argument("--from", required=True, type=date.fromisoformat, dest="date_from")
    backfill.add_argument("--to", required=True, type=date.fromisoformat, dest="date_to")
    backfill.add_argument("--source", required=True, choices=("entsoe", "operator"))
    backfill.add_argument("--bidding-zone", help="Required EIC bidding zone for ENTSO-E.")
    backfill.add_argument("--delay-seconds", type=float, default=0.5)
    backfill.add_argument("--max-days", type=int, default=366)

    quality = subparsers.add_parser("quality", help="Report stored hourly coverage.")
    quality.add_argument("--from", required=True, type=date.fromisoformat, dest="date_from")
    quality.add_argument("--to", required=True, type=date.fromisoformat, dest="date_to")
    quality.add_argument("--source", required=True, choices=("entsoe", "operator"))
    quality.add_argument("--format", choices=("text", "json"), default="text")
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
    if args.command == "backfill":
        from market_forecast.config import Settings
        from market_forecast.persistence import RawArtifactStore, SQLiteMarketRepository
        from market_forecast.services import MarketCollectionService, run_backfill
        from market_forecast.sources import EntsoeSource, OperatorMarketSource

        settings = Settings.from_environment()
        service = MarketCollectionService(
            SQLiteMarketRepository(settings.database_path),
            RawArtifactStore(settings.raw_data_directory),
        )
        if args.source == "entsoe":
            if not args.bidding_zone:
                raise SystemExit("--bidding-zone is required for ENTSO-E")
            source = EntsoeSource(
                settings.require_entsoe_token(),
                timeout_seconds=settings.request_timeout_seconds,
            )
            collect_day = lambda day: service.collect_entsoe(day, source, args.bidding_zone)
        else:
            source = OperatorMarketSource(timeout_seconds=settings.request_timeout_seconds)
            collect_day = lambda day: service.collect_operator_artifact(day, source)
        results = run_backfill(
            args.date_from,
            args.date_to,
            collect_day,
            delay_seconds=args.delay_seconds,
            max_days=args.max_days,
        )
        for item in results:
            details = f" inserted={item.inserted_records}" if item.status == "collected" else ""
            message = f" error={item.message}" if item.message else ""
            print(f"{item.delivery_date} {item.status}{details}{message}")
        failures = sum(item.status == "failed" for item in results)
        unpublished = sum(item.status == "unpublished" for item in results)
        print(
            f"Backfill summary: requested={len(results)}, failed={failures}, "
            f"unpublished={unpublished}"
        )
        return 1 if failures else 0
    if args.command == "refresh-operator":
        from market_forecast.config import Settings
        from market_forecast.persistence import RawArtifactStore, SQLiteMarketRepository
        from market_forecast.services import (
            MarketCollectionService,
            next_delivery_date,
            refresh_operator_day,
        )
        from market_forecast.sources import OperatorMarketSource

        settings = Settings.from_environment()
        repository = SQLiteMarketRepository(settings.database_path)
        service = MarketCollectionService(
            repository,
            RawArtifactStore(settings.raw_data_directory),
        )
        delivery_date = args.delivery_date or next_delivery_date()
        result = refresh_operator_day(
            delivery_date,
            service,
            OperatorMarketSource(timeout_seconds=settings.request_timeout_seconds),
            repository,
        )
        details = f" inserted={result.inserted_records}" if result.status == "collected" else ""
        message = f" error={result.message}" if result.message else ""
        print(f"{result.delivery_date} {result.status}{details}{message}")
        if result.status == "collected":
            from market_forecast.services import generate_baseline_snapshot

            snapshot = generate_baseline_snapshot(repository)
            snapshot_status = "created" if snapshot.created else "already_exists"
            print(
                f"Forecast snapshot {snapshot_status}: target={snapshot.target_delivery_date} "
                f"model={snapshot.model_name}@{snapshot.model_version} "
                f"points={snapshot.points}"
            )
            return 0
        return 2 if result.status == "unpublished" else 1
    if args.command == "snapshot-baseline":
        from market_forecast.config import Settings
        from market_forecast.persistence import SQLiteMarketRepository
        from market_forecast.services import generate_baseline_snapshot

        settings = Settings.from_environment()
        result = generate_baseline_snapshot(SQLiteMarketRepository(settings.database_path))
        status = "created" if result.created else "already_exists"
        print(
            f"Forecast snapshot {status}: target={result.target_delivery_date} "
            f"model={result.model_name}@{result.model_version} points={result.points}"
        )
        return 0
    if args.command == "backfill-neighbors":
        from market_forecast.config import Settings
        from market_forecast.persistence import RawArtifactStore, SQLiteMarketRepository
        from market_forecast.services import MarketCollectionService, run_backfill
        from market_forecast.sources import EntsoeSource

        settings = Settings.from_environment()
        source = EntsoeSource(
            settings.require_entsoe_token(),
            timeout_seconds=settings.request_timeout_seconds,
        )
        service = MarketCollectionService(
            SQLiteMarketRepository(settings.database_path),
            RawArtifactStore(settings.raw_data_directory),
        )
        markets = (
            list(MARKET_BY_CODE.values())
            if args.market == "all"
            else [MARKET_BY_CODE[args.market]]
        )
        failures = 0
        unpublished = 0
        for market in markets:
            results = run_backfill(
                args.date_from,
                args.date_to,
                lambda day, item=market: service.collect_entsoe(
                    day, source, item.bidding_zone_eic
                ),
                delay_seconds=args.delay_seconds,
                max_days=args.max_days,
            )
            market_failures = sum(item.status == "failed" for item in results)
            market_unpublished = sum(item.status == "unpublished" for item in results)
            failures += market_failures
            unpublished += market_unpublished
            inserted = sum(item.inserted_records for item in results)
            print(
                f"{market.code} summary: requested={len(results)} "
                f"inserted={inserted} failed={market_failures} "
                f"unpublished={market_unpublished}"
            )
        return 1 if failures else 0
    if args.command == "quality":
        from market_forecast.config import Settings
        from market_forecast.persistence import SQLiteMarketRepository
        from market_forecast.services import build_quality_report

        settings = Settings.from_environment()
        repository = SQLiteMarketRepository(settings.database_path)
        repository.initialize()
        source = "operator_market" if args.source == "operator" else "entsoe"
        report = build_quality_report(repository, args.date_from, args.date_to, source)
        if args.format == "json":
            print(json.dumps([item.to_dict() for item in report], ensure_ascii=False, indent=2))
        else:
            for item in report:
                values = ""
                if item.actual_periods:
                    values = (
                        f" min={item.minimum_price} max={item.maximum_price} "
                        f"avg={item.average_price.quantize(Decimal('0.01'))}"
                    )
                print(
                    f"{item.delivery_date} {item.status} "
                    f"periods={item.actual_periods}/{item.expected_periods}{values}"
                )
        return 1 if any(item.status != "complete" for item in report) else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
