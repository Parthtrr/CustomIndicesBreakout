import argparse
from datetime import date

from services.thread_executor import ThreadExecutor
from utils.logger import get_logger

logger = get_logger(__name__)

def _parse_symbols(raw_symbols: str) -> list[str]:
    return [symbol.strip() for symbol in raw_symbols.split(",") if symbol.strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the shared pattern enricher")
    parser.add_argument(
        "--symbols",
        help="Comma-separated symbols to enrich instead of the configured universe",
    )
    parser.add_argument("--start-date", help="Start date for an explicit symbol run")
    parser.add_argument("--end-date", help="End date for an explicit symbol run")
    args = parser.parse_args(argv)
    if (args.start_date or args.end_date) and not args.symbols:
        parser.error("--start-date and --end-date require --symbols")
    return args


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    logger.info("Starting stock data enrichment process")
    executor = ThreadExecutor()
    if args.symbols:
        executor.process_symbols(
            _parse_symbols(args.symbols),
            args.start_date or "2010-01-01",
            args.end_date or date.today().strftime("%Y-%m-%d"),
        )
    else:
        executor.process_all_from_config()
    logger.info("Stock data enrichment process completed")

if __name__ == "__main__":
    main()
